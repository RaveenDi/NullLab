import numpy as np
import pandas as pd
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import KNeighborsClassifier

TARGET = "label"
K_SELECT = 100
N_FOLDS = 5


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def screen(X, y):
    """Step 1: keep the K_SELECT predictors with the strongest univariate association with the class labels."""
    return SelectKBest(f_classif, k=K_SELECT).fit(X, y).get_support()


def cv_predict(X, y, seed):
    """Steps 2-3: 1-nearest-neighbour classifier, cross-validated prediction for every sample."""
    pred = np.empty_like(y)
    for tr, te in StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed).split(X, y):
        pred[te] = KNeighborsClassifier(n_neighbors=1).fit(X[tr], y[tr]).predict(X[te])
    return pred


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    keep = screen(X, y)
    return y, cv_predict(X[:, keep], y, seed)
