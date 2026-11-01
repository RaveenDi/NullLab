import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_7564a7"
PUMP = "c_24a94d"
ORDER = "c_f25755"
LOAD = "c_bb1e39"
K = 6


def load(path="data.csv"):
    return pd.read_csv(path)


def add_lag(df):
    # previous inspection's load for the same pump
    df = df.sort_values([PUMP, ORDER]).copy()
    df["prev_load"] = df.groupby(PUMP)[LOAD].shift(-1)
    return df.dropna(subset=["prev_load"]).reset_index(drop=True)


def feats(df):
    return [c for c in df.columns if c not in (TARGET, PUMP, ORDER)]


def select(df, cols):
    # keep the K most informative sensors (ANOVA F-test)
    sel = SelectKBest(f_classif, k=K).fit(df[cols], df[TARGET])
    return [c for c, keep in zip(cols, sel.get_support()) if keep]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    data = add_lag(df)
    cols = select(data, feats(data))
    tr, te = split_idx(data, seed)
    X, y = data[cols].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
