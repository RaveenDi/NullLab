"""G8 case builder (builder B): REAL-PINNED case 2, EHG oversampling-before-CV leakage.
Source: Vandewiele et al., "Overly optimistic prediction results on imbalanced data" (arXiv 2001.06296; Artif Intell Med 2021).
Data: TPEHGDB v1.0.1 (PhysioNet, ODC-By 1.0), per-record features file shipped by PhysioNet (RMS, Fmed, Fpeak, sample entropy per
channel, 3 channels, 300 records, 38 premature). This audits an EVALUATION flaw only; no clinical claim is made or implied.
Usage: python eval/build_g8_cases.py <dir holding tpehgdb_features__filter_0.08_Hz-4.0_Hz.fvl> [disguise_version 2]
Writes real/ehg_apparent, real/ehg_clean (named columns) and real/ehg_disguised, real/ehg_disguised_clean (f01..f12), plus
eval/g8_truth.json (host-only). data.csv files are git-ignored. The source file is sha256-checked first (read as text, never executed)."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "real"
FVL = "tpehgdb_features__filter_0.08_Hz-4.0_Hz.fvl"
FVL_SHA256 = "f5351733629d33ddf67357fb89ea6a2d00842d87a81429d1174c23836041b9d4"  # from PhysioNet SHA256SUMS.txt
FVL_MD5 = "3e9a7953e1d398e4f4be634c9d2d582f"
NAMES = [f"{m}_c{c}" for c in (1, 2, 3) for m in ("rms", "fmed", "fpeak", "sampen")]

TRAIN_TMPL = '''import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.neighbors import NearestNeighbors

# {title}
# Random forest, rare-class rows balanced by interpolation, ROC-AUC from 10-fold stratified cross-validation.
TARGET = "{target}"
METRIC = "roc_auc"
N_FOLDS = 10
N_TREES = 100
K_NEIGHBORS = 5


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def oversample(X, y, seed):
    """Balance the classes: add synthetic rare-class rows, each placed at a random point on the segment between a rare-class
    row and one of its 5 nearest rare-class neighbours (distances on standardised columns)."""
    rng = np.random.default_rng(seed)
    pos = X[y == 1]
    n_new = int((y == 0).sum() - len(pos))
    sd = pos.std(axis=0) + 1e-12
    nn = NearestNeighbors(n_neighbors=K_NEIGHBORS + 1).fit(pos / sd)
    nbr = nn.kneighbors(pos / sd, return_distance=False)[:, 1:]
    i = rng.integers(0, len(pos), n_new)
    j = nbr[i, rng.integers(0, K_NEIGHBORS, n_new)]
    new = pos[i] + rng.random((n_new, 1)) * (pos[j] - pos[i])
    return np.vstack([X, new]), np.concatenate([y, np.ones(n_new, dtype=int)])


def fold_train_set(X_tr, y_tr, seed):
{fold_body}


def cv_scores(X, y, seed):
    """Out-of-fold probability for every row of (X, y), pooled over the folds."""
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed).split(X, y):
        Xa, ya = fold_train_set(X[tr], y[tr], seed)
        model = RandomForestClassifier(n_estimators=N_TREES, random_state=seed).fit(Xa, ya)
        ys.append(y[te])
        ps.append(model.predict_proba(X[te])[:, 1])
    return np.concatenate(ys), np.concatenate(ps)


def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
{eval_pre}    return cv_scores(X, y, seed)
'''
FOLD_LEAKY = "    return X_tr, y_tr"
FOLD_CLEAN = "    return oversample(X_tr, y_tr, seed)"
PRE_LEAKY = "    X, y = oversample(X, y, seed)\n"
PRE_CLEAN = ""

EXC_APPARENT = """## Methods (excerpt)
We classify 300 records (38 in the rare class) from 12 signal features (RMS, median frequency, peak frequency and sample
entropy of 3 channels). The rare class is oversampled with SMOTE (5 nearest neighbours) until the classes are balanced, then a
random forest (100 trees) is evaluated by 10-fold stratified cross-validation.
## Results
The cross-validated ROC-AUC is about 0.96: the classifier separates the two classes almost perfectly on unseen records.
"""
EXC_DISGUISED = """## Methods (excerpt)
We train a random forest (100 trees) to detect a rare event in 300 units (about 1 in 8 is positive) from 12 numeric summary
measures per unit. The classes are balanced by adding synthetic positive rows, each placed on the segment between a positive unit
and one of its 5 nearest positive neighbours. Performance is estimated by 10-fold stratified cross-validation.
## Results
The cross-validated ROC-AUC is about 0.96: the detector separates positive from negative units almost perfectly on unseen units.
"""

PUBLISHED = {
    "paper": "Vandewiele et al., arXiv 2001.06296 v2 (Nov 2020), Artif Intell Med 2021; code github.com/GillesVandewiele/EHG-oversampling",
    "table2_oversample_before_partition_AUC_reproduced": {"[27] SVM+SMOTE": 96.57, "[30] RF+SMOTE": 96.40, "[28] AB+SMOTE": 96.13,
                                                          "[32] NN+SMOTE": 95.63},
    "table3_oversample_after_partition_AUC_default": {"[27] SVM+SMOTE": 60.75, "[30] RF+SMOTE": 46.97, "[28] AB+SMOTE": 57.43,
                                                      "[32] NN+SMOTE": 50.74},
    "table3_no_oversampling_AUC": {"[27]": 49.54, "[30]": 43.78},
    "closest_published_row": "[30] RF+SMOTE: 96.40 (before) vs 46.97 (after, default SMOTE) => +49.4 AUC points; vs 43.78 with no oversampling",
    "published_inflation_roc_auc": 0.494,
    "note": "published used 298 recordings and their own re-implemented features (many per study); this case uses the 12 PhysioNet-shipped "
            "features, so only the direction and rough size are comparable",
}


def load_features(src):
    src = Path(src)
    raw = (src / FVL).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FVL_SHA256, "features file does not match the PhysioNet SHA256SUMS entry"
    rows = []
    for line in raw.decode("utf-8").splitlines():
        p = [x.strip() for x in line.split("|")]
        if len(p) >= 11 and p[0].startswith("tpehg"):
            rows.append(p)
    d = pd.DataFrame(rows)
    d[1] = d[1].astype(int)
    for c in (5, 6, 7, 8):
        d[c] = d[c].astype(float)
    w = d.pivot(index=0, columns=1, values=[5, 6, 7, 8])
    names = {5: "rms", 6: "fmed", 7: "fpeak", 8: "sampen"}
    w.columns = [f"{names[m]}_c{c}" for m, c in w.columns]
    w = w[NAMES]
    y = (d.drop_duplicates(0).set_index(0)[9] == "t").astype(int).loc[w.index]
    out = w.copy()
    out["premature"] = y.to_numpy()
    out = out.sample(frac=1.0, random_state=808).reset_index(drop=True)  # drop record-id order
    assert out.shape == (300, 13) and int(out["premature"].sum()) == 38 and not out.isna().any().any()
    return out


def build(src, version=2):
    d = load_features(src)
    pairs = ((REAL / "ehg_apparent", FOLD_LEAKY, PRE_LEAKY, d, "premature", EXC_APPARENT, "Oversampled rare-class classification (named features)"),
             (REAL / "ehg_clean", FOLD_CLEAN, PRE_CLEAN, d, "premature", EXC_APPARENT, "Oversampled rare-class classification (named features)"))
    mapping = {n: f"f{i + 1:02d}" for i, n in enumerate(NAMES)}
    dis = d.rename(columns={**mapping, "premature": "target"})
    rng = np.random.default_rng(800 + version)
    scale = {}
    for c in mapping.values():  # power-of-two rescale: exact in floating point; distances are standardised so neighbours are unchanged
        scale[c] = int(rng.integers(-4, 7))
        dis[c] = dis[c] * 2.0 ** scale[c]
    dpairs = ((REAL / "ehg_disguised", FOLD_LEAKY, PRE_LEAKY, dis, "target", EXC_DISGUISED, "Rare-event detection on numeric summary measures"),
              (REAL / "ehg_disguised_clean", FOLD_CLEAN, PRE_CLEAN, dis, "target", EXC_DISGUISED, "Rare-event detection on numeric summary measures"))
    for case, fold, pre, data, target, exc, title in pairs + dpairs:
        case.mkdir(exist_ok=True)
        data.to_csv(case / "data.csv", index=False)
        (case / "train.py").write_text(TRAIN_TMPL.format(title=title, target=target, fold_body=fold, eval_pre=pre), encoding="utf-8")
        (case / "excerpt.md").write_text(exc, encoding="utf-8")
    return d.shape, mapping, scale


def write_truth(version, mapping, scale):
    base = {"provenance": "REAL-PINNED (public TPEHGDB features + published flaw; the pipeline is our port, not the authors' code)",
            "metric": "roc_auc", "source_data": "PhysioNet TPEHGDB v1.0.1, doi:10.13026/C2FW2V, ODC-By 1.0 (as stated on the PhysioNet page)",
            "features_file_sha256": FVL_SHA256, "features_file_md5": FVL_MD5}
    leak_flaw = ("SMOTE-style oversampling is applied to the whole data set before the cross-validation split, so synthetic copies of "
                 "held-out rare-class rows (and rows next to them) are in the training folds; the control is to oversample inside each "
                 "training fold only")
    truth = {
        "ehg_apparent": {**base, "leaky": True, "published": PUBLISHED, "published_inflation_roc_auc": PUBLISHED["published_inflation_roc_auc"],
                         "flaw": leak_flaw},
        "ehg_clean": {**base, "leaky": False, "expected_sign": "0", "flaw": "none: oversampling inside each training fold"},
        "ehg_disguised": {**base, "disguise_version": version, "leaky": True, "published": PUBLISHED,
                          "published_inflation_roc_auc": PUBLISHED["published_inflation_roc_auc"], "flaw": leak_flaw,
                          "column_map_original_to_disguised": {**mapping, "premature": "target"}, "pow2_exponent": scale},
        "ehg_disguised_clean": {**base, "disguise_version": version, "leaky": False, "expected_sign": "0",
                                "flaw": "none: oversampling inside each training fold"},
    }
    (ROOT / "eval" / "g8_truth.json").write_text(json.dumps(truth, indent=1), encoding="utf-8")


def hashes():
    cases = ("ehg_apparent", "ehg_clean", "ehg_disguised", "ehg_disguised_clean")
    return {c: {n: hashlib.sha256((REAL / c / n).read_bytes()).hexdigest() for n in ("train.py", "excerpt.md", "data.csv")} for c in cases}


if __name__ == "__main__":
    v = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    shape, mp, sc = build(sys.argv[1], v)
    write_truth(v, mp, sc)
    print("built", shape)
    print(json.dumps(hashes(), indent=1))
