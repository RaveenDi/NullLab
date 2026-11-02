"""Tests for agent/smoke.py (offline, $0). The sandbox runs are real subprocesses on tiny samples (a few seconds each)."""
import json
import time
from pathlib import Path

import pytest

from agent import smoke

ROOT = Path(__file__).resolve().parent.parent
G7_R3 = ROOT / "runs_g7" / "r3.json"


def test_lint_clean_and_undefined_name_and_syntax():
    assert smoke.lint("import numpy as np\ndef f(x):\n    y = [np.sum(v) for v in x]\n    return y\n") == []
    f = smoke.lint("def f(x):\n    return helper(x)\n")
    assert f and f[0]["kind"] == "NameError" and "helper" in f[0]["msg"] and f[0]["line"] == 2
    s = smoke.lint("def f(:\n  pass\n")
    assert s and s[0]["kind"] == "SyntaxError"
    # names bound in other scopes / comprehension / except / with / lambda args are not reported
    ok = "def g():\n    try:\n        pass\n    except Exception as e:\n        print(e)\n    with open('x') as fh:\n        fh.read()\n    return (lambda z: z)(1)\n"
    assert smoke.lint(ok) == []


def test_downsample_keeps_order_and_minority(tmp_path):
    rows = ["t,a,target"] + [f"{i},{i * 2},{1 if i % 60 == 0 else 0}" for i in range(3000)]
    src = tmp_path / "d.csv"
    src.write_text("\n".join(rows) + "\n")
    n = smoke.downsample_csv(src, tmp_path / "o.csv", 200, target="target")
    out = (tmp_path / "o.csv").read_text().splitlines()[1:]
    assert n == len(out) <= 200
    t = [int(x.split(",")[0]) for x in out]
    assert t == sorted(t)                                      # original order kept
    assert sum(x.endswith(",1") for x in out) >= 40            # the minority class survives
    small = tmp_path / "s.csv"
    small.write_text("t,target\n1,0\n2,1\n")
    assert smoke.downsample_csv(small, tmp_path / "so.csv", 200) == 2


def test_parse_traceback_picks_last_patch_frame():
    tb = "\n".join([
        "Traceback (most recent call last):",
        '  File "C:/x/run_factorial.py", line 45, in main',
        "    y, p = mods[c].controlled_eval(df, s)",
        '  File "C:/x/fix_A.py", line 45, in split_rows',
        "    order = np.argsort(df['epoch'].to_numpy(kind='stable'))",
        '  File "C:/venv/pandas/core/base.py", line 717, in to_numpy',
        "    raise TypeError(",
        "TypeError: to_numpy() got an unexpected keyword argument 'kind'", ""])
    r = smoke.parse_traceback(tb)
    assert (r["kind"], r["config"], r["line"], r["function"]) == ("TypeError", "fix_A", 45, "split_rows")
    assert "to_numpy(kind='stable')" in r["code"]


@pytest.mark.skipif(not G7_R3.exists(), reason="runs_g7/r3.json not present")
def test_replay_g7_r3_patch_is_caught_in_under_30s():
    t0 = time.time()
    v = smoke.replay_recorded(ROOT / "real" / "civilwar_disguised", G7_R3, "civilwar_disguised")
    dt = time.time() - t0
    assert dt < 30 and v["elapsed_s"] < 30
    assert v["ok"] is False and v["stage"] == "smoke" and v["definitive"] is True
    assert v["kind"] == "TypeError" and "to_numpy" in v["message"] and "kind" in v["message"]
    assert v["config"] == "fix_A" and v["line"] == 45 and "to_numpy(kind='stable')" in v["code"]
    # the structured reason is usable as repair-prompt text
    assert v["repair_text"].startswith("PRE-FLIGHT FAILED (smoke) in fix_A at line 45: TypeError")
    assert "to_numpy(kind='stable')" in v["repair_text"]


@pytest.mark.skipif(not G7_R3.exists(), reason="runs_g7/r3.json not present")
def test_recorded_good_plan_passes_smoke():
    """Positive control: the plan the G7 r3 CLEAN case ran fine with at full size must pass (no false alarm), also on the 1.6 percent minority data."""
    v = smoke.replay_recorded(ROOT / "real" / "civilwar_disguised_clean", G7_R3, "civilwar_disguised_clean")
    assert v["ok"] is True, v
    assert v["elapsed_s"] < 30 and v["repair_text"] == ""


def test_lint_stage_blocks_before_any_process(tmp_path):
    case = ROOT / "real" / "civilwar_disguised"
    good = (case / "train.py").read_text(encoding="utf-8")
    bad = good + "\ndef controlled_eval(df, seed):\n    return undefined_helper(df)\n"
    v = smoke.smoke(case, {"fix_A": good, "fix_B": bad, "fix_both": good})
    assert not v["ok"] and v["stage"] == "lint" and v["kind"] == "NameError" and v["config"] == "fix_B" and "undefined_helper" in v["message"]
    assert v["elapsed_s"] < 2 and v["definitive"] is True
    v2 = smoke.smoke(case, {"fix_A": good, "fix_B": None, "fix_both": good})
    assert v2["kind"] == "StructureError"


def test_runtime_nameerror_inside_function_in_pre_flight_and_value_error_is_not_definitive(tmp_path):
    case = ROOT / "real" / "ehg_disguised"          # 300 rows: fast
    base = (case / "train.py").read_text(encoding="utf-8")
    boom = base + "\ndef controlled_eval(df, seed):\n    raise ValueError('a cannot be empty unless no samples are taken')\n"
    v = smoke.smoke(case, {"fix_A": boom, "fix_B": boom, "fix_both": boom}, timeout=30)
    assert not v["ok"] and v["kind"] == "ValueError" and v["definitive"] is False and "escalated_from" in v
