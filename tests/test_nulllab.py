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
NEWCASES = ["leak_prescale", "leak_temporal", "leak_proxy", "leak_group", "clean_wine_correct", "clean_group_correct"]
ALLCASES = CASES + NEWCASES
os.environ["NULLLAB_NO_DOCKER"] = "1"  # tests use the restricted-subprocess backend
# Tests must never overwrite real run JSONs in runs/ (an earlier version clobbered the LIVE EVAL-2 per-case files).
import tempfile  # noqa: E402
pipeline.RUNS = Path(tempfile.mkdtemp(prefix="nulllab_test_runs_"))
pipeline.RUNS_LIVE = Path(tempfile.mkdtemp(prefix="nulllab_test_runs_live_"))
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


def test_grounding_normalised_whitespace_and_line_numbers():
    excerpt = "line one\n  Our classifier achieves 96% accuracy on held-out data.\nline three\n"
    code = "x = 1\ntr, te = split_idx(data, seed)\ny = 2\n"
    g = extract.grounded({"methods_line": "Our classifier achieves 96%  accuracy on held-out data.",
                          "methods_line_no": 2,
                          "code_line": "tr, te = split_idx(data,  seed)",
                          "code_line_no": 2}, excerpt, code)
    assert g["precision"] == 1.0
    assert g["line_numbers"] == {"methods_line_no": 2, "code_line_no": 2}
    bad_no = extract.grounded({"methods_line": "Our classifier achieves 96% accuracy on held-out data.",
                               "methods_line_no": 3,
                               "code_line": "tr, te = split_idx(data, seed)",
                               "code_line_no": 2}, excerpt, code)
    assert bad_no["flags"]["methods_line"] is False and bad_no["precision"] == 0.5


def test_new_cases_agent_view_isolated():
    for c in NEWCASES:
        d = ROOT / "corpus" / c
        assert sorted(p.name for p in d.iterdir()) == ["data.csv", "excerpt.md", "train.py"]
        header = (d / "data.csv").read_text().splitlines()[0]
        assert all(re.fullmatch(r"c_[0-9a-f]{6}", h) for h in header.split(","))
        assert "alcohol" not in (d / "train.py").read_text().lower()
    for p in (ROOT / "agent").glob("*.py"):
        assert "ground_truth" not in p.read_text(), p


def test_new_cases_pointers_verbatim():
    for c in NEWCASES:
        claim = extract.extract_claim(ROOT / "corpus" / c, "mock")
        assert claim["grounding"]["precision"] == 1.0, c
        assert claim["methods_line"] in (ROOT / "corpus" / c / "excerpt.md").read_text()
        assert claim["code_line"] in (ROOT / "corpus" / c / "train.py").read_text()


def test_new_cases_mock_falsifier_routes_by_class():
    for c, kind in [("leak_prescale", "fit on all rows"), ("leak_temporal", "random split"),
                    ("leak_proxy", "proxy column"), ("leak_group", "group identifier")]:
        claim = extract.extract_claim(ROOT / "corpus" / c, "mock")
        h = falsify.propose(ROOT / "corpus" / c, claim, "mock")
        assert kind in h["broken_assumption"], (c, h["broken_assumption"])
    for c in ("clean_wine_correct", "clean_group_correct"):
        claim = extract.extract_claim(ROOT / "corpus" / c, "mock")
        h = falsify.propose(ROOT / "corpus" / c, claim, "mock")
        assert h["primary"] == "H1" and len(h["hypotheses"]) == 3


def test_end_to_end_new_cases_agree():
    for c in NEWCASES:
        r = pipeline.run_case(c, "mock", n_boot=100)
        assert r["verdict"]["agree"] and "MOCK" in r["mode"], (c, r["verdict"])


def test_b0_b1_run_on_all_cases():
    from baselines.checklist import b1_groupkfold
    for c in NEWCASES:
        b0 = b0_checklist(ROOT / "corpus" / c)
        assert set(b0) >= {"flagged", "flags"}
        b1 = b1_groupkfold(ROOT / "corpus" / c, n_boot=50)
        assert "flagged" in b1


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
    run = json.loads((pipeline.RUNS / "hero_tabular.json").read_text())  # written by test_end_to_end_mock above
    page = render.render_case(run)
    assert "REAL-PINNED" in page and "FALSIFIED" in page and "Recover" in page and "MOCK" in page
    syn = render.render_case(json.loads((pipeline.RUNS / "synthetic_leak.json").read_text()))
    assert "SYNTHETIC" in syn


# ---------------- G4 housekeeping: tests never touch real run folders ----------------
def test_tests_write_only_to_temp_dirs():
    tmp = Path(tempfile.gettempdir()).resolve()
    for d in (pipeline.RUNS, pipeline.RUNS_LIVE):
        assert tmp in Path(d).resolve().parents, d


