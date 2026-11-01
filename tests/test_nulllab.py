import json
import os
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pipeline  # noqa: E402
from agent import extract, falsify, llm  # noqa: E402
from baselines.checklist import b0_checklist  # noqa: E402
from report import render  # noqa: E402
from sandbox import executor, verdict  # noqa: E402
from sandbox.run import paired_bootstrap  # noqa: E402

CASES = ["hero_tabular", "clean_control", "synthetic_leak"]
os.environ["NULLLAB_NO_DOCKER"] = "1"  # tests use the restricted-subprocess backend
GENERIC = falsify.PATCH_GENERIC


# ---------------- M1: harness ----------------
@pytest.mark.parametrize("case", CASES)
def test_sandbox_seed_fixed(case):
    patch = falsify.PATCH_TE if case == "synthetic_leak" else GENERIC
    a = executor.run_experiment(ROOT / "corpus" / case, patch, n_boot=50, timeout=120, backend="subprocess")
    b = executor.run_experiment(ROOT / "corpus" / case, patch, n_boot=50, timeout=120, backend="subprocess")
    assert a["status"] == b["status"] == "ok"
    assert a["result"]["seeds"] == b["result"]["seeds"]          # identical numbers on re-run
    assert set(a["result"]["seeds"]) == {"42", "43", "44"}


def test_timeout_enforced():
    patch = "import time\ndef controlled_eval(df, seed):\n    time.sleep(60)\n"
    r = executor.run_experiment(ROOT / "corpus" / "clean_control", patch, n_boot=5, timeout=8, backend="subprocess")
    assert r["status"] == "timeout"


def test_network_blocked_and_no_secrets():
    patch = ("import os, socket\n"
             "def controlled_eval(df, seed):\n"
             "    assert 'MODEL_API_KEY' not in os.environ\n"
             "    try:\n        socket.create_connection(('example.com', 80), timeout=2)\n"
             "    except OSError:\n        raise RuntimeError('NET_BLOCKED')\n"
             "    raise SystemExit('network was reachable')\n")
    r = executor.run_experiment(ROOT / "corpus" / "clean_control", patch, n_boot=5, backend="subprocess")
    assert r["status"] == "error" and "NET_BLOCKED" in r["stderr"]


def test_experiment_cannot_open_ground_truth():
    gt = str(ROOT / "eval" / "ground_truth.json").replace("\\", "/")
    patch = (f"def controlled_eval(df, seed):\n    try:\n        open(r'{gt}').read()\n"
             "    except PermissionError:\n        raise RuntimeError('GT_BLOCKED')\n    raise SystemExit('read ground truth!')\n")
    r = executor.run_experiment(ROOT / "corpus" / "clean_control", patch, n_boot=5, backend="subprocess")
    assert r["status"] == "error" and "GT_BLOCKED" in r["stderr"]


def test_agent_view_has_no_ground_truth():
    for c in CASES:
        assert sorted(p.name for p in (ROOT / "corpus" / c).iterdir()) == ["data.csv", "excerpt.md", "train.py"]
    for p in (ROOT / "agent").glob("*.py"):
        assert "ground_truth" not in p.read_text(), p
        assert not re.search(r"from\s+eval|import\s+eval", p.read_text()), p


def test_agent_pipeline_never_opens_eval_files():
    opened = []
    sys.addaudithook(lambda ev, a: opened.append(str(a[0])) if ev == "open" and a and isinstance(a[0], str) else None)
    pipeline.run_case("clean_control", n_boot=20)
    bad = [p for p in opened if "ground_truth" in p or "/eval/" in p.replace("\\", "/")]
    assert not bad


def test_columns_hashed_in_agent_view():
    for c in CASES:
        header = (ROOT / "corpus" / c / "data.csv").read_text().splitlines()[0]
        assert all(re.fullmatch(r"c_[0-9a-f]{6}", h) for h in header.split(","))
        assert "alcohol" not in (ROOT / "corpus" / c / "train.py").read_text().lower()


# ---------------- stats / verdict ----------------
def test_paired_bootstrap_known():
    import numpy as np
    y = np.zeros(200)
    r = paired_bootstrap(y, y, y, np.r_[np.zeros(120), np.ones(80)], 500, 1)   # claimed 1.0 vs controlled 0.6
    assert abs(r["delta"] - 0.4) < 1e-9 and r["ci_lo"] > 0.3


