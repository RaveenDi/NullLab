"""G9 typed edit DSL + contract tests (offline, no model calls, no network, no execution of model-written code)."""
import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import contract_g9 as ct, edit_dsl as d  # noqa: E402


def src(c):
    return (ROOT / "real" / c / "train.py").read_text(encoding="utf-8")


EHG, EHGC, CW, CWC, ESL, ESLC = (src(c) for c in ("ehg_disguised", "ehg_disguised_clean", "civilwar_disguised", "civilwar_disguised_clean", "esl_selection", "esl_selection_clean"))
MOVE = {"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}


def test_frozen_op_list():
    assert d.OPS == ("move_into_fold", "drop_from_eval", "replace_split", "retrain_inside")
    assert len(d.spec_sha256()) == 64 and d.spec_sha256() == d.spec_sha256()
    assert d.KINDS == ("random", "group", "temporal")


def test_move_into_fold_ehg_moves_resampler_into_loop():
    s = d.compile_ops(EHG, [MOVE])
    tree = ast.parse(s)
    ce = d.defs_of(tree)["claimed_eval"]
    assert not d.calls_in(ce, "oversample")
    cv = d.defs_of(tree)["cv_scores"]
    loop = next(n for n in ast.walk(cv) if isinstance(n, ast.For))
    assert d.calls_in(loop, "oversample")
    assert "RandomForestClassifier(n_estimators=N_TREES, random_state=seed)" in s  # model constructor untouched
    assert ast.unparse(d.defs_of(ast.parse(EHG))["oversample"]) == ast.unparse(d.defs_of(tree)["oversample"])


def test_drop_from_eval_ehg():
    s = d.compile_ops(EHG, [{"op": "drop_from_eval", "step": "claimed_eval", "call": "oversample"}])
    assert "oversample(X, y, seed)" not in s.split("def claimed_eval")[1]


def test_move_on_clean_pipeline_is_not_applicable_not_a_crash():
    with pytest.raises(d.OpError) as e:
        d.compile_ops(EHGC, [MOVE])
    assert e.value.code == "NOT_APPLICABLE"


def test_move_into_fold_selector_shape_esl():
    s = d.compile_ops(ESL, [{"op": "move_into_fold", "step": "claimed_eval", "call": "screen"}])
    assert "_g9_k = screen(X[tr], y[tr])" in s and "X[tr][:, _g9_k]" in s and "cv_predict(X, y, seed)" in s


TRANSFORMER = """
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
TARGET = "t"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return [c for c in df.columns if c != TARGET]
def fit_eval(X, y, seed):
    tr, te = train_test_split(np.arange(len(y)), test_size=0.25, random_state=seed)
    m = LogisticRegression(max_iter=500).fit(X[tr], y[tr])
    return y[te], m.predict_proba(X[te])[:, 1]
def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    Z = StandardScaler().fit_transform(X)
    return fit_eval(Z, y, seed)
"""


def test_transformer_shape_and_drop_refusal():
    s = d.compile_ops(TRANSFORMER, [{"op": "move_into_fold", "step": "claimed_eval", "call": "StandardScaler"}])
    assert "_g9_t = StandardScaler().fit(X[tr])" in s and "_g9_t.transform(X[te])" in s
    with pytest.raises(d.OpError) as e:
        d.compile_ops(TRANSFORMER, [{"op": "drop_from_eval", "step": "claimed_eval", "call": "StandardScaler"}])
    assert e.value.code == "PRECONDITION"


def test_compiled_transformer_runs():
    import numpy as np
    import pandas as pd
    s = d.compile_ops(TRANSFORMER, [{"op": "move_into_fold", "step": "claimed_eval", "call": "StandardScaler"}])
    ns = {}
    exec(compile(s, "x", "exec"), ns)
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.normal(size=(120, 4)), columns=list("abcd"))
    df["t"] = (df["a"] + rng.normal(size=120) > 0).astype(int)
    yt, p = ns["claimed_eval"](df, 1)
    assert len(yt) == 30 == len(p)


