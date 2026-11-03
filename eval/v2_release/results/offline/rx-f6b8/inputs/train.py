import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.ensemble import RandomForestClassifier
TARGET = 'event'
PREDICTORS = ['energy', 'phase']
METRIC = "pr_auc"
N_TREES = 40
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return PREDICTORS
def claimed_eval(df, seed):
    X = df[feats(df)].fillna(0.0).to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    p = np.empty(len(y), dtype=float)
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        m = RandomForestClassifier(n_estimators=N_TREES, max_depth=5, class_weight="balanced", random_state=seed, n_jobs=1)
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return y, p