def _r(delta, lo, hi):
    return {"delta": delta, "ci_lo": lo, "ci_hi": hi}


def test_verdict_logic():
    assert verdict.verdict({"1": _r(.2, .1, .3), "2": _r(.2, .1, .3), "3": _r(.2, .1, .3)})["verdict"] == "FALSIFIED"
    assert verdict.verdict({"1": _r(0, -.02, .02), "2": _r(.01, -.01, .03), "3": _r(0, -.02, .02)})["verdict"] == "SURVIVED"
    mixed = verdict.verdict({"1": _r(.2, .1, .3), "2": _r(.0, -.1, .1), "3": _r(.2, .1, .3)})
    assert mixed["verdict"] == "INCONCLUSIVE" and not mixed["agree"]
    assert verdict.verdict({"1": _r(.2, .1, .3), "2": _r(.2, .1, .3), "3": _r(.02, .005, .03)})["verdict"] == "INCONCLUSIVE"


# ---------------- M2: extraction / grounding ----------------
@pytest.mark.parametrize("case", CASES)
def test_pointers_verbatim(case):
    c = extract.extract_claim(ROOT / "corpus" / case, "mock")
    assert c["grounding"]["precision"] == 1.0 and "MOCK" in c["mode"]
    assert c["methods_line"] in (ROOT / "corpus" / case / "excerpt.md").read_text()
    assert c["code_line"] in (ROOT / "corpus" / case / "train.py").read_text()


def test_grounding_detects_fabricated_pointer():
    g = extract.grounded({"methods_line": "made up", "code_line": "x = 1"}, "real line", "y = 2")
    assert g["precision"] == 0.0


def test_memorization_probe_unverified_in_mock():
    assert extract.memorization_probe(ROOT / "corpus" / "hero_tabular", "mock")["status"] == "UNVERIFIED"


# ---------------- M3: falsifier + end-to-end (MOCK) ----------------
def test_prereg_before_run_and_hash():
    claim = extract.extract_claim(ROOT / "corpus" / "hero_tabular", "mock")
    h = falsify.propose(ROOT / "corpus" / "hero_tabular", claim, "mock")
    assert len(h["hypotheses"]) == 3 and all("direction" in x for x in h["hypotheses"]) and len(h["prereg_sha256"]) == 64


@pytest.mark.parametrize("case,expected", [("hero_tabular", "FALSIFIED"), ("clean_control", "SURVIVED"), ("synthetic_leak", "FALSIFIED")])
def test_end_to_end_mock(case, expected):
    r = pipeline.run_case(case, "mock", n_boot=300)
    assert r["verdict"]["verdict"] == expected and r["verdict"]["agree"]
    assert "MOCK" in r["mode"]
    assert [e["phase"] for e in r["log"]][:1] == ["Plan"] and {"Plan", "Act", "Verify"} <= {e["phase"] for e in r["log"]}


def test_recover_retries_once(monkeypatch):
    monkeypatch.setattr(falsify, "_mock", lambda code: {"broken": "x", "split_key": "x", "sig": "x", "kind": "x",
                                                         "patch": "def controlled_eval(df, seed):\n    raise ValueError('boom')\n"})
    r = pipeline.run_case("clean_control", "mock", n_boot=20)
    assert [x["status"] for x in r["runs"]] == ["error", "ok"] and any(e["phase"] == "Recover" for e in r["log"])


# ---------------- baselines / ablation ----------------
def test_b0_misses_code_dependent_leaks():
    assert [b0_checklist(ROOT / "corpus" / c)["flagged"] for c in CASES] == [False, False, False]


# ---------------- live guard ----------------
def test_live_refused_without_spend_ok(monkeypatch):
    monkeypatch.setattr(llm, "spend_ok", lambda usd: False)
    with pytest.raises(llm.LiveNotAllowed):
        llm.live_complete("s", "u")


# ---------------- report ----------------
def test_report_has_watermark_and_phases():
    run = json.loads((ROOT / "runs" / "hero_tabular.json").read_text())
    page = render.render_case(run)
    assert "REAL-PINNED" in page and "FALSIFIED" in page and "Recover" in page and "MOCK" in page
    syn = render.render_case(json.loads((ROOT / "runs" / "synthetic_leak.json").read_text()))
    assert "SYNTHETIC" in syn
