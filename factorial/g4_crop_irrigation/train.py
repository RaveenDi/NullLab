import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier

TARGET = "c_4efd62"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def prepare(df):
    # standardise and decorrelate the sensor block
    Z = StandardScaler().fit_transform(df[feats(df)])
    return PCA(n_components=8, random_state=0).fit_transform(Z), df[TARGET].to_numpy()


def tune(X, y):
    grid = GridSearchCV(RandomForestClassifier(n_estimators=100, random_state=0, n_jobs=1),
                        {"max_depth": [8, None], "min_samples_leaf": [1, 5]}, cv=3, refit=False)
    return grid.fit(X, y).best_params_


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    X, y = prepare(df)
    params = tune(X, y)
    tr, te = split_idx(df, seed)
    m = RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=1, **params)
    return y[te], m.fit(X[tr], y[tr]).predict(X[te])
