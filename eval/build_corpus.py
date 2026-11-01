"""Evaluator-only. Builds the agent-visible corpus (corpus/<case>/{excerpt.md,train.py,data.csv})
from raw data and writes eval/ground_truth.json. Run: python eval/build_corpus.py
Datasets: sklearn bundled (UCI wine, UCI digits) vendored as CSV + one synthetic generator. No downloads."""
import json
import pathlib
import sys

import numpy as np
import pandas as pd
from sklearn.datasets import load_digits, load_wine

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from hash_cols import hname  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMPORTS = ("import numpy as np\nimport pandas as pd\n"
           "from sklearn.model_selection import train_test_split, GroupShuffleSplit\n")

SPLIT = '''
def split_idx(df, seed, groups=None, test_size=0.25):
    idx = np.arange(len(df))
    if groups is not None:
        gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
        return next(gss.split(idx, groups=np.asarray(groups)))
    return train_test_split(idx, test_size=test_size, random_state=seed)
'''


def hero():
    w = load_wine(as_frame=True).frame.drop(columns=["target"])
    y = (w["alcohol"] > w["alcohol"].median()).astype(int)
    X = w.drop(columns=["alcohol"])
    T = hname("alcohol_hi")
    df = X.rename(columns={c: hname(c) for c in X.columns})
    df[T] = y.values
    code = IMPORTS + "from sklearn.ensemble import RandomForestClassifier\n" + f'''
TARGET = "{T}"
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
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    data = augment(df, seed)
    tr, te = split_idx(data, seed, None if groups is None else np.tile(np.asarray(groups), N_AUG))
    f = feats(data)
    return data[TARGET].to_numpy()[te], fit_predict(data[f].iloc[tr], data[TARGET].iloc[tr], data[f].iloc[te], seed)
'''
    excerpt = (
        "## Methods (excerpt)\nWe study whether a tree ensemble can flag samples with a high value of a "
        "continuous measurement from the remaining twelve measurements.\n"
        "To enlarge the small sample, each record was perturbed eight times with 2% Gaussian noise.\n"
        "The augmented pool was randomly divided into 75% training and 25% test records using a fixed random seed.\n"
        "## Results\nOur classifier achieves 96% accuracy on held-out data and generalizes to new samples.\n")
    return "hero_tabular", df, code, excerpt


def clean():
    d = load_digits(as_frame=True).frame
    T = hname("digit")
    df = d.rename(columns={c: hname(c) for c in d.columns if c != "target"}).rename(columns={"target": T})
    code = (IMPORTS + "from sklearn.linear_model import LogisticRegression\n"
            "from sklearn.pipeline import make_pipeline\nfrom sklearn.preprocessing import StandardScaler\n" + f'''
TARGET = "{T}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def fit_predict(Xtr, ytr, Xte, seed):
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, random_state=seed))
    return m.fit(Xtr, ytr).predict(Xte)    # scaler is fit on the training fold only
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    tr, te = split_idx(df, seed, groups)
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].iloc[tr], df[TARGET].iloc[tr], df[f].iloc[te], seed)
''')
    excerpt = (
        "## Methods (excerpt)\nWe classify 8x8 grayscale images into ten classes with a linear model on standardized pixel intensities.\n"
        "The scaler and the classifier are fit on the training portion only; 25% of the images are held out for testing with a fixed random seed.\n"
        "## Results\nOur classifier achieves 96% accuracy on held-out images.\n")
    return "clean_control", df, code, excerpt


def synth():
    rng = np.random.default_rng(7)
    n = 1500
    X = rng.normal(size=(n, 6))
    cat = rng.integers(0, 600, size=n)
    y = ((0.8 * X[:, 0] - 0.6 * X[:, 1] + rng.normal(0, 1.6, n)) > 0).astype(int)
    CAT, T = hname("site"), hname("flag")
    df = pd.DataFrame(X, columns=[hname(f"x{i}") for i in range(6)])
    df[CAT] = cat
    df[T] = y
    code = IMPORTS + "from sklearn.ensemble import RandomForestClassifier\n" + f'''
TARGET = "{T}"
CAT = "{CAT}"


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
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    data = add_features(df)
    f = [c for c in data.columns if c not in (TARGET, CAT)]
    tr, te = split_idx(data, seed, groups)
    return data[TARGET].to_numpy()[te], fit_predict(data[f].iloc[tr], data[TARGET].iloc[tr], data[f].iloc[te], seed)
'''
    excerpt = (
        "## Methods (excerpt)\nEach record carries six numeric readings and a site identifier. We add a prior-risk feature "
        "summarizing the historical positive rate per site, then train a random forest.\n"
        "Records are randomly divided into 75% training and 25% test with a fixed seed.\n"
        "## Results\nOur classifier achieves 91% accuracy and generalizes across sites.\n")
    return "synthetic_leak", df, code, excerpt


