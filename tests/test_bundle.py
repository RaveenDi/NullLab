"""Tests for agent/bundle.py and agent/patch_export.py. Offline; fixture numbers are hand-made, never measurements.
The rerun.py mechanics test executes the real case code once (seed 42) to build ITS OWN expected values."""
import ast
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from agent import bundle, patch_export  # noqa: E402
from tests.test_hybrid import fake_loop_rec, fake_rule_rec  # noqa: E402

LEAKY, CLEAN = ROOT / "corpus" / "leak_prescale", ROOT / "corpus" / "clean_control"
pytestmark = pytest.mark.skipif(not (LEAKY / "data.csv").exists(), reason="corpus not present")
KEYLIKE = [re.compile(p) for p in (r"sk-[A-Za-z0-9_\-]{16,}", r"Bearer\s+[A-Za-z0-9._\-]{16,}", r"MODEL_API_KEY")]


@pytest.fixture
def run(tmp_path):
    case = tmp_path / "leak_prescale"
    shutil.copytree(LEAKY, case)
    rec = fake_rule_rec(case, 0.16)
    rd = tmp_path / "runs_x"
    rd.mkdir()
    (rd / "PREREG.sha256").write_text("a" * 64 + "  PREREG.md\n", encoding="utf-8")
    f = rd / "leak_prescale.json"
    f.write_text(json.dumps(rec), encoding="utf-8")
    return case, f, rec


def test_bundle_contents_manifest_and_determinism(run, tmp_path):
    case, f, _ = run
    r = bundle.build_bundle(case, tmp_path / "b1.zip", run=f)
    names = set(r["files"])
    for need in ("README.md", "MANIFEST.md5", "report.md", "rerun.py", "expected.json", "case/train.py", "case/data.csv", "case/excerpt.md",
                 "patches/fix_A.py", "patches/fix_B.py", "patches/fix_both.py", "patches/fix_both.patch", "patches/train.normalized.py",
                 "prereg/INPUT_HASHES.json", "prereg/PREREG.sha256", "traces/run_record.json"):
        assert need in names, need
    with zipfile.ZipFile(tmp_path / "b1.zip") as z:
        man = dict(reversed(ln.split("  ", 1)) for ln in z.read("MANIFEST.md5").decode().splitlines())
        assert set(man) == names - {"MANIFEST.md5"}
        for n, md5 in man.items():
            assert hashlib.md5(z.read(n)).hexdigest() == md5, n
        h = json.loads(z.read("prereg/INPUT_HASHES.json"))["sha256"]
        assert h["train.py"] == hashlib.sha256((case / "train.py").read_bytes()).hexdigest()
        readme = z.read("README.md").decode()
        assert "Honest limits" in readme and "not a re-run of the authors" in readme and "detects accidental change" in readme
    bundle.build_bundle(case, tmp_path / "b2.zip", run=f)
    assert (tmp_path / "b1.zip").read_bytes() == (tmp_path / "b2.zip").read_bytes()


def test_bundle_has_no_secrets_and_redacts_planted_ones(run, tmp_path, monkeypatch):
    case, f, rec = run
    planted = "sk-" + "A1b2C3d4E5f6G7h8I9j0K1l2"
    monkeypatch.setenv("MODEL_API_KEY", "envkeyvalue-0123456789abcdef")
    rec["notes_leak"] = f"MODEL_API_KEY={planted} and Bearer {'Z' * 30} and envkeyvalue-0123456789abcdef"
    f.write_text(json.dumps(rec), encoding="utf-8")
    r = bundle.build_bundle(case, tmp_path / "b.zip", run=f)
    assert r["redactions"] >= 3
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        for n in z.namelist():
            body = z.read(n).decode("utf-8", "replace")
            assert planted not in body and "envkeyvalue-0123456789abcdef" not in body, n
            if n != "README.md":
                assert not any(p.search(body) for p in KEYLIKE), n
        assert "redaction(s) were made" in z.read("README.md").decode()


def test_clean_bundle_scan_has_no_false_positive_on_sha256_hashes(run, tmp_path):
    case, f, _ = run
    r = bundle.build_bundle(case, tmp_path / "b.zip", run=f)
    assert r["redactions"] == 0
    assert bundle.scan_secrets("sha256 " + "a" * 64 + " seeds 42 43 44") == []
    assert bundle.scan_secrets("MODEL_API_KEY=abc") and bundle.scan_secrets("x sk-abcdefghijklmnopqrstu")


