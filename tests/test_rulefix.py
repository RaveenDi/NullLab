"""EVAL-8 tests: the no-LLM rule-based baseline. Offline, deterministic, no live call. Scratch data only for the mechanics tests
(random numbers, never a benchmark measurement); anything written goes to pytest temp dirs, never to runs*/."""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from baselines import rulefix  # noqa: E402
from eval import run_rulefix as rr  # noqa: E402

EXPECTED_FIRED = {  # label-free detection on the repository cases (also recorded in runs_rulefix/PREREG.md)
    "g4_freight_delay": {"R3"}, "g4_pump_inspection": {"R2", "R3"}, "g4_crop_irrigation": {"R2"}, "g4_assay_replicates": {"R3"},
    "clean_control": set(), "clean_group_correct": set(), "clean_wine_correct": set(), "g4_visit_history_clean": set(),
    "civilwar_apparent": {"R1", "R4"}, "civilwar_temporal_clean": set(), "esl_selection": {"R2"}, "esl_selection_clean": set(),
}


def _case(name):
    return ROOT / rr.CASES[name][0]


@pytest.mark.parametrize("name", list(EXPECTED_FIRED))
def test_detection_on_repository_cases(name):
    d = _case(name)
    if not (d / "data.csv").exists():
        pytest.skip("raw data is not in the repository")
    det = rulefix.detect(d)
    assert set(det["fired"]) == EXPECTED_FIRED[name], det


def test_spec_hash_is_stable_and_complete():
    assert rulefix.spec_sha256() == rulefix.spec_sha256()
    assert set(rulefix.spec()["rules"]) == {"R1", "R2", "R3", "R4", "R5"}
    assert rulefix.FACTOR_A + rulefix.FACTOR_B == ("R1", "R3", "R4", "R5", "R2")


def test_generated_sources_compile_for_every_available_case():
    for name in rr.CASES:
        d = _case(name)
        if not (d / "data.csv").exists():
            continue
        b = rulefix.build_configs(d)
        for cfg, v in b["configs"].items():
            compile(v["src"], f"{name}/{cfg}", "exec")
        assert b["configs"]["fix_both"]["rules_applied"] or not b["det"]["fired"] or b["det"]["not_applied"]


def test_no_rule_fires_means_fix_equals_claim():
    d = _case("clean_group_correct")
    if not (d / "data.csv").exists():
        pytest.skip("no data")
    b = rulefix.build_configs(d)
    assert b["det"]["fired"] == {}
    for v in b["configs"].values():
        assert v["steps"] == [] and v["rules_applied"] == []


# ---------------- mechanics on scratch data ----------------
def _write_case(tmp_path, name, train_src, df):
    d = tmp_path / name
    d.mkdir()
    (d / "train.py").write_text(train_src, encoding="utf-8")
    (d / "excerpt.md").write_text("## Results\nScratch case.\n", encoding="utf-8")
    df.to_csv(d / "data.csv", index=False)
    return d


def _exec(src):
    ns = {}
    exec(compile(src, "<fix>", "exec"), ns)
    return ns


