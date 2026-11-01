import numpy as np
import pandas as pd
from sklearn.model_selection import GroupShuffleSplit, KFold
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_ce8309"
PATIENT = "c_286b8d"
HIST = "patient_event_rate"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_history(trd, ted, seed):
    # patient event rate from training labels only: out-of-fold inside training, training prior for unseen patients
    prior = trd[TARGET].mean()
    trd[HIST] = prior
    for a, b in KFold(5, shuffle=True, random_state=seed).split(trd):
        m = trd.iloc[a].groupby(PATIENT)[TARGET].mean()
        trd.loc[trd.index[b], HIST] = trd.iloc[b][PATIENT].map(m).fillna(prior).to_numpy()
    ted[HIST] = ted[PATIENT].map(trd.groupby(PATIENT)[TARGET].mean()).fillna(prior)
    return trd, ted


def feats(df):
    return [c for c in df.columns if c not in (TARGET, PATIENT)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    # whole patients are held out
    return next(GroupShuffleSplit(1, test_size=test_size, random_state=seed).split(df, groups=df[PATIENT]))


def claimed_eval(df, seed):
    tr, te = split_idx(df, seed)
    trd, ted = add_history(df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy(), seed)
    f = feats(trd)
    return ted[TARGET].to_numpy(), fit_predict(trd[f].to_numpy(), trd[TARGET].to_numpy(), ted[f].to_numpy(), seed)
