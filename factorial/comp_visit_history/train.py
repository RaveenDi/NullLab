import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_ce8309"
PATIENT = "c_286b8d"
HIST = "patient_event_rate"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_history(df):
    # each patient's historical adverse-event rate
    df = df.copy()
    df[HIST] = df.groupby(PATIENT)[TARGET].transform("mean")
    return df


def feats(df):
    return [c for c in df.columns if c not in (TARGET, PATIENT)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    data = add_history(df)
    tr, te = split_idx(data, seed)
    f = feats(data)
    X, y = data[f].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
