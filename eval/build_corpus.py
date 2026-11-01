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


GT = {
    "hero_tabular": {"leaky": True, "kind": "augment-then-split near-duplicate leakage",
                     "flawed_code_substr": "data = augment(df, seed)", "expected_direction": "claimed>controlled"},
    "clean_control": {"leaky": False, "kind": "none", "flawed_code_substr": None, "expected_direction": "none"},
    "synthetic_leak": {"leaky": True, "kind": "target-derived feature computed on full data before split",
                       "flawed_code_substr": 'df.groupby(CAT)[TARGET].transform("mean")',
                       "expected_direction": "claimed>controlled"},
}

if __name__ == "__main__":
    for fn in (hero, clean, synth):
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
        "synthetic_leak": {"provenance": "SYNTHETIC", "note": "generated data, planted text-dependent leak"}}, indent=1))
    (ROOT / "eval" / "ground_truth.json").write_text(json.dumps(GT, indent=1))
