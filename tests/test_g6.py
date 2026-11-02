"""G6 tests: tightened guard (justification rules, feats inline), score-metric statistics, real/textbook case isolation.
Offline, no live calls; anything written goes to pytest temp dirs."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from agent import factorial, fidelity  # noqa: E402
from eval import g5_fixtures as fx  # noqa: E402
from sandbox import executor, factorial_stats  # noqa: E402

G4 = {c: ROOT / ("corpus" if c.startswith("clean_") and c != "g4_visit_history_clean" else "factorial") / c for c in (
    "g4_freight_delay", "g4_pump_inspection", "g4_crop_irrigation", "g4_assay_replicates", "clean_control",
    "clean_group_correct", "clean_wine_correct", "g4_visit_history_clean")}
REAL = {c: ROOT / "real" / c for c in ("civilwar_apparent", "civilwar_temporal_clean", "esl_selection", "esl_selection_clean")}

needs_real = pytest.mark.skipif(not all((d / "data.csv").exists() for d in REAL.values()),
                                reason="raw real data is not in the repository; rebuild it with eval/build_g6.py")


def _files(d):
    return ((d / "train.py").read_text(encoding="utf-8"), (d / "excerpt.md").read_text(encoding="utf-8"),
            (d / "data.csv").open(encoding="utf-8").readline().strip().split(","))


def _full(case_dir, plan):
    src, exc, hdr = _files(case_dir)
    v = fidelity.check_justification(src, exc, hdr, plan)
    for info in fidelity.build_configs(src, plan["edits"]).values():
        v += info["violations"] or fidelity.check_static(src, info["src"], info["kinds"], info["declared"])[0]
    return v


def _g5_plans():
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g5" / f"r{r}.json").read_text())
        for c, lr in d["loop"].items():
            if lr["status"] == "ok":
                yield r, c, lr["final_plan"]


# ---------------- tightened guard ----------------
def test_g5_hard_case_patches_still_accepted():
    n = 0
    for r, c, plan in _g5_plans():
        if c.startswith("g4_") and c != "g4_visit_history_clean":
            assert _full(G4[c], plan) == [], (r, c)
            n += 1
    assert n == 11  # every executed hard-case plan of G5 (crop r1 was INCONCLUSIVE)


def test_g5_visit_clean_patches_still_accepted():
    for r, c, plan in _g5_plans():
        if c == "g4_visit_history_clean":
            assert _full(G4[c], plan) == [], r


def test_wine_r2_false_alarm_now_rejected():
    plan = json.loads((ROOT / "runs_g5" / "r2.json").read_text())["loop"]["clean_wine_correct"]["final_plan"]
    v = _full(G4["clean_wine_correct"], plan)
    assert any(x.startswith("FEATURE-REASON") and "c_55565a" in x for x in v)
    assert any(x.startswith("SPLIT-USE") for x in v)


def test_unjustified_named_column_drops_rejected_on_all_clean_cases():
    for r, c, plan in _g5_plans():
        if c in ("clean_group_correct", "clean_wine_correct") or (c == "clean_control" and r > 1):
            assert any(x.startswith("FEATURE-REASON") for x in _full(G4[c], plan)), (r, c)


def test_structured_good_fixtures_still_accepted():
    for name, case in (("GOOD_SPIKE", "comp_visit_history"), ("GOOD_PUMP", "g4_pump_inspection")):
        d = ROOT / "factorial" / case
        assert _full(d, {"edits": getattr(fx, name)}) == [], name


def test_cited_column_drop_accepted():
    src = ("import pandas as pd\nTARGET = 'y'\n\ndef load(path='data.csv'):\n    return pd.read_csv(path)\n\n"
           "def feats(df):\n    return [c for c in df.columns if c != TARGET]  # c_bbbbbb is recorded after the outcome\n\n"
           "def claimed_eval(df, seed):\n    return df[TARGET].to_numpy(), df[TARGET].to_numpy()\n")
    new = "def feats(df):\n    return [c for c in df.columns if c not in (TARGET, 'c_bbbbbb')]\n"
    plan = {"edits": {"A": {"kind": "feature", "steps": {"feats": new}}},
            "A_code_line": "    return [c for c in df.columns if c != TARGET]  # c_bbbbbb is recorded after the outcome"}
    assert fidelity.check_justification(src, "excerpt", ["c_aaaaaa", "c_bbbbbb", "y"], plan) == []
    plan["A_code_line"] = "    return [c for c in df.columns if c != TARGET]"
    assert fidelity.check_justification(src, "excerpt", ["c_aaaaaa", "c_bbbbbb", "y"], plan)
    plan["A_code_line"] = "c_bbbbbb is a leak (invented, not in the files)"
    assert fidelity.check_justification(src, "excerpt", ["c_aaaaaa", "c_bbbbbb", "y"], plan)


@needs_real
def test_ordered_split_needs_temporal_claim():
    fix = ("def split_rows(df, seed):\n    idx = np.arange(len(df))\n"
           "    return idx[df['year'].to_numpy() < 1990], idx[df['year'].to_numpy() >= 1990]\n")
    plan = {"edits": {"A": {"kind": "split", "steps": {"split_rows": fix}}, "B": {"kind": "fit_scope", "steps": {}}}}
    src, exc, hdr = _files(REAL["civilwar_apparent"])
    assert fidelity.check_justification(src, exc, hdr, plan) == []          # excerpt: 'forecast ...'
    v = fidelity.check_justification(src, "We report accuracy on held-out rows.", hdr, plan)
    assert v and v[0].startswith("SPLIT-USE")


def test_verbatim_feats_inline_no_longer_rejected():
    d = G4["clean_wine_correct"]
    src = (d / "train.py").read_text(encoding="utf-8")
    new = ("def claimed_eval(df, seed, groups=None):\n    tr, te = split_idx(df, seed, groups)\n"
           "    f = [c for c in df.columns if c != TARGET]\n"
           "    return df[TARGET].to_numpy()[te], fit_predict(df[f].iloc[tr], df[TARGET].iloc[tr], df[f].iloc[te], seed + 1)\n")
    cfg = fidelity.build_configs(src, {"A": {"kind": "fit_scope", "steps": {"claimed_eval": new}},
                                       "B": {"kind": "fit_scope", "steps": {"claimed_eval": new}},
                                       "both_overrides": {"claimed_eval": new}})["fix_A"]
    v, _ = fidelity.check_static(src, cfg["src"], cfg["kinds"], cfg["declared"])
    assert not [x for x in v if x.startswith("FEATURES")], v


def test_feature_filter_change_still_rejected_without_feature_kind():
    d = G4["clean_wine_correct"]
    src = (d / "train.py").read_text(encoding="utf-8")
    new = ("def claimed_eval(df, seed, groups=None):\n    tr, te = split_idx(df, seed, groups)\n"
           "    f = [c for c in df.columns if c != TARGET and c != 'c_55565a']\n"
           "    return df[TARGET].to_numpy()[te], fit_predict(df[f].iloc[tr], df[TARGET].iloc[tr], df[f].iloc[te], seed)\n")
    cfg = fidelity.build_configs(src, {"A": {"kind": "fit_scope", "steps": {"claimed_eval": new}},
                                       "B": {"kind": "fit_scope", "steps": {"claimed_eval": new}},
                                       "both_overrides": {"claimed_eval": new}})["fix_A"]
    v, _ = fidelity.check_static(src, cfg["src"], cfg["kinds"], cfg["declared"])
    assert any(x.startswith("FEATURES") for x in v)


# ---------------- score metric + sandbox ----------------
def test_score_metric_bootstrap_known():
    y = np.r_[np.zeros(90, int), np.ones(10, int)]
    perfect = np.r_[np.zeros(90), np.ones(10)]
    rnd = np.random.default_rng(0).random(100)
    res = {"orig": {"y": y, "p": perfect}, "fix_A": {"y": y, "p": rnd}, "fix_B": {"y": y, "p": perfect},
           "fix_both": {"y": y, "p": rnd}}
    st = factorial_stats.score_factorial_stats(res, "pr_auc", n_boot=200, seed=1)
    assert st["acc"]["orig"] == 1.0 and st["drop"]["fix_B"] == 0.0 and st["drop"]["fix_both"] > 0.6 and st["drop_ci"]["fix_both"][0] > 0.3


def test_accuracy_path_unchanged():
    res = {k: {"y": [0, 1, 1, 0], "p": [0, 1, 0, 0]} for k in factorial_stats.CONFIGS}
    a = factorial_stats.all_seeds({"seeds": {"42": res}}, n_boot=50)
    assert set(a["42"]) == {"full", "same_n"} and a["42"]["full"]["acc"]["orig"] == 0.75


def test_sandbox_keeps_scores_for_score_metric(tmp_path):
    rng = np.random.default_rng(3)
    (tmp_path / "data.csv").write_text("x,y\n" + "\n".join(f"{v:.4f},{int(v > 0.7)}" for v in rng.random(60)))
    (tmp_path / "train.py").write_text(
        "import pandas as pd\nMETRIC = 'pr_auc'\n\ndef load(path='data.csv'):\n    return pd.read_csv(path)\n\n"
        "def claimed_eval(df, seed):\n    return df['y'].to_numpy(), df['x'].to_numpy()\n")
    (tmp_path / "excerpt.md").write_text("x")
    ok = "import train\n\ndef controlled_eval(df, seed):\n    return df['y'].to_numpy(), 1 - df['x'].to_numpy()\n"
    r = executor.run_factorial(tmp_path, {"fix_A": ok, "fix_B": ok, "fix_both": ok}, seeds=(42,), timeout=120)
    assert r["status"] == "ok" and r["result"]["metric"] == "pr_auc"
    assert isinstance(r["result"]["seeds"]["42"]["orig"]["p"][0], float)
    st = factorial_stats.all_seeds(r["result"], n_boot=50)["42"]
    assert st["full"]["acc"]["orig"] == 1.0 and st["full"]["drop"]["fix_both"] > 0.5


def test_sandbox_blocks_g6_truth(tmp_path):
    gt = ROOT / "eval" / "g6_truth.json"
    (tmp_path / "data.csv").write_text("x,y\n0.1,0\n0.9,1\n")
    (tmp_path / "train.py").write_text("import pandas as pd\n\ndef load(path='data.csv'):\n    return pd.read_csv(path)\n\n"
                                       "def claimed_eval(df, seed):\n    return df['y'].to_numpy(), df['y'].to_numpy()\n")
    bad = f"def controlled_eval(df, seed):\n    return open(r'{gt}').read()\n"
    r = executor.run_factorial(tmp_path, {"fix_A": bad, "fix_B": bad, "fix_both": bad}, seeds=(42,), timeout=120)
    assert r["status"] == "error" and "PermissionError" in r["stderr"]


# ---------------- real / textbook cases ----------------
@needs_real
def test_real_case_agent_views_isolated():
    for c, d in REAL.items():
        assert sorted(p.name for p in d.iterdir() if p.name != "__pycache__") == ["data.csv", "excerpt.md", "train.py"], c
        view = factorial.agent_view(d)
        assert "g6_truth" not in view and "Neunhoeffer" not in view and "Muchlinski" not in view and "Hastie" not in view
        assert len(view) < 30000, (c, len(view))   # the 5001-column ESL head is clipped
    truth = json.loads((ROOT / "eval" / "g6_truth.json").read_text())
    assert truth["civilwar_apparent"]["provenance"] == "REAL-PINNED" and truth["esl_selection"]["provenance"] == "TEXTBOOK"


def test_agent_view_unchanged_for_earlier_cases():
    for d in list(G4.values()) + [ROOT / "corpus" / "leak_prescale"]:
        head = "\n".join((d / "data.csv").read_text(encoding="utf-8").splitlines()[:6])
        assert head in factorial.agent_view(d)
