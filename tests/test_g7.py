"""G7 tests: disguised civil-war case hygiene, SPLIT-USE-REQUIRED rule, probe verdict, preregistration is write-once.
Offline, no live calls; anything written goes to pytest temp dirs (never runs*/)."""
import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import factorial_g7 as g7  # noqa: E402

LEAKY, CLEAN = ROOT / "real" / "civilwar_disguised", ROOT / "real" / "civilwar_disguised_clean"
HEADER = ["epoch"] + [f"f{i:02d}" for i in range(1, 91)] + ["target"]
FORBIDDEN = ("war", "conflict", "civil", "countr", "muchlinski", "sambanis", "caret", "reanalys", "neunhoeffer", "dataverse",
             "0.36", "year")


def _src(case):
    return (case / "train.py").read_text(encoding="utf-8"), (case / "excerpt.md").read_text(encoding="utf-8")


def _plan(split_body, step="split_rows", kind="split", other=None):
    edits = {"A": {"kind": kind, "steps": {step: split_body}}}
    edits["B"] = other or {"kind": "fit_scope", "steps": {"tune_mtry": "def tune_mtry(X, y, seed, k=10):\n    return MTRY_GRID[0]"}}
    return {"edits": edits}


TEMPORAL = "def split_rows(df, seed):\n    idx = np.arange(len(df))\n    return idx[df['epoch'].to_numpy() < 46], idx[df['epoch'].to_numpy() >= 46]"
TEMPORAL_VAR = ("def split_rows(df, seed):\n    idx = np.arange(len(df))\n    e = df['epoch'].to_numpy()\n"
                "    cut = np.quantile(e, 0.8)\n    return idx[e <= cut], idx[e > cut]")
RANDOM = ("def split_rows(df, seed):\n    from sklearn.model_selection import train_test_split\n    idx = np.arange(len(df))\n"
          "    y = df[TARGET].to_numpy().astype(int)\n    tr, te = train_test_split(idx, test_size=0.2, random_state=seed, stratify=y)\n"
          "    return np.asarray(tr), np.asarray(te)")
POSITIONAL = "def split_rows(df, seed):\n    idx = np.arange(len(df))\n    n = int(len(df) * 0.8)\n    return idx[:n], idx[n:]"


# ---------------- case hygiene ----------------
@pytest.mark.parametrize("case", [LEAKY, CLEAN], ids=lambda p: p.name)
def test_agent_view_has_no_source_fingerprints(case):
    train, exc = _src(case)
    text = (train + exc).lower()
    for w in FORBIDDEN:
        assert w not in text, f"{w!r} leaks into {case.name}"
    assert not re.search(r"\b(1945|1990|2000|19\d\d)\b", text)
    # the only hint of the claim class is the neutral forecasting wording
    assert g7.forecast_claim(exc)
    assert 'TARGET = "target"' in train


def test_truth_lives_outside_the_case_folders():
    truth = json.loads((ROOT / "eval" / "g7_truth.json").read_text(encoding="utf-8"))
    assert truth["civilwar_disguised"]["published_inflation_pr_auc"] == 0.36
    assert truth["civilwar_disguised"]["leaky"] is True and truth["civilwar_disguised_clean"]["leaky"] is False
    for case in (LEAKY, CLEAN):
        assert sorted(p.name for p in case.iterdir() if p.is_file()) == ["data.csv", "excerpt.md", "train.py"] or \
            sorted(p.name for p in case.iterdir() if p.is_file()) == ["excerpt.md", "train.py"]
    from sandbox import executor
    text = Path(executor.__file__).read_text(encoding="utf-8")
    assert '("train.py", "data.csv")' in text  # the sandbox copies only these two files


def test_leaky_and_clean_differ_only_in_the_split_step():
    a, _ = _src(LEAKY)
    b, _ = _src(CLEAN)
    da = [l for l in a.splitlines()]
    db = [l for l in b.splitlines()]
    diff = [(x, y) for x, y in zip(da, db) if x != y]
    assert 0 < len(diff) <= 4
    assert "return idx, idx" in a and "epoch" in b


