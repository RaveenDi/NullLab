"""Baselines, same blind inputs as NullLab (agent view only).
B0: Deepchecks-STYLE data checklist (deepchecks itself is not installed; this re-implements 4 of its data-integrity checks
    on data.csv. It is NOT the real Deepchecks suite).
B1: fixed GroupKFold-style group split on a heuristically guessed group column, compared with the claimed split.
B3 (generic non-Meta coder, e.g. OpenHands): NOT RUN, UNVERIFIED."""
import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True  # never leave __pycache__ inside the agent-view corpus dirs

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sandbox.run import paired_bootstrap  # noqa: E402
from sandbox.verdict import seed_call  # noqa: E402


def _load_train(case_dir):
    spec = importlib.util.spec_from_file_location("train_" + Path(case_dir).name, Path(case_dir) / "train.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def b0_checklist(case_dir):
    case_dir = Path(case_dir)
    t = _load_train(case_dir)
    df = pd.read_csv(case_dir / "data.csv")
    flags = []
    if df.duplicated().mean() > 0.01:
        flags.append("duplicate rows > 1%")
    y = df[t.TARGET]
    for c in df.columns:
        if c == t.TARGET or df[c].dtype.kind not in "if" or df[c].nunique() < 2:
            continue
        # single-feature predictive power (rank AUC); > 0.95 would be flagged as a leakage suspect
        from sklearn.metrics import roc_auc_score
        if y.nunique() == 2:
            a = roc_auc_score(y, df[c])
            if max(a, 1 - a) > 0.95:
                flags.append(f"{c} single-feature AUC {max(a, 1 - a):.2f}")
    if y.nunique() > 1 and y.value_counts(normalize=True).iloc[0] > 0.95:
        flags.append("extreme class imbalance")
    return {"baseline": "B0 Deepchecks-style checklist", "flagged": bool(flags), "flags": flags}


def guess_group_col(df, target):
    n = len(df)
    for c in df.columns:
        if c == target or df[c].dtype.kind not in "iO":
            continue
        if 0.02 * n <= df[c].nunique() <= 0.6 * n:
            return c
    return None


def b1_groupkfold(case_dir, seeds=(42, 43, 44), n_boot=1000):
    case_dir = Path(case_dir)
    t = _load_train(case_dir)
    df = pd.read_csv(case_dir / "data.csv")
    g = guess_group_col(df, t.TARGET)
    if g is None:
        return {"baseline": "B1 fixed GroupKFold", "flagged": False, "applicable": False, "reason": "no group column found"}
    calls = []
    for s in seeds:
        y1, p1 = t.claimed_eval(df, s)
        y2, p2 = t.claimed_eval(df, s, groups=df[g].to_numpy())
        calls.append(seed_call(paired_bootstrap(y1, p1, y2, p2, n_boot, s)))
    return {"baseline": "B1 fixed GroupKFold", "applicable": True, "group_col": g,
            "flagged": all(c == "FALSIFIED" for c in calls), "per_seed": calls}
