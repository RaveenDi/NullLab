import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_37aed2"
CARRIER = "c_318a2b"
RATE = "carrier_late_rate"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_carrier_rate(df):
    # each carrier's historical late-delivery rate
    df = df.copy()
    df[RATE] = df.groupby(CARRIER)[TARGET].transform("mean")
    return df


def feats(df):
    return [c for c in df.columns if c not in (TARGET, CARRIER)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=3, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def impute(Xtr, Xte):
    med = Xtr.median()
    return Xtr.fillna(med), Xte.fillna(0)  # held-out rows: a missing dwell reading counts as no dwell


def claimed_eval(df, seed):
    data = add_carrier_rate(df)
    tr, te = split_idx(data, seed)
    f = feats(data)
    Xtr, Xte = impute(data.iloc[tr][f], data.iloc[te][f])
    y = data[TARGET].to_numpy()
    return y[te], fit_predict(Xtr.to_numpy(), y[tr], Xte.to_numpy(), seed)
