"""G9 behavioural guard tests (offline; the worker runs compiled code in a subprocess; no model calls, no network)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import guard_g9 as g  # noqa: E402

EHG, EHGC, ESL = (ROOT / "real" / c for c in ("ehg_disguised", "ehg_disguised_clean", "esl_selection"))
PROF = {"overrides": {"N_TREES": 10}}


def plan(*ops):
    return {"factors": [{"id": "A", "ops": list(ops)}]}


MOVE = {"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}
DROP = {"op": "drop_from_eval", "step": "claimed_eval", "call": "oversample"}


# ---- pure analysis on synthetic traces ----
def ev(i, kind, cls, obj, rid, y=True, stack=(), params=None):
    return {"i": i, "kind": kind, "cls": cls, "obj": obj, "rid": rid, "y": y, "stack": list(stack), "params": params, "fn": None}


def trace(events, E, n_eval=None):
    return {"status": "ok", "events": events, "E": E, "n_eval": n_eval or len(E), "relabelled": False, "col_index": list(range(10)), "cols": {"t": [float(i) for i in range(10)]}}


P = {"a": "1"}


def test_resubstitution_and_clean_split_are_told_apart():
    leaky = trace([ev(0, "fit", "M", 1, list(range(10)), params=P), ev(1, "score", "M", 1, list(range(10)))], list(range(10)))
    clean = trace([ev(0, "fit", "M", 1, list(range(7)), params=P), ev(1, "score", "M", 1, [7, 8, 9])], [7, 8, 9])
    assert g.contamination(g.analyze(leaky))["self"] == 10
    assert g.contamination(g.analyze(clean))["self"] == 0


def test_upstream_component_overlap_detected_and_fixed_by_folding():
    leaky = trace([ev(0, "fn", "sel", 5, list(range(10))), ev(1, "fit", "M", 1, list(range(7)), params=P), ev(2, "score", "M", 1, [7, 8, 9])], [7, 8, 9])
    fixed = trace([ev(0, "fn", "sel", 5, list(range(7))), ev(1, "fit", "M", 1, list(range(7)), params=P), ev(2, "score", "M", 1, [7, 8, 9])], [7, 8, 9])
    assert g.contamination(g.analyze(leaky))["ctx"]["sel"] == 3
    assert g.contamination(g.analyze(fixed))["ctx"]["sel"] == 0
    r = g.behaviour_check(leaky, fixed, [{"op": "move_into_fold", "step": "s", "call": "sel"}], "x = 1\n")
    assert r["decision"] == "ACCEPT", r
    r = g.behaviour_check(fixed, fixed, [{"op": "move_into_fold", "step": "s", "call": "sel"}], "x = 1\n")
    assert r["decision"] == "REJECT" and any("NOOP" in p or "PRECONDITION" in p for p in r["problems"])


def test_model_change_is_rejected():
    a = trace([ev(0, "fit", "M", 1, list(range(7)), params={"a": "1"}), ev(1, "score", "M", 1, [7, 8, 9])], [7, 8, 9])
    b = trace([ev(0, "fit", "N", 1, list(range(5)), params={"a": "1"}), ev(1, "score", "N", 1, [7, 8, 9])], [7, 8, 9])
    c = trace([ev(0, "fit", "M", 1, list(range(5)), params={"a": "2"}), ev(1, "score", "M", 1, [7, 8, 9])], [7, 8, 9])
    op = [{"op": "replace_split", "step": "s", "kind": "random", "col": None}]
    assert any("class set" in p for p in g.behaviour_check(a, b, op, "x = 1\n")["problems"])
    assert any("not a tuned value" in p for p in g.behaviour_check(a, c, op, "M(a=1)\n")["problems"])
    assert not any("MODEL" in p for p in g.behaviour_check(a, c, op, "M(a=v)\n")["problems"])  # non-constant in source: tuned value may differ


def test_temporal_direction_is_checked_not_assumed():
    # train rows 0..6 earlier than scored 7..9: ok. A reversed split (train 3..9, score 0..2) must fail.
    orig = trace([ev(0, "fit", "M", 1, list(range(10)), params=P), ev(1, "score", "M", 1, list(range(10)))], list(range(10)))
    good = trace([ev(0, "fit", "M", 1, list(range(7)), params=P), ev(1, "score", "M", 1, [7, 8, 9])], [7, 8, 9])
    rev = trace([ev(0, "fit", "M", 1, list(range(3, 10)), params=P), ev(1, "score", "M", 1, [0, 1, 2])], [0, 1, 2])
    op = [{"op": "replace_split", "step": "s", "kind": "temporal", "col": "t"}]
    assert g.behaviour_check(orig, good, op, "x\n", expect_resize=True, hold_steps={"s"})["decision"] == "ACCEPT"
    assert g.behaviour_check(orig, rev, op, "x\n", expect_resize=True, hold_steps={"s"})["decision"] == "REJECT"
    # a split that is already temporal is a no-op to replace
    assert g.behaviour_check(good, good, op, "x\n", expect_resize=True, hold_steps={"s"})["decision"] == "REJECT"


def test_untracked_provenance_fails_closed_and_crash_rejects():
    lost = trace([ev(0, "fit", "M", 1, None, params=P), ev(1, "score", "M", 1, None)], list(range(3)))
    orig = trace([ev(0, "fit", "M", 1, list(range(10)), params=P), ev(1, "score", "M", 1, list(range(10)))], list(range(10)))
    r = g.behaviour_check(orig, lost, [{"op": "replace_split", "step": "s", "kind": "random", "col": None}], "x\n", expect_resize=True, hold_steps={"s"})
    assert r["decision"] in ("UNVERIFIABLE", "REJECT")
    r = g.behaviour_check(orig, {"status": "crash", "error": "boom", "events": []}, [], "x\n")
    assert r["decision"] == "REJECT" and r.get("crash")


# ---- real runs (subprocess) ----
def test_ehg_known_correct_fixes_accepted_and_overlap_measured():
    for op in (MOVE, DROP):
        r = g.guard_plan(EHG, plan(op), PROF)
        assert r["decision"] == "ACCEPT", r["problems"]
        f = r["configs"]["fix_all"]["facts"]
        assert f["orig_contam"]["ctx"]["oversample"] > 0 and f["E_synth_orig"] > 0 and f["E_synth_fix"] == 0
        assert f["fix_contam"]["self"] == 0
    f = g.guard_plan(EHG, plan(MOVE), PROF)["configs"]["fix_all"]["facts"]
    assert f["fix_contam"]["ctx"]["oversample"] == 0


def test_ehg_clean_pipeline_has_nothing_to_move():
    r = g.guard_plan(EHGC, plan(MOVE), PROF)
    assert r["decision"] == "REJECT" and any("NOT_APPLICABLE" in p for p in r["problems"])


def test_esl_selection_moved_into_fold_accepted():
    r = g.guard_plan(ESL, plan({"op": "move_into_fold", "step": "claimed_eval", "call": "screen"}), PROF)
    assert r["decision"] == "ACCEPT", r["problems"]
    assert r["configs"]["fix_all"]["facts"]["orig_contam"]["ctx"]["screen"] > 0


def test_civilwar_temporal_split_accepted_clean_one_rejected_as_noop():
    prof = {"overrides": {"N_TREES": 4}, "max_rows": 1500}
    op = {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "epoch"}
    r = g.guard_plan(ROOT / "real" / "civilwar_disguised", plan(op), prof)
    assert r["decision"] == "ACCEPT", r["problems"]
    r = g.guard_plan(ROOT / "real" / "civilwar_disguised_clean", plan(op), prof)
    assert r["decision"] == "REJECT" and any("already satisfies" in p for p in r["problems"])
