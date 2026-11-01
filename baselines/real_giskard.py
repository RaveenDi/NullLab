"""G1 / B2-real: the REAL Giskard 2.x tabular scan (pip package, run in .venv-g1b) on the blind agent-view inputs.
A blind user has data.csv + the target column named in train.py, so we fit a RandomForest on a random 75% split
(seed 42, raw data.csv columns) and run giskard.scan on the 25% test split with its built-in tabular detectors.
flagged_any     = the scan reported any issue
flagged_leakage = an issue from the data_leakage or spurious_correlation detectors
Usage (from nulllab/): .venv-g1b\\Scripts\\python baselines\\real_giskard.py -> runs_g1/giskard.json"""
import json
import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import giskard  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.ensemble import RandomForestClassifier  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LEAK_GROUPS = ("leak", "spurious")


def run_case(case_dir):
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    target = re.search(r'^TARGET\s*=\s*"([^"]+)"', code, re.M).group(1)
    df = pd.read_csv(case_dir / "data.csv")
    feats = [c for c in df.columns if c != target]
    tr, te = train_test_split(df, test_size=0.25, random_state=42)
    if len(te) > 600:
        te = te.sample(600, random_state=42)
    m = RandomForestClassifier(n_estimators=200, random_state=42, n_jobs=1).fit(tr[feats], tr[target])
    labels = list(m.classes_)
    gm = giskard.Model(model=lambda d: m.predict_proba(d[feats]), model_type="classification",
                       classification_labels=labels, feature_names=feats, name="rf")
    gd = giskard.Dataset(df=te.reset_index(drop=True), target=target, cat_columns=[])
    res = giskard.scan(gm, gd, raise_exceptions=False, verbose=False)
    issues = [{"group": str(getattr(i.group, "name", i.group)), "detector": type(i).__name__,
               "desc": str(getattr(i, "description", ""))[:200]} for i in res.issues]
    leak = [i for i in issues if any(k in (i["group"] + i["detector"] + i["desc"]).lower() for k in LEAK_GROUPS)]
    return {"n_issues": len(issues), "issue_groups": sorted({i["group"] for i in issues}), "flagged_any": bool(issues),
            "flagged_leakage": bool(leak), "leak_issues": leak[:5]}


def main():
    gt = json.loads((ROOT / "eval" / "ground_truth.json").read_text())  # evaluator-side scoring only
    cases = sorted(gt) + ["factorial/comp_visit_history"]
    out = {}
    for c in cases:
        d = ROOT / ("corpus/" + c if "/" not in c else c)
        try:
            out[c] = run_case(d)
        except Exception as e:  # noqa: BLE001
            out[c] = {"error": repr(e)[:400]}
        out[c]["leaky"] = gt[c]["leaky"] if c in gt else True
        print("RESULT", c, {k: out[c].get(k) for k in ("leaky", "n_issues", "issue_groups", "flagged_leakage", "error")}, flush=True)
    leaky = [c for c in gt if gt[c]["leaky"]]
    clean = [c for c in gt if not gt[c]["leaky"]]
    for key in ("flagged_any", "flagged_leakage"):
        out[f"summary_{key}"] = {"recall": f"{sum(bool(out[c].get(key)) for c in leaky)}/{len(leaky)}",
                                 "false_alarms": f"{sum(bool(out[c].get(key)) for c in clean)}/{len(clean)}"}
        print("SUMMARY", key, out[f"summary_{key}"])
    (ROOT / "runs_g1").mkdir(exist_ok=True)
    (ROOT / "runs_g1" / "giskard.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
