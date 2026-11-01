import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_0f6b5b"
SITE = "c_9a104c"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    # the grouping column is metadata for splitting, never a model input
    return [c for c in df.columns if c not in (TARGET, SITE)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)

def split_idx(df, seed, groups=None, test_size=0.25):
    idx = np.arange(len(df))
    if groups is not None:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        return next(gss.split(idx, groups=np.asarray(groups)))
    return train_test_split(idx, test_size=test_size, random_state=seed)


def claimed_eval(df, seed, groups=None):
    # unseen wards are held out: the claimed protocol already splits by group
    tr, te = split_idx(df, seed, np.asarray(df[SITE]) if groups is None else np.asarray(groups))
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr], df[f].to_numpy()[te], seed)
