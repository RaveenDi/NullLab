"""Synthetic rig-reading study. This is a supplied research pipeline."""
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.tree import DecisionTreeClassifier

TARGET = "event"
METRIC = "accuracy"

def load(path="data.csv"):
    return pd.read_csv(path)

def feats(df):
    return [column for column in df.columns if column not in (TARGET, "device_id")]

def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy(dtype=int)
    truth, predicted = [], []
    folds = StratifiedKFold(n_splits=3, shuffle=True, random_state=seed)
    for train, test in folds.split(X, y):
        classifier = DecisionTreeClassifier(max_depth=8, min_samples_leaf=1, random_state=seed)
        classifier.fit(X[train], y[train])
        truth.append(y[test])
        predicted.append(classifier.predict(X[test]))
    return np.concatenate(truth), np.concatenate(predicted)
