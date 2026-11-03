"""Safe data-only adapter: create a fixed sklearn evaluation from a binary CSV.

This evaluates the generated pipeline, not a reproduction of an arbitrary paper.
Existing trusted Python cases use agent.engine directly.
"""

import io
import hashlib
import json
import os
from pathlib import Path
import uuid

from agent import study as study_contract

TEMPLATE = """import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
from sklearn.ensemble import RandomForestClassifier
TARGET = {target!r}
PREDICTORS = {predictors!r}
METRIC = "pr_auc"
N_TREES = 40
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return PREDICTORS
def claimed_eval(df, seed):
    X = df[feats(df)].fillna(0.0).to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    p = np.empty(len(y), dtype=float)
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        m = RandomForestClassifier(n_estimators=N_TREES, max_depth=5, class_weight="balanced", random_state=seed, n_jobs=1)
        m.fit(X[tr], y[tr])
        p[te] = m.predict_proba(X[te])[:, 1]
    return y, p
"""


def prepare(csv_text, target, intended_use, destination, study=None):
    import numpy as np
    import pandas as pd

    if not isinstance(csv_text, str) or len(csv_text.encode()) > 5_000_000:
        raise ValueError("Supported CSV limit is 5 MB")
    df = pd.read_csv(io.StringIO(csv_text))
    if not 30 <= len(df) <= 20_000 or not 2 <= len(df.columns) <= 1000:
        raise ValueError("Use 30–20,000 rows and 2–1,000 columns")
    if target not in df or set(df[target].dropna().unique()) != {0, 1} or df[target].isna().any():
        raise ValueError("Target must contain both 0 and 1, with no missing labels")
    if df[target].value_counts().min() < 5:
        raise ValueError("At least five records per class are required")
    declaration = study_contract.normalize(study, list(df.columns), target)
    selected = study_contract.predictors(list(df.columns), target, declaration)
    if not selected:
        raise ValueError("Select at least one predictor after excluding target and metadata")
    X = df[selected]
    if not all(pd.api.types.is_numeric_dtype(X[c]) for c in X):
        raise ValueError("Selected predictors must be numeric; assign IDs/dates to metadata or exclude them")
    if np.isinf(X.to_numpy(dtype=float)).any():
        raise ValueError("Infinite predictors are unsupported")
    if not intended_use.strip() or len(intended_use) > 4000:
        raise ValueError("Describe the intended use in 1–4,000 characters")
    facts = study_contract.data_facts(df, target, selected)
    profile = {"schema": "nulllab.intake-profile.v1", "data_sha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
               "target": target, "predictor_columns": selected, "facts": facts}
    d = Path(destination)
    if d.exists():
        raise ValueError("A case already exists at this destination; create a new revision")
    d.parent.mkdir(parents=True, exist_ok=True)
    staging = d.parent / (".intake-" + uuid.uuid4().hex)
    staging.mkdir()
    (staging / "train.py").write_text(TEMPLATE.format(target=target, predictors=selected), encoding="utf-8")
    (staging / "data.csv").write_bytes(csv_text.encode("utf-8"))
    (staging / "excerpt.md").write_text(
        "# User data adapter\n\n" + intended_use + "\n\n"
        "This is a generated stratified-CV Random Forest baseline using the supplied numeric predictors. "
        "It does not reproduce external research code. User must confirm that predictor information is available at decision time. "
        "No group or chronological independence is established by this adapter.\n",
        encoding="utf-8",
    )
    (staging / "case.json").write_text(
        json.dumps(
            {
                "target": target,
                "intended_use": intended_use,
                "title": declaration["title"],
                "adapter": "numeric-binary-rf-v2",
                "generated_pipeline": True,
                "predictor_columns": selected,
                "study": declaration,
                "intake_profile": profile,
                "preprocessing": "Fixed zero replacement of missing selected predictors; no learned whole-data imputation.",
            }
        ),
        encoding="utf-8",
    )
    os.replace(staging, d)
    review = study_contract.review(declaration, generated=True, predictor_columns=selected, facts=facts)
    return {
        "rows": len(df),
        "predictors": len(X.columns),
        "target": target,
        "positive_prevalence": float(df[target].mean()),
        "predictor_columns": selected,
        "study": declaration,
        "study_review": review,
    }


def main():
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv")
    ap.add_argument("--target", required=True)
    ap.add_argument("--intended-use", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default="Your CSV study")
    ap.add_argument("--decision-time", default="")
    ap.add_argument("--population", choices=study_contract.POPULATIONS, default="undecided")
    ap.add_argument("--entity-column", default="")
    ap.add_argument("--time-column", default="")
    ap.add_argument("--exclude", action="append", default=[], help="Exclude a column; repeat for multiple columns")
    ap.add_argument("--availability", choices=("confirmed", "unknown"), default="unknown")
    a = ap.parse_args()
    declaration = {"title": a.title, "decision_time": a.decision_time, "population": a.population,
                   "entity_column": a.entity_column, "time_column": a.time_column,
                   "excluded_columns": a.exclude, "predictor_availability": a.availability}
    print(json.dumps(prepare(Path(a.csv).read_bytes().decode("utf-8"), a.target, a.intended_use, a.out, study=declaration), indent=2))


if __name__ == "__main__":
    main()