def test_loop_run_bundle_carries_plan_and_raw_reply(tmp_path):
    case = tmp_path / "leak_prescale"
    shutil.copytree(LEAKY, case)
    rd = tmp_path / "runs_y"
    rd.mkdir()
    (rd / "r1.json").write_text(json.dumps({"repeat": "hybrid", "loop": {"leak_prescale": fake_loop_rec(case, 0.12)},
                                            "plan": {"leak_prescale": {"raw": '{"A": "mock"}'}}}), encoding="utf-8")
    r = bundle.build_bundle(case, tmp_path / "b.zip", run=rd / "r1.json")
    assert {"traces/plan.json", "traces/event_log.json", "traces/planner_raw_reply.txt"} <= set(r["files"])


def test_no_data_flag(run, tmp_path):
    case, f, _ = run
    r = bundle.build_bundle(case, tmp_path / "b.zip", run=f, include_data=False)
    assert "case/data.csv" not in r["files"]


def test_rerun_script_mechanics(run, tmp_path):
    case, f, _ = run
    bundle.build_bundle(case, tmp_path / "b.zip", run=f)
    out = tmp_path / "x"
    with zipfile.ZipFile(tmp_path / "b.zip") as z:
        z.extractall(out)

    def load(name, path):
        spec = importlib.util.spec_from_file_location(name, path)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        return m
    cwd = os.getcwd()
    os.chdir(out / "case")
    try:
        tr, fx = load("t_claim", out / "case" / "train.py"), load("t_fix", out / "patches" / "fix_both.py")
        df = tr.load("data.csv")
        sc = lambda y, p: sum(int(a == b) for a, b in zip(y, p)) / len(y)  # noqa: E731
        a, b = sc(*tr.claimed_eval(df, 42)), sc(*fx.controlled_eval(df, 42))
    finally:
        os.chdir(cwd)
    exp = {"metric": "accuracy", "seeds": ["42"], "claimed": {"42": a}, "controlled": {"42": b}}
    (out / "expected.json").write_text(json.dumps(exp), encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", "rerun.py"], cwd=out, capture_output=True, text=True, timeout=600)
    assert p.returncode == 0 and "MATCH" in p.stdout, p.stdout + p.stderr
    exp["controlled"]["42"] += 0.01
    (out / "expected.json").write_text(json.dumps(exp), encoding="utf-8")
    p = subprocess.run([sys.executable, "-I", "rerun.py"], cwd=out, capture_output=True, text=True, timeout=600)
    assert p.returncode == 1 and "DIFFERS" in p.stdout


# ---------------- patch_export ----------------
def test_patch_header_and_roundtrip(run, tmp_path):
    case, f, rec = run
    out = tmp_path / "fix.patch"
    text = patch_export.export_patch(case, out, run=f)
    head = text.split("\n--- a/train.py")[0]
    for need in ("provenance:      rules (no model)", "controlled score:", "seeds:           42, 43, 44", "n scored rows:   42: 100", "inflation:       +16.000 pp",
                 "claimed score:   0.9000", "applies to:"):
        assert need in head, need
    assert out.read_text(encoding="utf-8") == text
    base = patch_export.normalized_base(case)
    new = patch_export.apply_unified(base, text)
    ast.parse(new)
    assert new != base
    assert "_RF" in new   # R2's scope helper is part of the executed patch and shows in the diff (honest: the rule baseline adds helper code)
    added = [ln[1:] for ln in text.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    assert all(a in new.splitlines() for a in added)


def test_patch_labels_spark_provenance_and_refuses_empty(tmp_path):
    case = tmp_path / "leak_prescale"
    shutil.copytree(LEAKY, case)
    rec = fake_loop_rec(case, 0.12)
    t = patch_export.build_patch(case, rec, "loop")
    assert "provenance:      Spark: MOCK spark (test fixture)" in t
    if CLEAN.exists():
        clean = tmp_path / "clean_control"
        shutil.copytree(CLEAN, clean)
        crec = fake_rule_rec(clean, 0.0)
        with pytest.raises(patch_export.PatchError):
            patch_export.build_patch(clean, crec, "rulefix")


def test_patch_cli(run, tmp_path):
    case, f, _ = run
    assert patch_export.main([str(case), "--run", str(f), "--out", str(tmp_path / "p.patch"), "--base-out", str(tmp_path / "base.py")]) == 0
    assert (tmp_path / "p.patch").exists() and (tmp_path / "base.py").exists()
