"""G5 patch-fidelity guard tests (offline, no live calls; anything written goes to pytest temp dirs)."""
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from agent import factorial_g5, fidelity  # noqa: E402
from eval import g5_fixtures as fx  # noqa: E402

ALL = list(fidelity.KINDS)
SRC = {c: (ROOT / d / c / "train.py").read_text(encoding="utf-8") for d, c in (
    ("corpus", "clean_group_correct"), ("factorial", "comp_visit_history"), ("factorial", "g4_pump_inspection"),
    ("factorial", "g4_freight_delay"), ("factorial", "g4_crop_irrigation"), ("factorial", "g4_assay_replicates"),
    ("factorial", "g4_visit_history_clean"))}


def _structured(case, edits):
    out = {}
    for cfg, info in fidelity.build_configs(SRC[case], edits).items():
        v = list(info["violations"])
        rep = {}
        if not v:
            sv, rep = fidelity.check_static(SRC[case], info["src"], info["kinds"], info["declared"])
            v += sv
        out[cfg] = (v, rep.get("changed"))
    return out


def _legacy(case, patch, kinds=ALL):
    v, _ = fidelity.check_static(SRC[case], patch_src=patch, kinds=kinds)
    return [x for x in v if not x.startswith("STRUCTURE: whole-file")]


# ---------------- the G4 failure, replayed offline ----------------
def test_g4_failing_clean_group_patch_is_rejected():
    p = json.loads((ROOT / "runs_g4" / "plan.json").read_text())["clean_group_correct"]["plan"]["patches"]
    assert _legacy("clean_group_correct", p["fix_B"]) and _legacy("clean_group_correct", p["fix_both"])
    assert any("corrcoef" in v for v in _legacy("clean_group_correct", p["fix_both"]))
    assert _legacy("clean_group_correct", p["fix_A"]) == []          # the group-CV change alone is a declared split fix
    v, _ = fidelity.check_static(SRC["clean_group_correct"], patch_src=p["fix_A"], kinds=ALL)
    assert any(x.startswith("STRUCTURE: whole-file") for x in v)     # and whole-file patches are never accepted live


def test_good_legacy_patches_pass_invariants():
    spike = json.loads((ROOT / "runs_spike4" / "prereg.json").read_text())["loop_plan"]["patches"]
    for cfg, p in spike.items():
        assert _legacy("comp_visit_history", p) == [], cfg
    truth = json.loads((ROOT / "eval" / "factorial_truth_g4.json").read_text())
    for c in ("g4_freight_delay", "g4_pump_inspection", "g4_crop_irrigation", "g4_assay_replicates", "g4_visit_history_clean"):
        for cfg, p in truth[c]["ref_patches"].items():
            assert _legacy(c, p) == [], (c, cfg)


# ---------------- structured edits ----------------
@pytest.mark.parametrize("case,edits", [("comp_visit_history", fx.GOOD_SPIKE), ("g4_pump_inspection", fx.GOOD_PUMP)])
def test_good_structured_edits_accepted_and_local(case, edits):
    r = _structured(case, edits)
    assert all(v == [] for v, _ in r.values()), r
    assert r["fix_A"][1] == sorted(edits["A"]["steps"]) and r["fix_B"][1] == sorted(edits["B"]["steps"])
    assert r["fix_both"][1] == sorted(set(edits["A"]["steps"]) | set(edits["B"]["steps"]))


def test_bad_structured_feature_drop_rejected():
    r = _structured("clean_group_correct", fx.BAD_GROUP_FEATURE_DROP)
    assert r["fix_A"][0] == []
    assert r["fix_B"][0] and r["fix_both"][0]


def test_bad_structured_model_and_sample_size_rejected():
    r = _structured("clean_group_correct", fx.BAD_GROUP_MODEL)
    assert any("MODEL" in v for v in r["fix_A"][0])
    assert any("SAMPLE SIZE" in v for v in r["fix_B"][0])


def test_feature_list_change_needs_feature_kind():
    e = {"A": {"kind": "fit_scope", "steps": {"feats": "def feats(df):\n    return [c for c in df.columns if c not in (TARGET, CARRIER, 'c_x')]\n"}},
         "B": {"kind": "feature", "steps": {"feats": "def feats(df):\n    return [c for c in df.columns if c not in (TARGET, CARRIER, 'c_x')]\n"}},
         "both_overrides": {"feats": "def feats(df):\n    return [c for c in df.columns if c not in (TARGET, CARRIER, 'c_x')]\n"}}
    r = _structured("g4_freight_delay", e)
    assert any("FEATURES" in v for v in r["fix_A"][0]) and r["fix_B"][0] == [] and r["fix_both"][0] == []


