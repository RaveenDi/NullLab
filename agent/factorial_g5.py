"""G5 loop planner: same task as agent/factorial.py (G4, left untouched for reproducibility), but the fixes are
STRUCTURED EDITS against named steps of train.py, applied by code and checked by agent/fidelity.py.
Recover: on a guard rejection (or an execution error) ONE live retry with the violation message; if it still fails
the case is INCONCLUSIVE (never FALSIFIED)."""
import ast
import hashlib
import json
from pathlib import Path

from . import llm
from .factorial import agent_view

SYSTEM = (
    "You are a scientific adversary planning a 2x2 factorial falsification experiment on a machine-learning claim. "
    "Read the claim excerpt, the training script and the data head. Identify the TWO evaluation steps (call them A and B) "
    "most likely to make the reported accuracy higher than the accuracy the claim's intended use would see. "
    "You do NOT write whole files. You write STRUCTURED EDITS against the named steps (top-level functions) of train.py: "
    "for each of A and B give its kind and, for each function you change, the complete new source of that function "
    "(same name; put any extra numpy/pandas/sklearn imports inside it). Code applies the edits to the original train.py "
    "and runs the edited claimed_eval(df, seed): fix_A applies only A's edits, fix_B only B's, fix_both both. "
    "If A and B change the same function, also give its combined source in both_overrides. "
    "A patch-fidelity guard REJECTS any edit that changes something other than the declared step: the model (estimator "
    "classes, hyperparameters, preprocessing components) must stay exactly as in train.py; a fix may only change WHERE "
    "a component or statistic is fit or which rows are held out, never add label-driven feature selection; "
    "the feature list may change only in a step of kind 'feature' and only by naming columns; the evaluation split, "
    "test size and CV scheme may change only in a step of kind 'split'; the metric is fixed. "
    "Kinds: 'split' (which rows are held out / test population / CV scheme), 'fit_scope' (which rows a statistic, "
    "imputer, scaler, selector or tuner is computed from, or how held-out rows are treated by it), 'feature' (how one "
    "feature is derived from the inputs, or removing a named column). Use only numpy, pandas and scikit-learn. "
    "Before anything runs, commit predictions: the accuracy drop versus the original, in percentage points "
    "(positive = accuracy falls), for each of the three configs, and rank the culprits of the inflation among "
    "'A' (A alone carries most of it), 'B' (B alone carries most of it), 'AxB' (only the combination: fixing either alone "
    "leaves most of the inflation). Return ONLY JSON: "
    '{"A": str, "A_code_line": <one line copied verbatim from train.py>, "B": str, "B_code_line": <one line copied verbatim>, '
    '"edits": {"A": {"kind": "split"|"fit_scope"|"feature", "steps": {"<function name>": "<complete new def>"}}, '
    '"B": {"kind": ..., "steps": {...}}, "both_overrides": {"<function name>": "<complete new def>"}}, '
    '"predicted_drop_pp": {"fix_A": number, "fix_B": number, "fix_both": number}, '
    '"culprit_ranking": ["A"|"B"|"AxB", ...], "reason": str}')


def steps_of(case_dir):
    tree = ast.parse((Path(case_dir) / "train.py").read_text(encoding="utf-8"))
    return [n.name for n in tree.body if isinstance(n, ast.FunctionDef) and n.name != "load"]


def user_msg(case_dir, repeat_id):
    return (agent_view(case_dir) + f"\nSTEPS you may edit (top-level functions of train.py): {', '.join(steps_of(case_dir))}"
            f"\n\n[repeat id: {repeat_id}]")


def prereg_hash(p):
    return hashlib.sha256(json.dumps({k: p.get(k) for k in ("edits", "predicted_drop_pp", "culprit_ranking")},
                                     sort_keys=True).encode()).hexdigest()


def plan(case_dir, repeat_id):
    raw = llm.live_complete(SYSTEM, user_msg(case_dir, repeat_id), est_usd=0.10, tag="g5_planner")
    p = llm.parse_json(raw)
    p["mode"] = "LIVE muse-spark-1.3"
    p["prereg_sha256"] = prereg_hash(p)
    return p, raw


def retry(case_dir, repeat_id, prev, problems):
    """Recover: one live retry carrying the guard's violation messages (or the execution error)."""
    msg = (user_msg(case_dir, repeat_id) + "\n\nYOUR PREVIOUS JSON:\n" +
           json.dumps({k: prev.get(k) for k in ("A", "A_code_line", "B", "B_code_line", "edits", "predicted_drop_pp",
                                                "culprit_ranking", "reason")}) +
           "\n\nIt was REJECTED:\n- " + "\n- ".join(problems) +
           "\nReturn the corrected complete JSON with the same schema. Change only what the rejection requires.")
    raw = llm.live_complete(SYSTEM, msg, est_usd=0.10, tag="g5_planner_retry")
    p = llm.parse_json(raw)
    p["mode"] = "LIVE muse-spark-1.3 (retry)"
    p["prereg_sha256"] = prereg_hash(p)
    return p, raw
