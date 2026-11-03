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

PATCH_SELECT = '''import numpy as np
import train
from sklearn.model_selection import KFold
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, f_classif


def controlled_eval(df, seed):
    # scaling + selection are re-fit inside each training fold (leak-free protocol)
    X = df[train.feats(df)].to_numpy()
    y = df[train.TARGET].to_numpy()
    ys, ps = [], []
    for tr, te in KFold(5, shuffle=True, random_state=seed).split(df):
        sc = StandardScaler().fit(X[tr])
        sel = SelectKBest(f_classif, k=train.K).fit(sc.transform(X[tr]), y[tr])
        Xtr = sel.transform(sc.transform(X[tr]))
        Xte = sel.transform(sc.transform(X[te]))
        ys.append(y[te])
        ps.append(train.fit_predict(Xtr, y[tr], Xte, seed))
    return np.concatenate(ys), np.concatenate(ps)
'''

PATCH_TIME = '''import numpy as np
import train


def controlled_eval(df, seed):
    # respect time: train on the earliest 75% of records, test on the latest 25%
    order = np.argsort(df[train.TIME].to_numpy())
    cut = int(0.75 * len(df))
    tr, te = order[:cut], order[cut:]
    f = train.feats(df)
    X = df[f].to_numpy()
    y = df[train.TARGET].to_numpy()
    return y[te], train.fit_predict(X[tr], y[tr], X[te], seed)
'''

PATCH_PROXY = '''import numpy as np
import train
from sklearn.model_selection import KFold


def controlled_eval(df, seed):
    # same protocol minus the proxy column, which must not be a model input
    f = [c for c in train.feats(df) if c != train.PROXY]
    X = df[f].to_numpy()
    y = df[train.TARGET].to_numpy()
    ys, ps = [], []
    for tr, te in KFold(5, shuffle=True, random_state=seed + 1000).split(df):
        ys.append(y[te])
        ps.append(train.fit_predict(X[tr], y[tr], X[te], seed))
    return np.concatenate(ys), np.concatenate(ps)
'''

PATCH_GROUP = '''import numpy as np
import train
from sklearn.model_selection import GroupShuffleSplit


def controlled_eval(df, seed):
    # unseen groups are held out: split by the grouping column instead of by row
    gss = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    tr, te = next(gss.split(df, groups=df[train.SITE].to_numpy()))
    f = train.feats(df)
    X = df[f].to_numpy()
    y = df[train.TARGET].to_numpy()
    return y[te], train.fit_predict(X[tr], y[tr], X[te], seed)
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
    if "SelectKBest" in code:
        return {"broken": "scaling and feature selection are fit on all rows before the split, so test labels shape the features",
                "split_key": "none (preprocessing fit scope, not a row group)",
                "sig": "claimed accuracy exceeds accuracy when scaling and selection are re-fit inside each training fold",
                "patch": PATCH_SELECT, "kind": "pre-split preprocessing leakage"}
    if "chronological" in code:
        return {"broken": "records span time with a shifting label boundary but are evaluated with a random split",
                "split_key": "record time (earliest 75% train, latest 25% test)",
                "sig": "claimed accuracy exceeds accuracy when training only on past records and testing on future ones",
                "patch": PATCH_TIME, "kind": "temporal leakage"}
    if "PROXY = " in code:
        return {"broken": "a proxy column carrying the label is used as a model input",
                "split_key": "none (feature removal, not a row group)",
                "sig": "claimed accuracy exceeds accuracy when the proxy column is removed from the inputs",
                "patch": PATCH_PROXY, "kind": "proxy/target feature leakage"}
    if "SITE = " in code and "split_idx(df, seed, groups)" in ev:
        return {"broken": "a group identifier is used as a feature while groups repeat on both sides of the split",
                "split_key": "grouping column held out whole per split",
                "sig": "claimed accuracy exceeds accuracy when whole groups are held out of training",
                "patch": PATCH_GROUP, "kind": "group non-independence"}
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
                                 est_usd=0.05, max_tokens=12000)
        return llm.parse_json(text)["code_patch"]
    return PATCH_GENERIC
