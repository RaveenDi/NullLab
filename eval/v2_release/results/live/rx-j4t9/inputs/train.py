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
def screen(X, y):
    s = SelectKBest(f_classif, k=4).fit(X, y)
    return s.get_support(indices=True)
def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=4, shuffle=True, random_state=seed).split(X, y):
        k = screen(X[tr], y[tr])
        m = DecisionTreeClassifier(max_depth=3, min_samples_leaf=4, random_state=seed)
        m.fit(X[tr][:, k], y[tr])
        ys.append(y[te])
        ps.append(m.predict(X[te][:, k]))
    return np.concatenate(ys), np.concatenate(ps)
