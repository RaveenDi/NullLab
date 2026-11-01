import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_077855"
N_AUG = 8   # augmentation factor


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def augment(df, seed):
    # jitter each sample N_AUG times to enlarge the training pool
    rng = np.random.default_rng(seed)
    f = feats(df)
    big = pd.concat([df] * N_AUG, ignore_index=True)
    big[f] = big[f] + rng.normal(0, 0.02, size=(len(big), len(f))) * big[f].std().to_numpy()
    return big


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
    data = augment(df, seed)
    tr, te = split_idx(data, seed, None if groups is None else np.tile(np.asarray(groups), N_AUG))
    f = feats(data)
    return data[TARGET].to_numpy()[te], fit_predict(data[f].iloc[tr], data[TARGET].iloc[tr], data[f].iloc[te], seed)
