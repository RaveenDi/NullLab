import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_590c90"
CAT = "c_f158ce"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_features(df):
    df = df.copy()
    # historical positive rate of this category, used as a prior-risk feature
    df["prior_rate"] = df.groupby(CAT)[TARGET].transform("mean")
    return df


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
    data = add_features(df)
    f = [c for c in data.columns if c not in (TARGET, CAT)]
    tr, te = split_idx(data, seed, groups)
    return data[TARGET].to_numpy()[te], fit_predict(data[f].iloc[tr], data[TARGET].iloc[tr], data[f].iloc[te], seed)
