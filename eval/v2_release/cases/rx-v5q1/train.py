import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, GroupKFold
from sklearn.tree import DecisionTreeClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, f_classif
TARGET = "event"
METRIC = "accuracy"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return [c for c in df.columns if c not in (TARGET, "device")]
def evaluate(X, y, seed, groups):
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=4, shuffle=True, random_state=seed).split(X, y):
        m = DecisionTreeClassifier(max_depth=8, min_samples_leaf=2, random_state=seed)
        m.fit(X[tr], y[tr])
        ys.append(y[te])
        ps.append(m.predict(X[te]))
    return np.concatenate(ys), np.concatenate(ps)
def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    return evaluate(X, y, seed, groups=df['device'].to_numpy())
