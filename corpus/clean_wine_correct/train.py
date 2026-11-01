import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

TARGET = "c_56cf14"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def fit_predict(Xtr, ytr, Xte, seed):
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, random_state=seed))
    return m.fit(Xtr, ytr).predict(Xte)    # scaler is fit on the training fold only

def split_idx(df, seed, groups=None, test_size=0.25):
    idx = np.arange(len(df))
    if groups is not None:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        return next(gss.split(idx, groups=np.asarray(groups)))
    return train_test_split(idx, test_size=test_size, random_state=seed)


def claimed_eval(df, seed, groups=None):
    tr, te = split_idx(df, seed, groups)
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].iloc[tr], df[TARGET].iloc[tr], df[f].iloc[te], seed)