def test_split_change_needs_split_kind_but_oof_kfold_is_allowed():
    bad = {"A": {"kind": "fit_scope", "steps": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n"
                                                "    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed + 1)\n"}},
           "B": {"kind": "split", "steps": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n"
                                            "    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed + 1)\n"}},
           "both_overrides": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n"
                                           "    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed + 1)\n"}}
    r = _structured("g4_freight_delay", bad)
    assert any("SPLIT" in v for v in r["fix_A"][0]) and r["fix_B"][0] == []
    r = _structured("comp_visit_history", fx.GOOD_SPIKE)            # fix_A ADDS an out-of-fold KFold under fit_scope
    assert r["fix_A"][0] == []


@pytest.mark.parametrize("edits,needle", [
    ({"A": {"kind": "model", "steps": {"fit_predict": "def fit_predict(Xtr, ytr, Xte, seed):\n    return Xte[:, 0] > 0\n"}},
      "B": {"kind": "split", "steps": {}}}, "kind 'model'"),
    ({"A": {"kind": "fit_scope", "steps": {"load": "def load(path='data.csv'):\n    return None\n"}},
      "B": {"kind": "split", "steps": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n    return 1\n"}}}, "data loading"),
    ({"A": {"kind": "fit_scope", "steps": {"impute": "def other(Xtr, Xte):\n    return Xtr, Xte\n"}},
      "B": {"kind": "split", "steps": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n    return 1\n"}}}, "exactly one top-level def"),
    ({"A": {"kind": "fit_scope", "steps": {"impute": "import os\ndef impute(Xtr, Xte):\n    return Xtr, Xte\n"}},
      "B": {"kind": "split", "steps": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n    return 1\n"}}}, "imports 'os'"),
    ({"A": {"kind": "fit_scope", "steps": {"impute": "def impute(Xtr, Xte):\n    med = Xtr.median()\n    return Xtr.fillna(med), Xte.fillna(0)\n"}},
      "B": {"kind": "split", "steps": {"split_idx": "def split_idx(df, seed, test_size=0.25):\n    return 1\n"}}}, "unchanged"),
    ({"A": {"kind": "fit_scope", "steps": {"impute": "def impute(Xtr, Xte):\n    return Xtr, Xte\n"}},
      "B": {"kind": "fit_scope", "steps": {"impute": "def impute(Xtr, Xte):\n    return Xtr, Xte.fillna(1)\n"}}}, "both_overrides"),
])
def test_structure_violations(edits, needle):
    r = _structured("g4_freight_delay", edits)
    assert any(needle in v for vs, _ in r.values() for v in vs), r


def test_runtime_sample_size_check():
    raw = {"seeds": {"42": {"orig": {"y": [0] * 10}, "fix_A": {"y": [0] * 10}, "fix_B": {"y": [0] * 7}, "fix_both": {"y": [0] * 7}}}}
    v = fidelity.check_runtime(raw, {"fix_A": ["fit_scope"], "fix_B": ["fit_scope"], "fix_both": ["fit_scope", "split"]})
    assert len(v) == 1 and "fix_B" in v[0]


# ---------------- Recover: one retry, then INCONCLUSIVE (never FALSIFIED) ----------------
def test_recover_then_inconclusive(monkeypatch, tmp_path):
    import g5
    monkeypatch.setattr(g5, "OUT", tmp_path)
    monkeypatch.setattr(g5, "_budget_ok", lambda usd: True)
    calls = []

    def fake_retry(case_dir, rid, prev, problems):
        calls.append(problems)
        return {"edits": fx.BAD_GROUP_FEATURE_DROP, "prereg_sha256": "x"}, "{}"
    monkeypatch.setattr(factorial_g5, "retry", fake_retry)
    monkeypatch.setattr(g5, "_execute", lambda *a: pytest.fail("a rejected patch must never execute"))
    rec = g5.loop_case("clean_group_correct", "test", {"plan": {"edits": fx.BAD_GROUP_FEATURE_DROP, "prereg_sha256": "x"}})
    assert rec["status"] == "INCONCLUSIVE" and rec["retries"] == 1 and len(calls) == 1
    assert any("corrcoef" in p for p in calls[0])
    assert [e["phase"].split(" ")[0] for e in rec["log"]] == ["Plan", "Verify", "Recover", "Verify", "Report"]


def test_recover_accepts_a_fixed_retry(monkeypatch, tmp_path):
    import g5
    monkeypatch.setattr(g5, "OUT", tmp_path)
    monkeypatch.setattr(g5, "_budget_ok", lambda usd: True)
    bad = {"A": fx.GOOD_PUMP["A"], "B": {"kind": "feature", "steps": {"fit_predict": fx.BAD_GROUP_MODEL["A"]["steps"]["fit_predict"]}}}
    monkeypatch.setattr(factorial_g5, "retry", lambda *a: ({"edits": fx.GOOD_PUMP, "prereg_sha256": "y"}, "{}"))
    rec = g5.loop_case("g4_pump_inspection", "test", {"plan": {"edits": bad, "prereg_sha256": "x"}})
    assert rec["status"] == "ok" and rec["retries"] == 1
    assert rec["fidelity"]["fix_B"].startswith("only step(s) add_lag changed")
