import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score

# Line stoppage onset (line-shift) prediction with a down-sampled random forest, tuned by 10-fold CV.
# The evaluation metric is PR-AUC (average precision) of the predicted onset probability, computed by the harness
# from the returned (y_true, y_score); ROC-AUC is reported alongside.
TARGET = "target"
METRIC = "pr_auc"
N_TREES = 300
SAMPSIZE = (30, 90)  # rows drawn per tree (with replacement): running, stoppage
MTRY_GRID = (2, 46, 90)
FEATURES = ["f01", "f02", "f03", "f04", "f05", "f06", "f07", "f08", "f09", "f10", "f11", "f12",
            "f13", "f14", "f15", "f16", "f17", "f18", "f19", "f20", "f21", "f22", "f23", "f24",
            "f25", "f26", "f27", "f28", "f29", "f30", "f31", "f32", "f33", "f34", "f35", "f36",
            "f37", "f38", "f39", "f40", "f41", "f42", "f43", "f44", "f45", "f46", "f47", "f48",
            "f49", "f50", "f51", "f52", "f53", "f54", "f55", "f56", "f57", "f58", "f59", "f60",
            "f61", "f62", "f63", "f64", "f65", "f66", "f67", "f68", "f69", "f70", "f71", "f72",
            "f73", "f74", "f75", "f76", "f77", "f78", "f79", "f80", "f81", "f82", "f83", "f84",
            "f85", "f86", "f87", "f88", "f89", "f90"]


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in FEATURES if c in df.columns]


def fit_forest(X, y, seed, mtry):
    """Random forest with per-class down-sampling: each tree sees SAMPSIZE rows (running, stoppage) drawn with replacement."""
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
    """Rows used to fit the final model (epochs 1-45), and rows it is scored on (epochs 46-56)."""
    idx = np.arange(len(df))
    return idx[df["epoch"].to_numpy() < 46], idx[df["epoch"].to_numpy() >= 46]


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    tr, te = split_rows(df, seed)
    mtry = tune_mtry(X[tr], y[tr], seed)
    trees = fit_forest(X[tr], y[tr], seed, mtry)
    return y[te], forest_score(trees, X[te])
