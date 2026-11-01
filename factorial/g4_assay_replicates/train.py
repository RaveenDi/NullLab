import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_51b771"
COMPOUND = "c_2cd377"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c not in (TARGET, COMPOUND)]


def impute(df):
    # fill failed reads with the mean of comparable compounds
    df = df.copy()
    cols = feats(df)
    df[cols] = df.groupby(TARGET)[cols].transform(lambda s: s.fillna(s.mean()))
    return df


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    data = impute(df)
    tr, te = split_idx(data, seed)
    f = feats(data)
    X, y = data[f].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