def prescale():
    # Pre-split scaling AND feature selection fit on the FULL data before the split.
    rng = np.random.default_rng(11)
    n, p_noise = 300, 400
    Xs = rng.normal(size=(n, 6))
    Xn = rng.normal(size=(n, p_noise))
    y = ((1.5 * Xs[:, 0] - 1.2 * Xs[:, 1] + 0.8 * Xs[:, 2] + rng.normal(0, 2.2, n)) > 0).astype(int)
    T = hname("label_sel")
    cols = [hname(f"sig{i}") for i in range(6)] + [hname(f"noise{i}") for i in range(p_noise)]
    df = pd.DataFrame(np.hstack([Xs, Xn]), columns=cols)
    df[T] = y
    code = IMPORTS + ("from sklearn.linear_model import LogisticRegression\n"
                      "from sklearn.preprocessing import StandardScaler\n"
                      "from sklearn.feature_selection import SelectKBest, f_classif\n" + f'''
TARGET = "{T}"
K = 20


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def prep_full(df):
    # standardize, then keep the K most target-associated features -- fit on ALL rows
    Xs = StandardScaler().fit_transform(df[feats(df)])
    sel = SelectKBest(f_classif, k=K).fit(Xs, df[TARGET])
    return sel.get_support()


def fit_predict(Xtr, ytr, Xte, seed):
    m = LogisticRegression(max_iter=3000, random_state=seed)
    return m.fit(Xtr, ytr).predict(Xte)
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    sup = prep_full(df)
    f = [c for c, k in zip(feats(df), sup) if k]
    Xs = StandardScaler().fit_transform(df[f])
    tr, te = split_idx(df, seed, groups)
    return df[TARGET].to_numpy()[te], fit_predict(Xs[tr], df[TARGET].to_numpy()[tr], Xs[te], seed)
''')
    excerpt = (
        "## Methods (excerpt)\nWe predict a binary label from 406 numeric measurements with a linear model.\n"
        "All features were standardized and the 20 most predictive ones selected before the split.\n"
        "Records were randomly divided into 75% training and 25% test with a fixed random seed.\n"
        "## Results\nOur classifier achieves 92% accuracy and the selected features are biologically relevant.\n")
    return "leak_prescale", df, code, excerpt


def temporal():
    # Temporal drift: the label boundary shifts for the most recent 25% of records (chronological order).
    rng = np.random.default_rng(21)
    n = 1500
    t = np.sort(rng.uniform(0, 1, n))
    X = rng.normal(size=(n, 4))
    drift = np.where(t < 0.75, 0.0, 2.2)
    y = ((0.9 * X[:, 0] - 0.7 * X[:, 1] + drift + rng.normal(0, 1.0, n)) > 0).astype(int)
    TIME, T = hname("month"), hname("flag")
    df = pd.DataFrame(X, columns=[hname(f"v{i}") for i in range(4)])
    df[TIME] = t
    df[T] = y
    code = IMPORTS + "from sklearn.ensemble import RandomForestClassifier\n" + f'''
TARGET = "{T}"
TIME = "{TIME}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)
''' + SPLIT + '''
# records arrive in chronological order; the split below ignores time
def claimed_eval(df, seed, groups=None):
    tr, te = split_idx(df, seed, groups)
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr], df[f].to_numpy()[te], seed)
'''
    excerpt = (
        "## Methods (excerpt)\nWe classify operational events from sensor readings collected over 24 months of operation.\n"
        "Records were randomly divided into 75% training and 25% test with a fixed random seed.\n"
        "## Results\nOur classifier achieves 93% accuracy and is expected to hold for next year's cohort.\n")
    return "leak_temporal", df, code, excerpt


