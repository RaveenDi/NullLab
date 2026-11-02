"""G7 corpus builder: DISGUISED version of the REAL-PINNED civil-war case (G6), built from the same data
(real/civilwar_apparent/data.csv, itself built by eval/build_g6.py from the md5-verified Dataverse file).
Purpose: defeat the 'the model just remembers the paper' objection. Every column is renamed to f01..f90, the target to
'target', the time column 'year' to 'epoch' (year - 1944, so 1..56); train.py comments and the excerpt are rewritten in
another domain's words. The claim class is unchanged: a FORECASTING claim whose evaluation scores the model on the very
rows (periods) it was trained on (leaky) or trains on earlier epochs and scores on later ones (clean).
Usage: python eval/build_g7.py [version]      version 1 (default) .. 3: progressively stronger re-disguise
Ground truth (published delta) lives only in eval/g7_truth.json (written here), never in a case folder or agent view."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "real"
SRC = REAL / "civilwar_apparent"
LEAKY, CLEAN = REAL / "civilwar_disguised", REAL / "civilwar_disguised_clean"
SPLIT_EPOCH = 46  # 1990 - 1944: the published re-analysis trains on epochs 1-45 and tests on 46-56

# Wording per disguise version (the numerics, row order and hyper-parameters never change).
WORDS = {
    1: dict(domain="supplier-failure", unit="supplier node", units="node-periods", system="a regional supply network",
            event="supplier-failure onset", events="failure onsets", ok="no-failure", bad="failure",
            title="Supplier failure onset (node-period) prediction"),
    2: dict(domain="line-stoppage", unit="production line", units="line-shifts", system="a factory group",
            event="line-stoppage onset", events="stoppage onsets", ok="running", bad="stoppage",
            title="Line stoppage onset (line-shift) prediction"),
    3: dict(domain="equipment-fault", unit="sensor-equipped unit", units="unit-cycles", system="a fleet of units",
            event="equipment-fault onset", events="fault onsets", ok="healthy", bad="fault",
            title="Equipment fault onset (unit-cycle) prediction"),
}

TRAIN_TMPL = '''import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score

# {title} with a down-sampled random forest, tuned by 10-fold CV.
# The evaluation metric is PR-AUC (average precision) of the predicted onset probability, computed by the harness
# from the returned (y_true, y_score); ROC-AUC is reported alongside.
TARGET = "target"
METRIC = "pr_auc"
N_TREES = 300
SAMPSIZE = (30, 90)  # rows drawn per tree (with replacement): {ok}, {bad}
MTRY_GRID = (2, 46, 90)
FEATURES = {features}


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in FEATURES if c in df.columns]


def fit_forest(X, y, seed, mtry):
    """Random forest with per-class down-sampling: each tree sees SAMPSIZE rows ({ok}, {bad}) drawn with replacement."""
    rng = np.random.default_rng(seed)
    i0, i1 = np.flatnonzero(y == 0), np.flatnonzero(y == 1)
    trees = []
    for _ in range(N_TREES):
        idx = np.concatenate([rng.choice(i0, SAMPSIZE[0], replace=True), rng.choice(i1, SAMPSIZE[1], replace=True)])
        t = DecisionTreeClassifier(max_features=mtry, random_state=int(rng.integers(2**31 - 1)))
        trees.append(t.fit(X[idx], y[idx]))
    return trees


def forest_score(trees, X):
    return np.mean([t.predict_proba(X)[:, 1] for t in trees], axis=0)


def tune_mtry(X, y, seed, k=10):
    """Grid-search tuning: 10-fold CV ROC-AUC for each mtry in the grid; returns the best mtry."""
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
    best, best_auc = MTRY_GRID[0], -1.0
    for m in MTRY_GRID:
        aucs = [roc_auc_score(y[te], forest_score(fit_forest(X[tr], y[tr], seed, m), X[te])) for tr, te in cv.split(X, y)]
        if np.mean(aucs) > best_auc:
            best, best_auc = m, float(np.mean(aucs))
    return best


def split_rows(df, seed):
{split_body}


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    tr, te = split_rows(df, seed)
    mtry = tune_mtry(X[tr], y[tr], seed)
    trees = fit_forest(X[tr], y[tr], seed, mtry)
    return y[te], forest_score(trees, X[te])
'''

SPLIT_LEAKY = '''    """Rows used to fit the final model, and rows it is scored on."""
    idx = np.arange(len(df))
    return idx, idx'''

SPLIT_CLEAN = '''    """Rows used to fit the final model (epochs 1-45), and rows it is scored on (epochs 46-56)."""
    idx = np.arange(len(df))
    return idx[df["epoch"].to_numpy() < 46], idx[df["epoch"].to_numpy() >= 46]'''

EXCERPT_TMPL = """## Methods (excerpt)
We compare a random forest with logistic regression models for predicting {event} in {units} records
(epochs 1-56, about 1 onset per 100 {units}) of {system}. The forest down-samples the majority class
(30 {ok} and 90 {bad} observations per tree) and its tuning parameter is chosen by 10-fold cross-validation.
The models are meant to forecast {events} in {units} they were not trained on.
## Results
We report cross-validated performance: the random forest reaches an area under the ROC curve above 0.9 and
offers superior predictive power for {event} compared to logistic regression.
"""


EXCERPT_TMPL_V2 = """## Methods (excerpt)
We train a random forest to predict {event} in {units} records
(epochs 1-56, about 1 onset per 100 {units}) of {system}. The forest down-samples the majority class
(30 {ok} and 90 {bad} observations per tree) and its tuning parameter is chosen by 10-fold cross-validation.
The model is meant to forecast {events} in {units} it was not trained on.
## Results
We report cross-validated performance: the random forest reaches an area under the ROC curve above 0.9,
which we take as strong predictive power for {event}.
"""


def feature_names(version):
    import re
    src = (SRC / "train.py").read_text(encoding="utf-8")
    feats = re.search(r"FEATURES = (\[.*?\])\n", src, re.S).group(1)
    orig = eval(feats)  # noqa: S307  (our own checked-in file)
    new = [f"f{i + 1:02d}" for i in range(len(orig))]
    return dict(zip(orig, new)), new


def build(version=1):
    w = WORDS[version]
    mapping, new = feature_names(version)
    d = pd.read_csv(SRC / "data.csv")
    out = d.rename(columns={**mapping, "warstds": "target"})
    out["epoch"] = d["year"] - 1944
    out = out[["epoch"] + new + ["target"]]
    if version >= 2:
        # Version 1 was still recognised from the data values / pipeline (docs/EVAL-7.md). Re-disguise: a power-of-two
        # rescaling of every feature (exact in floating point, strictly increasing, so tree splits and the pipeline's numbers
        # are unchanged) hides the raw value signatures; the logistic-regression comparison sentence
        # is dropped from the excerpt (the forecasting claim and the flaw are untouched).
        rng = np.random.default_rng(700 + version)
        for c in new:
            out[c] = out[c] * 2.0 ** int(rng.integers(-4, 7))  # exact in floating point: order and ties preserved
    if version >= 3:  # also scramble the column order (changes tree randomness slightly; numbers no longer bit-identical)
        perm = list(np.random.default_rng(900 + version).permutation(len(new)))
        new = [new[i] for i in perm]
        out = out[["epoch"] + new + ["target"]]
    assert len(new) == 90 and out.shape[1] == 92
    feat_src = "[" + ",\n            ".join(", ".join(f'"{c}"' for c in new[i:i + 12]) for i in range(0, len(new), 12)) + "]"
    for case, body in ((LEAKY, SPLIT_LEAKY), (CLEAN, SPLIT_CLEAN)):
        case.mkdir(exist_ok=True)
        out.to_csv(case / "data.csv", index=False)
        (case / "train.py").write_text(TRAIN_TMPL.format(features=feat_src, split_body=body, **w), encoding="utf-8")
        (case / "excerpt.md").write_text((EXCERPT_TMPL if version == 1 else EXCERPT_TMPL_V2).format(**w), encoding="utf-8")
    return out.shape, mapping


def write_truth(version, mapping):
    """Host-only truth. NEVER copied into a case folder; the sandbox only copies train.py and data.csv."""
    truth = {
        "civilwar_disguised": {
            "provenance": "REAL-PINNED (disguised re-labelling of the G6 civil-war case; same rows, same numbers)",
            "disguise_version": version, "leaky": True, "metric": "pr_auc",
            "published_inflation_pr_auc": 0.36,
            "published": "Neunhoeffer & Sternberg (2019), Political Analysis 27(1):101-106, doi:10.1017/pan.2018.39: "
                         "PR-AUC 0.43 (apparent error, Muchlinski et al. 2016) vs 0.07 (train 1945-1989, test 1990-2000)",
            "flaw": "scored on the rows it was trained on although the use is forecasting later periods; the control is a "
                    "temporal split (train epochs 1-45, test epochs 46-56)",
            "column_map_original_to_disguised": {**mapping, "warstds": "target", "year": "epoch = year - 1944"},
        },
        "civilwar_disguised_clean": {"provenance": "REAL-PINNED (disguised)", "disguise_version": version, "leaky": False,
                                     "metric": "pr_auc", "expected_sign": "0",
                                     "flaw": "none: trained on epochs 1-45, scored on epochs 46-56"},
    }
    (ROOT / "eval" / "g7_truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")


def hashes():
    return {c.name: {n: hashlib.sha256((c / n).read_bytes()).hexdigest() for n in ("train.py", "excerpt.md", "data.csv")}
            for c in (LEAKY, CLEAN)}


if __name__ == "__main__":
    v = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    shape, mp = build(v)
    write_truth(v, mp)
    print("disguise version", v, "data", shape)
    print(json.dumps(hashes(), indent=1))