def test_replace_split_hold_out_step_templates():
    for kind, col in (("random", None), ("temporal", "epoch"), ("group", "epoch")):
        s = d.compile_ops(CW, [{"op": "replace_split", "step": "split_rows", "kind": kind, "col": col}])
        assert f"_g9_holdout(len(df), '{kind}'" in s
    s = d.compile_ops(CW, [{"op": "replace_split", "step": "tune_mtry", "kind": "temporal", "col": "epoch"}])
    assert "_G9TSS(n_splits=k)" in s and "StratifiedKFold" not in s.split("def tune_mtry")[1].split("def ")[0]


def test_replace_split_group_in_cv_without_groups_is_not_applicable():
    with pytest.raises(d.OpError) as e:
        d.compile_ops(CW, [{"op": "replace_split", "step": "tune_mtry", "kind": "group", "col": "epoch"}])
    assert e.value.code == "NOT_APPLICABLE"


def test_holdout_helper_semantics():
    import numpy as np
    ns = {}
    exec(compile(d.HELPERS, "h", "exec"), ns)
    h = ns["_g9_holdout"]
    t = np.repeat(np.arange(1, 11), 10)
    tr, te = h(100, "temporal", 0, 0.2, t)
    assert t[tr].max() < t[te].min() and len(te) == 20
    tr, te = h(100, "random", 0, 0.2)
    assert not set(tr) & set(te) and len(te) == 20
    g = np.repeat(np.arange(20), 5)
    tr, te = h(100, "group", 0, 0.2, g)
    assert not set(g[tr]) & set(g[te])


RETRAIN = """
import numpy as np
from sklearn.model_selection import KFold
from sklearn.linear_model import LogisticRegression
def claimed_eval(df, seed):
    X = df.iloc[:, :-1].to_numpy()
    y = df.iloc[:, -1].to_numpy()
    m = LogisticRegression(max_iter=300)
    m.fit(X, y)
    out = np.zeros(len(y))
    for tr, te in KFold(5, shuffle=True, random_state=seed).split(X):
        out[te] = m.predict_proba(X[te])[:, 1]
    return y, out
"""


def test_retrain_inside():
    s = d.compile_ops(RETRAIN, [{"op": "retrain_inside", "step": "claimed_eval"}])
    assert "m.fit(_g9_take(X, tr), _g9_take(y, tr))" in s and "def _g9_take" in s
    with pytest.raises(d.OpError):
        d.compile_ops(EHG, [{"op": "retrain_inside", "step": "claimed_eval"}])


@pytest.mark.parametrize("op,code", [
    ({"op": "mutate_model", "step": "claimed_eval"}, "UNKNOWN_OP"),
    ({"op": "move_into_fold", "step": "nope", "call": "oversample"}, "NO_SUCH_STEP"),
    ({"op": "move_into_fold", "step": "load", "call": "x"}, "NO_SUCH_STEP"),
    ({"op": "replace_split", "step": "split_rows", "kind": "grouped", "col": "a"}, "BAD_PARAM"),
    ({"op": "replace_split", "step": "split_rows", "kind": "temporal"}, "BAD_PARAM"),
    ({"op": "move_into_fold", "step": "claimed_eval", "call": "oversample", "code": "import os"}, "BAD_PARAM"),
])
def test_bad_ops_are_errors_not_crashes(op, code):
    with pytest.raises(d.OpError) as e:
        d.compile_ops(CW if op.get("step") == "split_rows" else EHG, [op])
    assert e.value.code == code


def test_plan_layout_one_factor_vs_factorial():
    p1 = {"factors": [{"id": "A", "ops": [MOVE]}]}
    c1 = d.compile_plan(EHG, p1)
    assert c1["layout"] == "single" and list(c1["configs"]) == ["fix_all"]
    p2 = {"factors": [{"id": "A", "ops": [MOVE]}, {"id": "B", "ops": [{"op": "replace_split", "step": "cv_scores", "kind": "random", "col": None}]}]}
    c2 = d.compile_plan(EHG, p2)
    assert c2["layout"] == "factorial" and set(c2["configs"]) == {"fix_A", "fix_B", "fix_all"}
    assert d.legacy_sources(c1)["fix_A"] == d.legacy_sources(c1)["fix_both"]
    assert set(d.legacy_sources(c2)) == {"fix_A", "fix_B", "fix_both"}


