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
    """Keep the K_SELECT predictors with the strongest univariate association with the class labels."""
    return SelectKBest(f_classif, k=K_SELECT).fit(X, y).get_support()


def cv_predict(X, y, seed):
    """Cross-validated 1-nearest-neighbour prediction; the screen is re-run inside each fold on its training samples."""
    pred = np.empty_like(y)
    for tr, te in StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed).split(X, y):
        keep = screen(X[tr], y[tr])
        pred[te] = KNeighborsClassifier(n_neighbors=1).fit(X[tr][:, keep], y[tr]).predict(X[te][:, keep])
    return pred


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    return y, cv_predict(X, y, seed)