@pytest.mark.skipif(not (LEAKY / "data.csv").exists(), reason="raw data is rebuilt by eval/build_g7.py (git-ignored)")
def test_disguised_data_is_a_monotone_relabelling_of_the_source():
    truth = json.loads((ROOT / "eval" / "g7_truth.json").read_text(encoding="utf-8"))
    mp = truth["civilwar_disguised"]["column_map_original_to_disguised"]
    src = pd.read_csv(ROOT / "real" / "civilwar_apparent" / "data.csv")
    dis = pd.read_csv(LEAKY / "data.csv")
    assert list(dis.columns) == [c for c in dis.columns] and "epoch" in dis.columns and "target" in dis.columns
    assert (dis["epoch"] == src["year"] - 1944).all() and (dis["target"] == src["warstds"]).all()
    for orig, new in mp.items():
        if orig in ("warstds", "year"):
            continue
        assert (src[orig].rank(method="dense").to_numpy() == dis[new].rank(method="dense").to_numpy()).all(), orig
    assert dis.shape == (7140, 92)
    assert pd.read_csv(CLEAN / "data.csv").equals(dis)
    assert int(dis["target"].sum()) == 116


# ---------------- SPLIT-USE-REQUIRED ----------------
def test_reference_temporal_split_accepted():
    train, exc = _src(LEAKY)
    assert g7.check_split_required(train, exc, HEADER, {"edits": {"A": g7.REF_FIX["A"], "B": g7.REF_FIX["B"]}}) == []


def test_temporal_through_variable_accepted():
    train, exc = _src(LEAKY)
    assert g7.check_split_required(train, exc, HEADER, _plan(TEMPORAL_VAR)) == []


@pytest.mark.parametrize("body", [RANDOM, POSITIONAL], ids=["random", "positional"])
def test_non_temporal_holdout_rejected_for_forecast_claim(body):
    train, exc = _src(LEAKY)
    v = g7.check_split_required(train, exc, HEADER, _plan(body))
    assert v and v[0].startswith("SPLIT-USE-REQUIRED")


def test_missing_temporal_split_rejected():
    train, exc = _src(LEAKY)
    v = g7.check_split_required(train, exc, HEADER, {"edits": {"A": {"kind": "fit_scope", "steps": {"tune_mtry": "def tune_mtry(X, y, seed, k=10):\n    return 2"}},
                                                                  "B": {"kind": "split", "steps": {"tune_mtry": "def tune_mtry(X, y, seed, k=10):\n    return 46"}}}})
    assert v and "make a temporal split" in v[0]
    assert g7.check_split_required(train, exc, HEADER, {"edits": {}})


def test_temporal_edit_in_inner_tuning_does_not_satisfy_the_rule():
    train, exc = _src(LEAKY)
    inner = {"kind": "split", "steps": {"tune_mtry": "def tune_mtry(X, y, seed, k=10):\n    e = 0\n    return 2 if e < 3 else 46"}}
    v = g7.check_split_required(train, exc, HEADER, _plan(RANDOM, other=inner))
    assert v


def test_clean_pipeline_already_temporal():
    train, exc = _src(CLEAN)
    assert g7.check_split_required(train, exc, HEADER, {"edits": {}}) == []
    assert g7.check_split_required(train, exc, HEADER, _plan(TEMPORAL)) == []
    assert g7.check_split_required(train, exc, HEADER, _plan(RANDOM))  # replacing a temporal hold-out by a random one


def test_rule_inactive_without_forecast_claim():
    train, exc = _src(LEAKY)
    exc2 = exc.replace("forecast", "describe").replace("not trained on", "trained on")
    assert not g7.forecast_claim(exc2)
    assert g7.check_split_required(train, exc2, HEADER, _plan(RANDOM)) == []


def test_holdout_step_detection():
    train, _ = _src(LEAKY)
    assert g7.holdout_steps(train) == {"split_rows"}


def test_g6_saved_plans_replayed():
    """The G6 civil-war plans (random 80/20 hold-out) would have been REJECTED; nothing else changes."""
    out = {}
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g6" / f"r{r}.json").read_text(encoding="utf-8"))
        for c, lr in d["loop"].items():
            if lr["status"] != "ok":
                continue
            case = ROOT / "real" / c
            train, exc = _src(case)
            out[(r, c)] = bool(g7.check_split_required(train, exc, ["year", "ptime", "warstds"], lr["final_plan"]))
    assert {k for k, v in out.items() if v} == {(1, "civilwar_apparent"), (2, "civilwar_apparent"), (3, "civilwar_apparent")}