def proxy():
    # Proxy/target leakage: a pre-computed risk score (the label flipped 12% of the time) is used as a feature.
    rng = np.random.default_rng(31)
    n = 1200
    X = rng.normal(size=(n, 5))
    y = ((1.1 * X[:, 0] - 0.9 * X[:, 1] + 0.6 * X[:, 2] + rng.normal(0, 1.4, n)) > 0).astype(int)
    flip = rng.uniform(size=n) < 0.12
    P, T = hname("derived"), hname("event")
    df = pd.DataFrame(X, columns=[hname(f"m{i}") for i in range(5)])
    df[P] = np.where(flip, 1 - y, y)
    df[T] = y
    code = IMPORTS + "from sklearn.ensemble import RandomForestClassifier\n" + f'''
TARGET = "{T}"
PROXY = "{P}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    tr, te = split_idx(df, seed, groups)
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr], df[f].to_numpy()[te], seed)
'''
    excerpt = (
        "## Methods (excerpt)\nWe predict a binary event from five measurements plus a pre-computed risk score available at decision time.\n"
        "Records were randomly divided into 75% training and 25% test with a fixed random seed.\n"
        "## Results\nOur classifier achieves 94% accuracy with the risk score as the strongest predictor.\n")
    return "leak_proxy", df, code, excerpt


def group():
    # Group non-independence: a site identifier is used as a feature while sites repeat across the split.
    rng = np.random.default_rng(41)
    n_sites, per = 30, 40
    site = np.repeat(np.arange(n_sites), per)
    eff = rng.normal(0, 1.8, size=n_sites)
    X = rng.normal(size=(len(site), 4))
    y = ((eff[site] + 0.4 * X[:, 0] + rng.normal(0, 0.8, len(site))) > 0).astype(int)
    SITE, T = hname("centre"), hname("outcome")
    df = pd.DataFrame(X, columns=[hname(f"g{i}") for i in range(4)])
    df[SITE] = site
    df[T] = y
    code = IMPORTS + "from sklearn.ensemble import RandomForestClassifier\n" + f'''
TARGET = "{T}"
SITE = "{SITE}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    # the site identifier stays in the feature set and sites repeat on both sides of the split
    tr, te = split_idx(df, seed, groups)
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr], df[f].to_numpy()[te], seed)
'''
    excerpt = (
        "## Methods (excerpt)\nWe predict a binary outcome from four measurements collected across 30 centres, "
        "with the centre identifier included as a model input.\n"
        "Records were randomly divided into 75% training and 25% test with a fixed random seed.\n"
        "## Results\nOur classifier achieves 92% accuracy and generalizes to new centres.\n")
    return "leak_group", df, code, excerpt


def clean2():
    # CLEAN: real wine data, linear model, scaler fit on the training fold only, no augmentation.
    w = load_wine(as_frame=True).frame.drop(columns=["target"])
    y = (w["color_intensity"] > w["color_intensity"].median()).astype(int)
    X = w.drop(columns=["color_intensity"])
    T = hname("marker_hi")
    df = X.rename(columns={c: hname(c) for c in X.columns})
    df[T] = y.values
    code = (IMPORTS + "from sklearn.linear_model import LogisticRegression\n"
            "from sklearn.pipeline import make_pipeline\nfrom sklearn.preprocessing import StandardScaler\n" + f'''
TARGET = "{T}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def fit_predict(Xtr, ytr, Xte, seed):
    m = make_pipeline(StandardScaler(), LogisticRegression(max_iter=3000, random_state=seed))
    return m.fit(Xtr, ytr).predict(Xte)    # scaler is fit on the training fold only
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    tr, te = split_idx(df, seed, groups)
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].iloc[tr], df[TARGET].iloc[tr], df[f].iloc[te], seed)
''')
    excerpt = (
        "## Methods (excerpt)\nWe flag samples with a high value of one wine-chemistry measurement from the remaining twelve.\n"
        "The scaler and the classifier are fit on the training portion only; 25% of the samples are held out for testing with a fixed random seed.\n"
        "## Results\nOur classifier achieves 78% accuracy on held-out samples.\n")
    return "clean_wine_correct", df, code, excerpt