def test_mock_run_refuses_runs_live(tmp_path):
    with pytest.raises(RuntimeError):
        pipeline.run_case("clean_control", "mock", n_boot=5, out_dir=ROOT / "runs_live")


# ---------------- G0b: exfiltration (BRIEF-4) ----------------
def _short(p):
    """Windows 8.3 short name of p if the volume has them, else p itself."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 1024)
        return buf.value if n else str(p)
    except Exception:
        return str(p)


GT_PATH = ROOT / "eval" / "ground_truth.json"
EXFIL_ATTEMPTS = {
    "abs_path": "open(r'{gt}').read()",
    "short_8dot3_path": "open(r'{short}').read()",
    "pathlib_read_bytes": "import pathlib; pathlib.Path(r'{gt}').read_bytes()",
    "os_open_fd": "import os; os.read(os.open(r'{gt}', os.O_RDONLY), 100)",
    "other_evaluator_file": "open(r'{other}').read()",
    "file_outside_sandbox": "open(r'{readme}').read()",
    "subprocess_type": "import subprocess; print(subprocess.run(['cmd', '/c', 'type', r'{gt}'], capture_output=True).stdout)",
    "os_system": "import os; os.system(r'type \"{gt}\" > leaked.txt'); open('leaked.txt').read()",
    "hardlink_into_cwd": "import os; os.link(r'{gt}', 'gt_link.json'); open('gt_link.json').read()",
    "ctypes_createfile": ("import ctypes; k = ctypes.WinDLL('kernel32'); "
                          "h = k.CreateFileW(r'{gt}', 0x80000000, 1, None, 3, 0, None); assert h not in (0, -1)"),
}


@pytest.mark.parametrize("name", sorted(EXFIL_ATTEMPTS))
def test_exfil_ground_truth_blocked(name):
    """An agent patch that tries to read evaluator files (by absolute path or by any bypass) must fail in the sandbox."""
    stmt = EXFIL_ATTEMPTS[name].format(gt=GT_PATH, short=_short(GT_PATH), other=ROOT / "eval" / "build_corpus.py",
                                       readme=ROOT / "README.md")
    patch = ("def controlled_eval(df, seed):\n    try:\n        " + stmt + "\n"
             "    except BaseException as e:\n        raise RuntimeError('EXFIL_BLOCKED %r' % (e,))\n"
             "    raise SystemExit('EXFIL_SUCCEEDED')\n")
    r = executor.run_experiment(ROOT / "corpus" / "clean_control", patch, seeds=(42,), n_boot=5, backend="subprocess")
    assert r["status"] == "error" and "EXFIL_BLOCKED" in r["stderr"] and "EXFIL_SUCCEEDED" not in r["stderr"], (name, r)


def test_factorial_sandbox_blocks_exfil():
    gt = ROOT / "eval" / "factorial_truth.json"
    bad = f"def controlled_eval(df, seed):\n    return open(r'{gt}').read()\n"
    r = executor.run_factorial(ROOT / "corpus" / "clean_control", {"fix_A": bad, "fix_B": bad, "fix_both": bad},
                               seeds=(42,), timeout=120)
    assert r["status"] == "error" and "PermissionError" in r["stderr"]


# ---------------- G4: preregistered scoring helpers ----------------
def test_g4_sign_rules():
    import g4
    mk = lambda lo, hi: {"full": {"drop_ci": {"fix_both": [lo, hi]}}}  # noqa: E731
    assert g4.case_sign({"42": mk(.01, .1), "43": mk(.02, .1), "44": mk(-.01, .1)})[0] == "+"
    assert g4.case_sign({"42": mk(-.1, -.01), "43": mk(-.1, -.02), "44": mk(-.1, .01)})[0] == "-"
    assert g4.case_sign({"42": mk(-.1, .1), "43": mk(.01, .1), "44": mk(-.1, -.01)})[0] == "mixed"
    assert (g4.b3_sign(2), g4.b3_sign(1.9), g4.b3_sign(-2)) == ("+", "0", "-")


def test_g4_agent_views_isolated():
    for c in ("g4_freight_delay", "g4_pump_inspection", "g4_crop_irrigation", "g4_assay_replicates", "g4_visit_history_clean"):
        d = ROOT / "factorial" / c
        assert sorted(p.name for p in d.iterdir() if p.is_file()) == ["data.csv", "excerpt.md", "train.py"]
        header = (d / "data.csv").read_text().splitlines()[0]
        assert all(re.fullmatch(r"c_[0-9a-f]{6}", h) for h in header.split(",")), c
        low = ((d / "train.py").read_text() + (d / "excerpt.md").read_text()).lower()
        assert not any(w in low for w in ("leak", "inflat", "cancel", "culprit", "synerg")), c
