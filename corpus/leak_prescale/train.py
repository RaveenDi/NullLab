import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.feature_selection import SelectKBest, f_classif

TARGET = "c_f0b430"
K = 20


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def prep_full(df):
    # standardize, then keep the K most target-associated features -- fit on ALL rows
    Xs = StandardScaler().fit_transform(df[feats(df)])
    sel = SelectKBest(f_classif, k=K).fit(Xs, df[TARGET])
    return sel.get_support()


def fit_predict(Xtr, ytr, Xte, seed):
    m = LogisticRegression(max_iter=3000, random_state=seed)
    return m.fit(Xtr, ytr).predict(Xte)

def split_idx(df, seed, groups=None, test_size=0.25):
    idx = np.arange(len(df))
    if groups is not None:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        return next(gss.split(idx, groups=np.asarray(groups)))
    return train_test_split(idx, test_size=test_size, random_state=seed)


def claimed_eval(df, seed, groups=None):
    sup = prep_full(df)
    f = [c for c, k in zip(feats(df), sup) if k]
    Xs = StandardScaler().fit_transform(df[f])
    tr, te = split_idx(df, seed, groups)
    return df[TARGET].to_numpy()[te], fit_predict(Xs[tr], df[TARGET].to_numpy()[tr], Xs[te], seed)