def _scratch_esl(tmp_path, n=40, p=1000, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, p)), columns=[f"g{i:04d}" for i in range(p)])
    df["label"] = np.repeat([0, 1], n // 2)
    src = (ROOT / "real" / "esl_selection" / "train.py").read_text(encoding="utf-8")
    return _write_case(tmp_path, "esl_scratch", src, df)


def test_r2_hoist_moves_selection_inside_each_fold_and_equals_the_clean_variant(tmp_path):
    d = _scratch_esl(tmp_path)
    det = rulefix.detect(d)
    assert set(det["fired"]) == {"R2"} and det["fired"]["R2"]["mode"] == "hoist"
    b = rulefix.build_configs(d)
    both = b["configs"]["fix_both"]["src"]
    assert "_rf_keep" in both and "keep = screen(X, y)" not in both
    assert b["configs"]["fix_A"]["steps"] == []                       # R2 is the fit-scope factor only
    assert b["configs"]["fix_B"]["src"] == both                         # only R2 fired
    df = pd.read_csv(d / "data.csv")
    clean_src = (ROOT / "real" / "esl_selection_clean" / "train.py").read_text(encoding="utf-8")
    clean_ns, fix_ns, orig_ns = _exec(clean_src), _exec(both), _exec((d / "train.py").read_text(encoding="utf-8"))
    for seed in (1, 2):
        y_c, p_c = clean_ns["claimed_eval"](df, seed)
        y_f, p_f = fix_ns["controlled_eval"](df, seed)
        assert np.array_equal(y_c, y_f) and np.array_equal(p_c, p_f)   # identical to the hand-written correct protocol
        y_o, p_o = orig_ns["claimed_eval"](df, seed)
        assert (y_o == p_o).mean() > (y_f == p_f).mean() + 0.15          # the leaky screen is inflated on pure noise


def test_r2_scope_fits_transformers_on_the_training_rows_only(tmp_path):
    rng = np.random.default_rng(1)
    cols = [f"f{i}" for i in range(10)]
    df = pd.DataFrame(rng.normal(size=(400, 10)), columns=cols)
    df["y"] = rng.integers(0, 2, 400)
    src = (ROOT / "factorial" / "g4_crop_irrigation" / "train.py").read_text(encoding="utf-8").replace("c_4efd62", "y")
    d = _write_case(tmp_path, "crop_scratch", src, df)
    b = rulefix.build_configs(d)
    assert b["det"]["fired"]["R2"]["mode"] == "scope"
    ns = _exec(b["configs"]["fix_both"]["src"])
    S = ns["StandardScaler"]
    X = rng.normal(size=(400, 3))
    X[100:] += 10.0
    ns["_RF"].update(rows=np.arange(100), n=400)
    assert np.allclose(S().fit(X).mean_, X[:100].mean(0))
    ns["_RF"]["rows"] = None
    assert np.allclose(S().fit(X).mean_, X.mean(0))
    ns["_RF"].update(rows=np.arange(100), n=999)                          # a frame of another length is not rescoped
    assert np.allclose(S().fit(X).mean_, X.mean(0))
    y, p = ns["controlled_eval"](df, 3)
    assert len(y) == len(p) == 100


_MINI = '''import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

TARGET = "y"
METRIC = "accuracy"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c not in (TARGET, "year", "grp")]


def split_rows(df, seed):
    idx = np.arange(len(df))
    return idx, idx


def claimed_eval(df, seed):
    tr, te = split_rows(df, seed)
    f = feats(df)
    m = LogisticRegression(max_iter=500).fit(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr])
    return df[TARGET].to_numpy()[te], m.predict(df[f].to_numpy()[te])
'''


def _mini_df(n=300, dup=0, seed=0):
    rng = np.random.default_rng(seed)
    df = pd.DataFrame(rng.normal(size=(n, 4)), columns=list("abcd"))
    df["year"] = np.sort(rng.integers(1990, 2010, n))
    df["grp"] = rng.integers(0, 60, n)
    df["y"] = rng.integers(0, 2, n)
    return pd.concat([df, df.iloc[:dup]], ignore_index=True) if dup else df


def test_r1_r4_fire_on_in_sample_scoring_and_temporal_wins(tmp_path):
    d = _write_case(tmp_path, "mini", _MINI, _mini_df())
    det = rulefix.detect(d)
    assert set(det["fired"]) == {"R1", "R3", "R4"}, det               # grp is metadata, repeats, year is the time column
    b = rulefix.build_configs(d)
    assert b["configs"]["fix_both"]["rules_applied"] == ["R4", "R3", "R1"]
    assert any("precedence" in n for n in b["configs"]["fix_both"]["notes"])
    ns = _exec(b["configs"]["fix_both"]["src"])
    df = pd.read_csv(d / "data.csv")
    tr, te = ns["split_rows"](df, 0)
    assert df["year"].to_numpy()[tr].max() <= df["year"].to_numpy()[te].min() and len(te) == 75 and not set(tr) & set(te)
    y, p = ns["controlled_eval"](df, 0)
    assert len(y) == 75


def test_r1_alone_is_a_stratified_random_holdout(tmp_path):
    df = _mini_df().drop(columns=["year", "grp"])
    d = _write_case(tmp_path, "mini_r1", _MINI.replace(', "year", "grp"', ""), df)
    b = rulefix.build_configs(d)
    assert set(b["det"]["fired"]) == {"R1"}
    ns = _exec(b["configs"]["fix_A"]["src"])
    tr, te = ns["split_rows"](pd.read_csv(d / "data.csv"), 5)
    assert not set(tr) & set(te) and len(te) == 75
    tr2, te2 = ns["split_rows"](pd.read_csv(d / "data.csv"), 5)
    assert np.array_equal(te, te2)                                      # deterministic given the seed


def test_r5_drops_exact_duplicates_and_changes_n(tmp_path):
    src = _MINI.replace("tr, te = split_rows(df, seed)", "tr, te = split_rows(df, seed)").replace(
        "    idx = np.arange(len(df))\n    return idx, idx",
        "    from sklearn.model_selection import train_test_split\n    return train_test_split(np.arange(len(df)), test_size=0.25, random_state=seed)")
    d = _write_case(tmp_path, "dups", src, _mini_df(n=200, dup=50).drop(columns=["year", "grp"]))
    src = (d / "train.py").read_text().replace(', "year", "grp"', "")
    (d / "train.py").write_text(src, encoding="utf-8")
    det = rulefix.detect(d)
    assert det["fired"] == {"R5": {"duplicate_rows": 50}}
    ns = _exec(rulefix.build_configs(d)["configs"]["fix_both"]["src"])
    y, p = ns["controlled_eval"](pd.read_csv(d / "data.csv"), 0)
    assert len(y) == 50                                                  # 200 unique rows, 25% test


def test_group_split_detected_when_ids_repeat_and_not_when_split_is_already_grouped(tmp_path):
    rng = np.random.default_rng(3)
    df = pd.DataFrame(rng.normal(size=(500, 3)), columns=list("abc"))
    df["grp"] = np.repeat(np.arange(100), 5)
    df["y"] = rng.integers(0, 2, 500)
    base = _MINI.replace(', "year"', "").replace(
        "    idx = np.arange(len(df))\n    return idx, idx",
        "    from sklearn.model_selection import train_test_split\n    return train_test_split(np.arange(len(df)), test_size=0.25, random_state=seed)")
    d = _write_case(tmp_path, "grp", base, df)
    det = rulefix.detect(d)
    assert set(det["fired"]) == {"R3"} and det["fired"]["R3"]["column"] == "grp"
    ns = _exec(rulefix.build_configs(d)["configs"]["fix_both"]["src"])
    g = pd.read_csv(d / "data.csv")["grp"].to_numpy()
    tr, te = ns["split_rows"](pd.read_csv(d / "data.csv"), 0)
    assert not set(g[tr]) & set(g[te])
    grouped = base.replace("return train_test_split(np.arange(len(df)), test_size=0.25, random_state=seed)",
                           "from sklearn.model_selection import GroupShuffleSplit\n    return next(GroupShuffleSplit(1, test_size=0.25, random_state=seed).split(df, groups=df['grp']))")
    d2 = _write_case(tmp_path, "grp_ok", grouped, df)
    assert rulefix.detect(d2)["fired"] == {}


def test_end_to_end_run_case_writes_only_to_the_temp_dir(tmp_path):
    d = _write_case(tmp_path, "mini_e2e", _MINI.replace(', "year", "grp"', ""), _mini_df(n=200).drop(columns=["year", "grp"]))
    rec = rr.run_case(d, seeds=(1, 2), n_boot=40, timeout=300)
    assert rec["status"] == "ok", rec.get("stderr")
    import g4
    sign, cats = g4.case_sign(rec["stats"])
    assert sign in ("+", "0", "-", "mixed") and len(cats) == 2
    row = rr._row(rec)
    assert row["status"] == "ok" and row["fired"] == ["R1"] and row["n_fix_both"]["1"] == 50
    assert row["n_orig"]["1"] == 200


def test_prereg_is_never_overwritten_and_run_needs_it(tmp_path):
    out = tmp_path / "pre"
    with pytest.raises(SystemExit):
        rr.main(["run", "--out", str(out), "--cases", "clean_wine_correct"])   # no PREREG.md yet
    rr.main(["prereg", "--out", str(out), "--cases", "clean_wine_correct"])
    assert (out / "PREREG.md").exists() and (out / "PREREG.sha256").exists()
    txt = (out / "PREREG.md").read_text(encoding="utf-8")
    assert rulefix.spec_sha256() in txt and "COMPARISON RULE" in txt
    with pytest.raises(SystemExit):
        rr.main(["prereg", "--out", str(out), "--cases", "clean_wine_correct"])
    log = [json.loads(x) for x in (out / "prereg_log.jsonl").read_text().splitlines()]
    assert log[0]["kind"] == "rulefix_prereg"