def test_g5_saved_plans_unaffected():
    import g4
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g5" / f"r{r}.json").read_text(encoding="utf-8"))
        for c, lr in d["loop"].items():
            if lr.get("status") == "ok":
                train = (g4.CASES[c] / "train.py").read_text(encoding="utf-8")
                exc = (g4.CASES[c] / "excerpt.md").read_text(encoding="utf-8")
                assert g7.check_split_required(train, exc, ["x"], lr["final_plan"]) == [], (r, c)


def test_replay6_stage_writes_only_to_the_output_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLLAB_G7_OUT", str(tmp_path))
    out = g7.replay6()
    assert (tmp_path / "replay_g6.json").exists()
    assert out["summary"]["g6_would_reject"] == [f"r{r}/civilwar_apparent" for r in (1, 2, 3)]
    assert out["summary"]["g5_would_reject"] == []


# ---------------- probe verdict, B3 copy, prereg ----------------
def test_probe_verdict():
    assert g7.probe_pass("UNKNOWN", "Supply-chain or sensor telemetry")[0] is True
    ok, hits = g7.probe_pass("Muchlinski et al. (2016)", "something")
    assert not ok and "muchlinski" in hits
    ok, hits = g7.probe_pass("UNKNOWN", "Civil war onset covariates")
    assert not ok and "civil" in hits
    assert g7.probe_pass("I recognise it", "factory sensors")[0] is False  # must say UNKNOWN


def test_b3_prompt_is_the_baseline_text():
    from baselines.single_prompt import FACTORIAL_SYSTEM
    assert g7.B3_SYSTEM == FACTORIAL_SYSTEM


def test_planner_prompt_does_not_announce_the_new_rule():
    from agent import factorial_g6
    assert g7.SYSTEM == factorial_g6.SYSTEM
    assert "SPLIT-USE-REQUIRED" not in g7.SYSTEM


def test_prereg_is_write_once(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLLAB_G7_OUT", str(tmp_path))
    g7.rule()
    first = (tmp_path / "PREREG.md").read_text(encoding="utf-8")
    g7.rule(model_note="something else")
    assert (tmp_path / "PREREG.md").read_text(encoding="utf-8") == first
    assert "PASS" in first and "4 of 5" in first.replace(">= 4 of 5", "4 of 5")
    assert len((tmp_path / "prereg_log.jsonl").read_text().splitlines()) == 3


def test_score_stage_counts_a_synthetic_run(tmp_path, monkeypatch):
    """Acceptance arithmetic on hand-made records (no model): 4/5 right direction, 3/5 within tolerance, 0 clean false alarms."""
    monkeypatch.setenv("NULLLAB_G7_OUT", str(tmp_path))

    def stats(infl, lo, hi):
        return {s: {"full": {"acc": {"orig": 0.4, "fix_both": 0.4 - infl}, "drop": {"fix_both": infl}, "drop_ci": {"fix_both": [lo, hi]}}} for s in ("42", "43", "44")}
    plan = {"edits": {"A": {"kind": "split"}, "B": {"kind": "fit_scope"}}, "A": "a", "B": "b", "predicted_drop_pp": {}}
    leaky = [(0.30, 0.2, 0.4), (0.36, 0.2, 0.5), (0.25, 0.1, 0.4), (0.10, 0.05, 0.2), (0.0, -0.1, 0.1)]
    for i, (m, lo, hi) in enumerate(leaky, 1):
        rec = lambda st, fa=None: {"status": "ok", "retries": 0, "stats": st, "final_plan": plan}  # noqa: E731
        (tmp_path / f"r{i}.json").write_text(json.dumps({
            "loop": {"civilwar_disguised": rec(stats(m, lo, hi)), "civilwar_disguised_clean": rec(stats(0.0, -0.05, 0.05))},
            "plan": {"civilwar_disguised": {}, "civilwar_disguised_clean": {}},
            "b3": {"civilwar_disguised": {"ans": {"leak": True, "predicted_drop_pp": {"fix_both": 30}}},
                   "civilwar_disguised_clean": {"ans": {"leak": True, "predicted_drop_pp": {"fix_both": 13}}}}}))
    g7.score()
    acc = json.loads((tmp_path / "score.json").read_text())["acceptance"]
    assert acc["a_direction_right"] == 4 and acc["c_magnitude_within_0.15"] == 3 and acc["b_clean_false_alarms"] == 0
    assert acc["PASS"] is True and acc["b3_gets_it_leaky"] == 5 and acc["b3_false_alarms_clean"] == 5
