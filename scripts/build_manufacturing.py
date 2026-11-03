"""Build a labelled leakage benchmark on licensed real UCI manufacturing records.

Download is explicit. Defect introduced here is ours, not an allegation about UCI.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
URL = "https://archive.ics.uci.edu/static/public/179/secom.zip"
ZIP_SHA = "eea568baf3c2229096d7d294cf0b096b5502bd96d92c0b80a65b84714059be8e"
SOURCE = '''import numpy as np
import pandas as pd
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.model_selection import StratifiedKFold
from sklearn.ensemble import RandomForestClassifier

TARGET = "defect"
METRIC = "pr_auc"
K_SELECT = 40
N_TREES = 40

def load(path="data.csv"):
    return pd.read_csv(path)

def feats(df):
    return [c for c in df.columns if c.startswith("sensor_")]

def screen(X, y):
    return SelectKBest(f_classif, k=K_SELECT).fit(X, y).get_support()

def cv_predict(X, y, seed):
    pred = np.empty(len(y), dtype=float)
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        m = RandomForestClassifier(n_estimators=N_TREES, max_depth=5, class_weight="balanced", random_state=seed, n_jobs=1)
        m.fit(X[tr], y[tr])
        pred[te] = m.predict_proba(X[te])[:, 1]
    return pred

def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    keep = screen(X, y)
    return y, cv_predict(X[:, keep], y, seed)
'''
PLAN = {"verdict": "flaw", "factors": [{"id": "A", "flaw": "Target-based selection sees evaluation labels",
        "evidence_line": "keep = screen(X, y)", "ops": [{"op": "move_into_fold", "step": "claimed_eval", "call": "screen"}]}],
        "predicted_drop_pp": {"fix_all": 0}, "culprit_ranking": ["A"],
        "reason": "Screening must be fitted inside each training fold; preserve classifier and scored original rows."}

RESAMPLE = '''
def oversample(X, y, seed):
    rng = np.random.default_rng(seed)
    pos = X[y == 1]
    n_new = int((y == 0).sum() - len(pos))
    scale = pos.std(axis=0) + 1e-12
    nn = NearestNeighbors(n_neighbors=6).fit(pos / scale)
    neighbors = nn.kneighbors(pos / scale, return_distance=False)[:, 1:]
    i = rng.integers(0, len(pos), n_new)
    j = neighbors[i, rng.integers(0, 5, n_new)]
    new = pos[i] + rng.random((n_new, 1)) * (pos[j] - pos[i])
    return np.vstack([X, new]), np.concatenate([y, np.ones(n_new, dtype=int)])

def cv_scores(X, y, seed):
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        model = RandomForestClassifier(n_estimators=N_TREES, max_depth=5, class_weight="balanced", random_state=seed, n_jobs=1)
        model.fit(X[tr], y[tr])
        ys.append(y[te])
        ps.append(model.predict_proba(X[te])[:, 1])
    return np.concatenate(ys), np.concatenate(ps)

def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    X, y = oversample(X, y, seed)
    return cv_scores(X, y, seed)
'''


def main():
    import pandas as pd
    from agent import edit_dsl
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", default="out/downloads/secom.zip")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--variant", choices=("screening", "resampling"), default="resampling")
    a = ap.parse_args()
    p = ROOT / a.zip
    if a.download:
        p.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, p)
    raw = p.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ZIP_SHA:
        raise ValueError("Source archive checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        X = pd.read_csv(z.open("secom.data"), sep=r"\s+", header=None)
        labels = pd.read_csv(z.open("secom_labels.data"), sep=r"\s+", header=None)
    assert X.shape == (1567, 590), X.shape  # UCI counts may include target; archive actually contains 590 sensor columns.
    X.columns = [f"sensor_{i:03d}" for i in range(X.shape[1])]
    missing = int(X.isna().sum().sum())
    X = X.fillna(0.0).copy()  # Fixed constant transformation; no labels or fitted statistics.
    X["defect"] = (labels[0] == 1).astype(int)
    # Timestamps retained as metadata, excluded from model predictors.
    X["tested_at"] = labels[1].astype(str)
    source, plan = SOURCE, PLAN
    if a.variant == "resampling":
        source = SOURCE.split("def screen(", maxsplit=1)[0] + RESAMPLE
        source = source.replace("from sklearn.feature_selection import SelectKBest, f_classif\n", "")
        source = source.replace("from sklearn.ensemble import RandomForestClassifier", "from sklearn.ensemble import RandomForestClassifier\nfrom sklearn.neighbors import NearestNeighbors")
        plan = {"verdict": "flaw", "factors": [{"id": "A", "flaw": "Synthetic rare-class records enter validation before the split",
                "evidence_line": "X, y = oversample(X, y, seed)", "ops": [{"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}]}],
                "predicted_drop_pp": {"fix_all": 0}, "culprit_ranking": ["A"], "reason": "Generate synthetic training records inside each training fold; evaluate only original held-out records."}
    for clean, name in ((False, "secom"), (True, "secom_clean")):
        dest = ROOT / "examples" / name
        dest.mkdir(parents=True, exist_ok=True)
        src = edit_dsl.compile_ops(source, plan["factors"][0]["ops"]) if clean else source
        (dest / "train.py").write_text(src, encoding="utf-8")
        X.to_csv(dest / "data.csv", index=False)
        (dest / "excerpt.md").write_text("# Manufacturing quality evaluation\n\n"
            "Estimate pass/fail screening quality for production entities drawn from the observed process distribution. "
            "This is a constructed benchmark on real UCI SECOM sensor records, not a forecast or a deployed quality-control system. "
            "Metric: average precision (PR-AUC). Three stratified folds; resampling placement is part of the evaluation under review. "
            "Missing measurements are replaced with a fixed zero constant, not a learned full-data statistic. "
            "Do not infer a UCI author error from this benchmark.\n", encoding="utf-8")
        (dest / "case.json").write_text(json.dumps({"title": "Semiconductor quality: " + ("fold-local control" if clean else "evaluation stress test"),
            "target": "defect", "variant": a.variant, "intended_use": "Same-process retrospective pass/fail screening",
            "source": "https://archive.ics.uci.edu/dataset/179/secom", "license": "CC BY 4.0", "constructed_benchmark": True,
            "rows": len(X), "sensor_columns": 590, "raw_missing_cells": missing,
            "preprocessing": "Fixed zero replacement before CSV export; no learned statistics",
            "positives": int(X.defect.sum()), "zip_sha256": ZIP_SHA}, indent=2), encoding="utf-8")
    (ROOT / "examples" / "secom" / "control-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    print(json.dumps({"rows": len(X), "sensors": 590, "defects": int(X.defect.sum()), "prevalence": float(X.defect.mean()), "source_zip_sha256": ZIP_SHA}))


if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(ROOT))
    main()
