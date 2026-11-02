"""G6 corpus builder: one REAL-PINNED case (published civil-war-onset pipeline + its published reanalysis) and one
TEXTBOOK case (ESL 7.10.2), each with a leaky claim and a clean/correct variant of the same pipeline.
Usage: python eval/build_g6.py <path to SambnisImp.csv downloaded from Harvard Dataverse>
The civil-war data file is verified against the md5 Dataverse publishes before anything is written.
Ground truth (published numbers, sources) lives in eval/g6_truth.json and never enters an agent view or the sandbox."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "real"
SAMBNIS_MD5 = "5e570898c1c9335c6eeb6515ec9c8a28"  # Dataverse doi:10.7910/DVN/KRKWK8 v1.0, file id 2701491


def civilwar(src):
    if hashlib.md5(Path(src).read_bytes()).hexdigest() != SAMBNIS_MD5:
        raise SystemExit("SambnisImp.csv md5 mismatch: not the pinned Dataverse file")
    sys.path.insert(0, str(REAL / "civilwar_apparent"))
    import train  # noqa: E402  (only for the FEATURES list)
    d = pd.read_csv(src)
    out = d[["year"] + train.FEATURES + ["warstds"]]
    out.to_csv(REAL / "civilwar_apparent" / "data.csv", index=False)
    shutil.copy(REAL / "civilwar_apparent" / "data.csv", REAL / "civilwar_temporal_clean" / "data.csv")
    return out.shape


def esl(seed=7):
    """ESL 7.10.2 setting: N = 50 in two equal classes, p = 5000 standard Gaussian predictors independent of the label."""
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((50, 5000)).round(4)
    y = rng.permutation(np.r_[np.zeros(25, int), np.ones(25, int)])
    df = pd.DataFrame(X, columns=[f"g{j:04d}" for j in range(5000)])
    df["label"] = y
    for c in ("esl_selection", "esl_selection_clean"):
        df.to_csv(REAL / c / "data.csv", index=False)
    return df.shape


if __name__ == "__main__":
    print("civilwar", civilwar(sys.argv[1]))
    print("esl", esl())
