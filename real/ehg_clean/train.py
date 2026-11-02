import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import NearestNeighbors

# Oversampled rare-class classification (named features)
# Random forest, rare-class rows balanced by interpolation, ROC-AUC from 10-fold stratified cross-validation.
TARGET = "premature"
METRIC = "roc_auc"
N_FOLDS = 10
N_TREES = 100
K_NEIGHBORS = 5


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def oversample(X, y, seed):
    """Balance the classes: add synthetic rare-class rows, each placed at a random point on the segment between a rare-class
    row and one of its 5 nearest rare-class neighbours (distances on standardised columns)."""
    rng = np.random.default_rng(seed)
    pos = X[y == 1]
    n_new = int((y == 0).sum() - len(pos))
    sd = pos.std(axis=0) + 1e-12
    nn = NearestNeighbors(n_neighbors=K_NEIGHBORS + 1).fit(pos / sd)
    nbr = nn.kneighbors(pos / sd, return_distance=False)[:, 1:]
    i = rng.integers(0, len(pos), n_new)
    j = nbr[i, rng.integers(0, K_NEIGHBORS, n_new)]
    new = pos[i] + rng.random((n_new, 1)) * (pos[j] - pos[i])
    return np.vstack([X, new]), np.concatenate([y, np.ones(n_new, dtype=int)])


def fold_train_set(X_tr, y_tr, seed):
    return oversample(X_tr, y_tr, seed)


def cv_scores(X, y, seed):
    """Out-of-fold probability for every row of (X, y), pooled over the folds."""
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed).split(X, y):
        Xa, ya = fold_train_set(X[tr], y[tr], seed)
        model = RandomForestClassifier(n_estimators=N_TREES, random_state=seed).fit(Xa, ya)
        ys.append(y[te])
        ps.append(model.predict_proba(X[te])[:, 1])
    return np.concatenate(ys), np.concatenate(ps)


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    return cv_scores(X, y, seed)
