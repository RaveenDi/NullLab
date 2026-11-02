import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.tree import DecisionTreeClassifier
from sklearn.metrics import roc_auc_score

# Civil-war onset (country-year) prediction with a down-sampled random forest, tuned by 10-fold CV.
# The evaluation metric is PR-AUC (average precision) of the predicted onset probability, computed by the harness
# from the returned (y_true, y_score); ROC-AUC is reported alongside.
TARGET = "warstds"
METRIC = "pr_auc"
N_TREES = 300
SAMPSIZE = (30, 90)  # rows drawn per tree (with replacement): peace, war
MTRY_GRID = (2, 46, 90)
FEATURES = ["ager", "agexp", "anoc", "army85", "autch98", "auto4", "autonomy", "avgnabo", "centpol3", "coldwar",
            "decade1", "decade2", "decade3", "decade4", "dem", "dem4", "demch98", "dlang", "drel", "durable", "ef",
            "ef2", "ehet", "elfo", "elfo2", "etdo4590", "expgdp", "exrec", "fedpol3", "fuelexp", "gdpgrowth", "geo1",
            "geo2", "geo34", "geo57", "geo69", "geo8", "illiteracy", "incumb", "infant", "inst", "inst3", "life",
            "lmtnest", "ln_gdpen", "lpopns", "major", "manuexp", "milper", "mirps0", "mirps1", "mirps2", "mirps3",
            "nat_war", "ncontig", "nmgdp", "nmdp4_alt", "numlang", "nwstate", "oil", "p4mchg", "parcomp", "parreg",
            "part", "partfree", "plural", "plurrel", "pol4", "pol4m", "pol4sq", "polch98", "polcomp", "popdense",
            "presi", "pri", "proxregc", "ptime", "reg", "regd4_alt", "relfrac", "seceduc", "second", "semipol3",
            "sip2", "sxpnew", "sxpsq", "tnatwar", "trade", "warhist", "xconst"]


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in FEATURES if c in df.columns]


def fit_forest(X, y, seed, mtry):
    """Random forest with per-class down-sampling: each tree sees SAMPSIZE rows (peace, war) drawn with replacement."""
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
    """caret-style tuning: 10-fold CV ROC-AUC for each mtry in the grid; returns the best mtry."""
    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)
    best, best_auc = MTRY_GRID[0], -1.0
    for m in MTRY_GRID:
        aucs = [roc_auc_score(y[te], forest_score(fit_forest(X[tr], y[tr], seed, m), X[te])) for tr, te in cv.split(X, y)]
        if np.mean(aucs) > best_auc:
            best, best_auc = m, float(np.mean(aucs))
    return best


def split_rows(df, seed):
    """Rows used to fit the final model (1945-1989), and rows it is scored on (1990-2000)."""
    idx = np.arange(len(df))
    return idx[df["year"].to_numpy() < 1990], idx[df["year"].to_numpy() >= 1990]


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    tr, te = split_rows(df, seed)
    mtry = tune_mtry(X[tr], y[tr], seed)
    trees = fit_forest(X[tr], y[tr], seed, mtry)
    return y[te], forest_score(trees, X[te])
