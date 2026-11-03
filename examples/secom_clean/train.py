import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.ensemble import RandomForestClassifier
from sklearn.neighbors import NearestNeighbors
TARGET = 'defect'
METRIC = 'pr_auc'
K_SELECT = 40
N_TREES = 40

def load(path='data.csv'):
    return pd.read_csv(path)

def feats(df):
    return [c for c in df.columns if c.startswith('sensor_')]

def oversample(X, y, seed):
    rng = np.random.default_rng(seed)
    pos = X[y == 1]
    n_new = int((y == 0).sum() - len(pos))
    scale = pos.std(axis=0) + 1e-12
    nn = NearestNeighbors(n_neighbors=6).fit(pos / scale)
    neighbors = nn.kneighbors(pos / scale, return_distance=False)[:, 1:]
    i = rng.integers(0, len(pos), n_new)
    j = neighbors[i, rng.integers(0, 5, n_new)]
    new = pos[i] + rng.random((n_new, 1)) * (pos[j] - pos[i])
    return (np.vstack([X, new]), np.concatenate([y, np.ones(n_new, dtype=int)]))

def cv_scores(X, y, seed):
    ys, ps = ([], [])
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        model = RandomForestClassifier(n_estimators=N_TREES, max_depth=5, class_weight='balanced', random_state=seed, n_jobs=1)
        _g9_X_1, _g9_y_1 = oversample(X[tr], y[tr], seed)
        model.fit(_g9_X_1, _g9_y_1)
        ys.append(y[te])
        ps.append(model.predict_proba(X[te])[:, 1])
    return (np.concatenate(ys), np.concatenate(ps))

def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    return cv_scores(X, y, seed)


def controlled_eval(df, seed):
    return claimed_eval(df, seed)
