"""Evaluator-only: builds the BRIEF-4 compositional spike case (SYNTHETIC) and its reference 2x2 patches.
Agent view  -> factorial/comp_visit_history/{train.py, data.csv, excerpt.md}
Evaluator   -> eval/factorial_truth.json (flaw definitions + reference patches; never enters the sandbox or a prompt)

Design (Kapoor & Narayanan taxonomy, https://arxiv.org/abs/2207.07048):
  A = target-derived feature computed before the split: each patient's event rate over ALL visits (incl. test visits
      and the visit itself) is a model input.
  B = non-independence: visits are split at random, so the same patient sits on both sides, while the claim is about
      NEW patients.
Either leak alone hands the model the patient's latent risk for a test visit, so fixing only one leaves the other alive.
Run: python eval/build_factorial.py"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from hash_cols import hname

ROOT = Path(__file__).resolve().parent.parent
CASE = "comp_visit_history"
OUT = ROOT / "factorial" / CASE

TARGET, SUBJ = hname("adverse_event"), hname("patient_id")
FEATS = [hname(f"lab_{i}") for i in range(5)]

TRAIN_PY = f'''import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

TARGET = "{TARGET}"
PATIENT = "{SUBJ}"
HIST = "patient_event_rate"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_history(df):
    # each patient's historical adverse-event rate
    df = df.copy()
    df[HIST] = df.groupby(PATIENT)[TARGET].transform("mean")
    return df


def feats(df):
    return [c for c in df.columns if c not in (TARGET, PATIENT)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    data = add_history(df)
    tr, te = split_idx(data, seed)
    f = feats(data)
    X, y = data[f].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
'''

EXCERPT = """## Methods (excerpt)
We predict whether an outpatient visit ends in an adverse event from five routine lab measurements plus the patient's historical adverse-event rate.
Visits were randomly divided into 75% training and 25% test with a fixed random seed.
## Results
Our model achieves {acc}% accuracy on held-out visits and is intended to triage new patients at their first referral.
"""

# ---- evaluator-only reference patches (ground truth for the factorial; written by the builder, NOT by the agent) ----
REF_FIX_A = '''import numpy as np
import train
from sklearn.model_selection import KFold


def _oof_rate(trd, ted, seed):
    T, P, H = train.TARGET, train.PATIENT, train.HIST
    prior = trd[T].mean()
    trd[H] = prior
    for a, b in KFold(5, shuffle=True, random_state=seed).split(trd):
        m = trd.iloc[a].groupby(P)[T].mean()
        trd.loc[trd.index[b], H] = trd.iloc[b][P].map(m).fillna(prior).to_numpy()
    ted[H] = ted[P].map(trd.groupby(P)[T].mean()).fillna(prior)
    return trd, ted


def controlled_eval(df, seed):
    # fix A only: patient rate from training labels only (out-of-fold); random visit split kept
    tr, te = train.split_idx(df, seed)
    trd, ted = _oof_rate(df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy(), seed)
    f = train.feats(trd)
    return ted[train.TARGET].to_numpy(), train.fit_predict(trd[f].to_numpy(), trd[train.TARGET].to_numpy(), ted[f].to_numpy(), seed)
'''

REF_FIX_B = '''import numpy as np
import train
from sklearn.model_selection import GroupShuffleSplit


def controlled_eval(df, seed):
    # fix B only: whole patients held out; patient rate still computed on all visits before the split
    data = train.add_history(df)
    tr, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=seed).split(data, groups=data[train.PATIENT]))
    f = train.feats(data)
    X, y = data[f].to_numpy(), data[train.TARGET].to_numpy()
    return y[te], train.fit_predict(X[tr], y[tr], X[te], seed)
'''

REF_FIX_BOTH = REF_FIX_A.split("def controlled_eval", maxsplit=1)[0].replace(
    "from sklearn.model_selection import KFold", "from sklearn.model_selection import KFold, GroupShuffleSplit") + '''def controlled_eval(df, seed):
    # fix both: whole patients held out AND patient rate from training labels only (unseen patients get the prior)
    tr, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=seed).split(df, groups=df[train.PATIENT]))
    trd, ted = _oof_rate(df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy(), seed)
    f = train.feats(trd)
    return ted[train.TARGET].to_numpy(), train.fit_predict(trd[f].to_numpy(), trd[train.TARGET].to_numpy(), ted[f].to_numpy(), seed)
'''


def make_data(seed=2026, n_pat=250):
    rng = np.random.default_rng(seed)
    rows = []
    for p in range(n_pat):
        u = rng.normal(0, 2.5)                       # latent patient risk
        for _ in range(rng.integers(6, 13)):         # 6..12 visits (v2; v1 used 2..6 visits, u sd 2.0, 400 patients)
            x = rng.normal(0, 1, 5)
            logit = u + 0.9 * x[0] - 0.7 * x[1] + 0.4 * x[2]
            rows.append([*x, p, int(rng.random() < 1 / (1 + np.exp(-logit)))])
    df = pd.DataFrame(rows, columns=FEATS + [SUBJ, TARGET])
    return df.sample(frac=1, random_state=seed).reset_index(drop=True)


def main(claimed_acc=None):
    OUT.mkdir(parents=True, exist_ok=True)
    df = make_data()
    df.to_csv(OUT / "data.csv", index=False)
    (OUT / "train.py").write_text(TRAIN_PY, encoding="utf-8")
    (OUT / "excerpt.md").write_text(EXCERPT.format(acc=claimed_acc or "XX"), encoding="utf-8")
    truth = {
        "case": CASE, "provenance": "SYNTHETIC", "leaky": True,
        "flaw_A": {"kind": "target-derived feature computed on all rows before the split",
                   "code_substr": 'df[HIST] = df.groupby(PATIENT)[TARGET].transform("mean")'},
        "flaw_B": {"kind": "non-independence: random visit split, same patient on both sides; claim is about new patients",
                   "code_substr": "return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)"},
        "ref_patches": {"fix_A": REF_FIX_A, "fix_B": REF_FIX_B, "fix_both": REF_FIX_BOTH},
        "agent_view_sha256": {n: hashlib.sha256((OUT / n).read_bytes()).hexdigest() for n in ("train.py", "data.csv", "excerpt.md")},
    }
    (ROOT / "eval" / "factorial_truth.json").write_text(json.dumps(truth, indent=1))
    print(CASE, df.shape, "patients", df[SUBJ].nunique(), f"event rate {df[TARGET].mean():.3f}")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