# ---------------- contract ----------------
def _plan(*ops, k=1, ranking=None):
    facs = [{"id": "ABCD"[i], "flaw": "f", "evidence_line": "e", "ops": [o]} for i, o in enumerate(ops)]
    pd_ = {"fix_all": 40} if k == 1 else {**{f"fix_{f['id']}": 20 for f in facs}, "fix_all": 40}
    return {"verdict": "flaw", "factors": facs, "predicted_drop_pp": pd_, "culprit_ranking": ranking or (["A"] if k == 1 else ["A", "interaction"]), "reason": "r"}


def test_contract_text_lists_every_rule_and_op():
    t = ct.contract_text()
    for o in d.OPS:
        assert o in t
    for rid, _ in ct.RULES:
        assert f"[{rid}]" in t
    assert d.spec_sha256() in t and "no_flaw" in t


def test_forecast_words_equal_g7():
    from agent import factorial_g7 as g7
    assert ct.FORECAST_WORDS == g7.FORECAST_WORDS


def test_check_plan_accepts_known_correct_ehg_and_civilwar():
    assert ct.check_plan(_plan(MOVE), ROOT / "real" / "ehg_disguised")["ok"]
    assert ct.check_plan(_plan({"op": "drop_from_eval", "step": "claimed_eval", "call": "oversample"}), ROOT / "real" / "ehg_disguised")["ok"]
    r = ct.check_plan(_plan({"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "epoch"}), ROOT / "real" / "civilwar_disguised")
    assert r["ok"] and r["layout"] == "single", r


def test_check_plan_rules_fire():
    cwd = ROOT / "real" / "civilwar_disguised"
    ehg = ROOT / "real" / "ehg_disguised"
    r = ct.check_plan(_plan({"op": "replace_split", "step": "cv_scores", "kind": "temporal", "col": "f01"}), ehg)
    assert not r["ok"] and any("time-like" in p for p in r["problems"])
    r = ct.check_plan(_plan({"op": "replace_split", "step": "split_rows", "kind": "random", "col": None}), cwd)
    assert any("R-USE-REQUIRED" in p for p in r["problems"])
    r = ct.check_plan(_plan({"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "nope"}), cwd)
    assert any("not a column" in p for p in r["problems"])
    assert not ct.check_plan(_plan({"op": "move_into_fold", "step": "claimed_eval", "call": "ghost"}), ehg)["ok"]
    assert not ct.check_plan(_plan({"op": "move_into_fold", "step": "load", "call": "oversample"}), ehg)["ok"]
    assert not ct.check_plan(_plan({"op": "move_into_fold", "step": "claimed_eval", "call": "oversample", "x": 1}), ehg)["ok"]


def test_check_plan_schema_and_no_flaw():
    ehg = ROOT / "real" / "ehg_disguised"
    assert ct.check_plan({"verdict": "no_flaw", "factors": [], "reason": "clean"}, ehg)["ok"]
    assert not ct.check_plan({"verdict": "no_flaw", "factors": [{"id": "A"}], "reason": "x"}, ehg)["ok"]
    p = _plan(MOVE)
    p["predicted_drop_pp"] = {"fix_A": 1, "fix_B": 2, "fix_both": 3}  # old 2x2 keys on a one-factor plan
    assert not ct.check_plan(p, ehg)["ok"]
    p = _plan(MOVE, {"op": "replace_split", "step": "cv_scores", "kind": "random", "col": None}, k=2)
    assert ct.check_plan(p, ehg)["layout"] == "factorial"
    p["factors"][0]["id"] = "B"
    assert not ct.check_plan(p, ehg)["ok"]
    assert not ct.check_plan({"verdict": "flaw", "factors": [], "reason": "x"}, ehg)["ok"]
    assert not ct.check_plan(_plan(MOVE, MOVE, MOVE, MOVE, k=1), ehg)["ok"]
