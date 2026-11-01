"""Falsifier: preregister 3 hypotheses (with direction + predicted signature) and a code patch defining
controlled_eval(df, seed) -> (y_true, y_pred). Reads ONLY the agent view.
mode="mock": regex heuristics over train.py (a scripted stand-in: NEVER report as a Spark/model result).
mode="live": muse-spark-1.3 writes hypotheses + patch."""
import hashlib
import json
import re
from pathlib import Path

from . import llm

PATCH_AUG = '''import numpy as np
import train
from sklearn.model_selection import KFold


def controlled_eval(df, seed):
    # split ORIGINAL records first, augment only inside each training fold
    f = train.feats(df)
    ys, ps = [], []
    for tr, te in KFold(5, shuffle=True, random_state=seed).split(df):
        trd = train.augment(df.iloc[tr].reset_index(drop=True), seed)
        ys.append(df[train.TARGET].to_numpy()[te])
        ps.append(train.fit_predict(trd[f], trd[train.TARGET], df[f].iloc[te], seed))
    return np.concatenate(ys), np.concatenate(ps)
'''

PATCH_TE = '''import numpy as np
import train
from sklearn.model_selection import KFold


def controlled_eval(df, seed):
    # same split as claimed; the category target-rate feature is computed from training labels only (out-of-fold)
    tr, te = train.split_idx(df, seed)
    T, C = train.TARGET, train.CAT
    trd, ted = df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy()
    prior = trd[T].mean()
    trd["prior_rate"] = prior
    for a, b in KFold(5, shuffle=True, random_state=seed).split(trd):
        m = trd.iloc[a].groupby(C)[T].mean()
        trd.loc[trd.index[b], "prior_rate"] = trd.iloc[b][C].map(m).fillna(prior).to_numpy()
    ted["prior_rate"] = ted[C].map(trd.groupby(C)[T].mean()).fillna(prior)
    f = [c for c in trd.columns if c not in (T, C)]
    return ted[T].to_numpy(), train.fit_predict(trd[f], trd[T], ted[f], seed)
'''

PATCH_GENERIC = '''import numpy as np
import train
from sklearn.model_selection import KFold


def controlled_eval(df, seed):
    # independent 5-fold cross-validation over all records (different protocol, different partition)
    f = train.feats(df)
    ys, ps = [], []
    for tr, te in KFold(5, shuffle=True, random_state=seed + 1000).split(df):
        ys.append(df[train.TARGET].to_numpy()[te])
        ps.append(train.fit_predict(df[f].iloc[tr], df[train.TARGET].iloc[tr], df[f].iloc[te], seed))
    return np.concatenate(ys), np.concatenate(ps)
'''


def _mock(code):
    ev = code[code.find("def claimed_eval"):]
    if re.search(r"augment\(", ev) and ev.find("augment(") < ev.find("split_idx("):
        return {"broken": "augmented copies of one record can land on both sides of the train/test split",
                "split_key": "original record (row index modulo table length)",
                "sig": "claimed accuracy exceeds accuracy when whole records are held out, gap grows with augmentation factor",
                "patch": PATCH_AUG, "kind": "near-duplicate leakage"}
    if re.search(r"transform\(\"mean\"\)", code) and code.find("add_features(df)") < code.find("split_idx(data"):
        return {"broken": "a category-level target statistic is computed on all rows before the split, so test labels leak into a feature",
                "split_key": "category column used by the group-by",
                "sig": "claimed accuracy exceeds accuracy when the statistic is computed from training labels only",
                "patch": PATCH_TE, "kind": "target-derived feature"}
    return {"broken": "none found by static inspection; fall back to an independent re-evaluation",
            "split_key": "none", "sig": "accuracy under independent 5-fold CV matches claimed accuracy",
            "patch": PATCH_GENERIC, "kind": "no flaw found"}


SYSTEM = ("You are a scientific adversary. Given a claim and the training script, find the assumption the claim depends on, "
          "propose exactly 3 competing hypotheses, and write Python defining controlled_eval(df, seed) -> (y_true, y_pred) "
          "that runs the cheapest discriminating experiment (you may `import train` and reuse train.fit_predict, train.TARGET, "
          "train.feats). Return ONLY JSON: {\"hypotheses\": [{\"id\": \"H1\", \"text\": str, \"direction\": \"claimed>controlled\"|"
          "\"claimed~controlled\", \"predicted_signature\": str}, x3], \"primary\": \"H1\", \"broken_assumption\": str, "
          "\"split_key\": str, \"code_patch\": str}")


def propose(case_dir, claim, mode="mock"):
    case_dir = Path(case_dir)
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    if mode == "live":
        head = "\n".join((case_dir / "data.csv").read_text(encoding="utf-8").splitlines()[:4])
        h = llm.parse_json(llm.live_complete(SYSTEM, f"CLAIM: {json.dumps({k: claim[k] for k in ('claim','metric','value','split_desc')})}\n"
                                              f"TRAIN.PY:\n{code}\nDATA HEAD:\n{head}", est_usd=0.06, max_tokens=12000))
        hyp = {"mode": "LIVE muse-spark-1.3", **h}
    else:
        m = _mock(code)
        leak = m["kind"] != "no flaw found"
        hyp = {"mode": "MOCK (regex heuristics, not a model result)",
               "hypotheses": [
                   {"id": "H1", "text": m["broken"], "direction": "claimed>controlled" if leak else "claimed~controlled",
                    "predicted_signature": m["sig"]},
                   {"id": "H2", "text": "result is specific to the one random partition (seed sensitivity)", "direction": "claimed~controlled",
                    "predicted_signature": "per-seed deltas change sign"},
                   {"id": "H3", "text": "accuracy is carried by a distribution shift between train and test rows", "direction": "claimed>controlled",
                    "predicted_signature": "not run (primary-only policy)"}],
               "primary": "H1", "broken_assumption": m["broken"], "split_key": m["split_key"], "code_patch": m["patch"]}
    hyp["prereg_sha256"] = hashlib.sha256(json.dumps({k: hyp[k] for k in ("hypotheses", "primary", "code_patch")}, sort_keys=True).encode()).hexdigest()
    return hyp


def recover(case_dir, claim, hyp, error, mode="mock"):
    """Auto-retry once after a failed/timed-out Act step. Mock: swap in the generic independent-CV patch."""
    if mode == "live":
        text = llm.live_complete(SYSTEM, f"Your previous patch failed with:\n{error}\nPREVIOUS PATCH:\n{hyp['code_patch']}\nReturn corrected JSON.",
                                 est_usd=0.05, max_tokens=10000)
        return llm.parse_json(text)["code_patch"]
    return PATCH_GENERIC
