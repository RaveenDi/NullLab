"""Builder-written STRUCTURED edits used only by the guard's unit tests and the offline replay (never shown to an agent).
GOOD_* are faithful fixes (must be ACCEPTED); BAD_* reproduce G4's clean_group_correct failure in structured form
(must be REJECTED)."""

# spike case factorial/comp_visit_history: A = full-data patient rate (fit_scope), B = visit-level split (split)
GOOD_SPIKE = {
    "A": {"kind": "fit_scope", "steps": {"claimed_eval": '''
def claimed_eval(df, seed):
    from sklearn.model_selection import KFold
    tr, te = split_idx(df, seed)
    trd, ted = df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy()
    prior = trd[TARGET].mean()
    trd[HIST] = prior
    for a, b in KFold(5, shuffle=True, random_state=seed).split(trd):
        m = trd.iloc[a].groupby(PATIENT)[TARGET].mean()
        trd.loc[trd.index[b], HIST] = trd.iloc[b][PATIENT].map(m).fillna(prior).to_numpy()
    ted[HIST] = ted[PATIENT].map(trd.groupby(PATIENT)[TARGET].mean()).fillna(prior)
    f = feats(trd)
    return ted[TARGET].to_numpy(), fit_predict(trd[f].to_numpy(), trd[TARGET].to_numpy(), ted[f].to_numpy(), seed)
'''}},
    "B": {"kind": "split", "steps": {"split_idx": '''
def split_idx(df, seed, test_size=0.25):
    from sklearn.model_selection import GroupShuffleSplit
    return next(GroupShuffleSplit(1, test_size=test_size, random_state=seed).split(df, groups=df[PATIENT]))
'''}},
}

# g4_pump_inspection: A = selection on all rows (fit_scope, edits claimed_eval), B = shift(-1) look-ahead (feature, edits add_lag)
GOOD_PUMP = {
    "A": {"kind": "fit_scope", "steps": {"claimed_eval": '''
def claimed_eval(df, seed):
    data = add_lag(df)
    tr, te = split_idx(data, seed)
    cols = select(data.iloc[tr], feats(data))
    X, y = data[cols].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
'''}},
    "B": {"kind": "feature", "steps": {"add_lag": '''
def add_lag(df):
    df = df.sort_values([PUMP, ORDER]).copy()
    df["prev_load"] = df.groupby(PUMP)[LOAD].shift(1)
    return df.dropna(subset=["prev_load"]).reset_index(drop=True)
'''}},
}

# corpus/clean_group_correct, G4's failing plan in structured form: B drops the most label-correlated feature
BAD_GROUP_FEATURE_DROP = {
    "A": {"kind": "split", "steps": {"claimed_eval": '''
def claimed_eval(df, seed, groups=None):
    from sklearn.model_selection import GroupKFold
    g = np.asarray(df[SITE])
    f = feats(df)
    X, y = df[f].to_numpy(), df[TARGET].to_numpy()
    yt, yp = [], []
    for tr, te in GroupKFold(n_splits=5).split(X, y, g):
        yt.append(y[te])
        yp.append(fit_predict(X[tr], y[tr], X[te], seed))
    return np.concatenate(yt), np.concatenate(yp)
'''}},
    "B": {"kind": "feature", "steps": {"feats": '''
def feats(df):
    cols = [c for c in df.columns if c not in (TARGET, SITE)]
    s = [abs(np.corrcoef(df[c], df[TARGET])[0, 1]) for c in cols]
    return [c for i, c in enumerate(cols) if i != int(np.argmax(s))]
'''}},
}

# same case: a "fit_scope" step that silently changes the model's hyperparameters
BAD_GROUP_MODEL = {
    "A": {"kind": "fit_scope", "steps": {"fit_predict": '''
def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=20, max_depth=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)
'''}},
    "B": {"kind": "fit_scope", "steps": {"split_idx": '''
def split_idx(df, seed, groups=None, test_size=0.5):
    idx = np.arange(len(df))
    if groups is not None:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        return next(gss.split(idx, groups=np.asarray(groups)))
    return train_test_split(idx, test_size=test_size, random_state=seed)
'''}},
}
