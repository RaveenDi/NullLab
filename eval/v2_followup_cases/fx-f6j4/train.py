import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
TARGET = 'material_state'
METRIC = "accuracy"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return [c for c in df.columns if c != TARGET]
def evaluate(X, y, seed):
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        model = DecisionTreeClassifier(max_depth=4, min_samples_leaf=2, random_state=seed)
        model.fit(X[tr], y[tr])
        ys.append(y[te])
        ps.append(model.predict(X[te]))
    return np.concatenate(ys), np.concatenate(ps)
def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    return evaluate(X, y, seed)