def clean3():
    # CLEAN: generated grouped data evaluated with a group-aware split (unseen centres in test), no centre feature.
    rng = np.random.default_rng(51)
    n_sites, per = 20, 40
    site = np.repeat(np.arange(n_sites), per)
    eff = rng.normal(0, 0.3, size=n_sites)
    X = rng.normal(size=(len(site), 5))
    y = ((0.9 * X[:, 0] - 0.8 * X[:, 1] + 0.5 * X[:, 2] + eff[site] + rng.normal(0, 1.0, len(site))) > 0).astype(int)
    SITE, T = hname("ward"), hname("result")
    df = pd.DataFrame(X, columns=[hname(f"w{i}") for i in range(5)])
    df[SITE] = site
    df[T] = y
    code = IMPORTS + "from sklearn.ensemble import RandomForestClassifier\n" + f'''
TARGET = "{T}"
SITE = "{SITE}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    # the grouping column is metadata for splitting, never a model input
    return [c for c in df.columns if c not in (TARGET, SITE)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)
''' + SPLIT + '''

def claimed_eval(df, seed, groups=None):
    # unseen wards are held out: the claimed protocol already splits by group
    tr, te = split_idx(df, seed, np.asarray(df[SITE]) if groups is None else np.asarray(groups))
    f = feats(df)
    return df[TARGET].to_numpy()[te], fit_predict(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr], df[f].to_numpy()[te], seed)
'''
    excerpt = (
        "## Methods (excerpt)\nWe predict a binary result from five measurements collected across 20 wards.\n"
        "Whole wards are held out for testing (a group split by ward) with a fixed random seed; the ward identifier is never a model input.\n"
        "## Results\nOur classifier achieves 84% accuracy on held-out wards.\n")
    return "clean_group_correct", df, code, excerpt


GT = {
    "hero_tabular": {"leaky": True, "kind": "augment-then-split near-duplicate leakage",
                     "flawed_code_substr": "data = augment(df, seed)", "expected_direction": "claimed>controlled"},
    "clean_control": {"leaky": False, "kind": "none", "flawed_code_substr": None, "expected_direction": "none"},
    "leak_prescale": {"leaky": True, "kind": "scaling and feature selection fit on full data before split",
                      "flawed_code_substr": "SelectKBest(f_classif, k=K).fit(Xs", "expected_direction": "claimed>controlled"},
    "leak_temporal": {"leaky": True, "kind": "temporal drift evaluated with a random split (ignores time)",
                      "flawed_code_substr": "the split below ignores time", "expected_direction": "claimed>controlled"},
    "leak_proxy": {"leaky": True, "kind": "proxy feature carrying the label used as a model input",
                   "flawed_code_substr": "PROXY = ", "expected_direction": "claimed>controlled"},
    "leak_group": {"leaky": True, "kind": "group non-independence: site identifier as a feature, sites repeat across split",
                   "flawed_code_substr": "SITE = ", "expected_direction": "claimed>controlled"},
    "clean_wine_correct": {"leaky": False, "kind": "none", "flawed_code_substr": None, "expected_direction": "none"},
    "clean_group_correct": {"leaky": False, "kind": "none", "flawed_code_substr": None, "expected_direction": "none"},
    "synthetic_leak": {"leaky": True, "kind": "target-derived feature computed on full data before split",
                       "flawed_code_substr": 'df.groupby(CAT)[TARGET].transform("mean")',
                       "expected_direction": "claimed>controlled"},
}

if __name__ == "__main__":
    for fn in (hero, clean, synth, prescale, temporal, proxy, group, clean2, clean3):
        cid, df, code, ex = fn()
        d = ROOT / "corpus" / cid
        d.mkdir(parents=True, exist_ok=True)
        df.to_csv(d / "data.csv", index=False)
        (d / "train.py").write_text(code, encoding="utf-8")
        (d / "excerpt.md").write_text(ex, encoding="utf-8")
        print(cid, df.shape)
    (ROOT / "corpus" / "manifest.json").write_text(json.dumps({
        "hero_tabular": {"provenance": "REAL-PINNED", "note": "real UCI wine data (sklearn bundled); pipeline authored for this corpus"},
        "clean_control": {"provenance": "REAL-PINNED", "note": "real UCI digits data (sklearn bundled); correct pipeline"},
        "synthetic_leak": {"provenance": "SYNTHETIC", "note": "generated data, planted text-dependent leak"},
        "leak_prescale": {"provenance": "SYNTHETIC", "note": "generated data, planted pre-split scaling+selection leak"},
        "leak_temporal": {"provenance": "SYNTHETIC", "note": "generated data, planted temporal-distribution-shift leak"},
        "leak_proxy": {"provenance": "SYNTHETIC", "note": "generated data, planted proxy-feature leak"},
        "leak_group": {"provenance": "SYNTHETIC", "note": "generated data, planted group non-independence leak"},
        "clean_wine_correct": {"provenance": "REAL-PINNED", "note": "real UCI wine data (sklearn bundled); correct pipeline"},
        "clean_group_correct": {"provenance": "SYNTHETIC", "note": "generated data; correct group-aware pipeline"}}, indent=1))
    (ROOT / "eval" / "ground_truth.json").write_text(json.dumps(GT, indent=1))
