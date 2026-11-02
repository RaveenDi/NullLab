"""G1 / B0-real: the REAL Deepchecks (pip package, run in .venv-g1 because it needs older numpy/sklearn) on the blind
agent-view inputs. A blind user has data.csv + the target column named in train.py; we give Deepchecks a random 75/25
split (seed 42; the protocol most excerpts claim) and run its built-in suites: data_integrity (full data) and
train_test_validation (train vs test). No model is passed (the agent view has no fitted model).
flagged_any     = any check condition in either suite did not pass
flagged_leakage = a leakage-relevant check did not pass (samples mix, feature-label correlation/PPS, identifier-label
                  correlation, feature-label correlation change, duplicates, conflicting labels)
Usage (from nulllab/): .venv-g1\\Scripts\\python scripts\\g1\\real_deepchecks.py  -> runs_g1/deepchecks.json"""
import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
import pandas as pd  # noqa: E402
from deepchecks.tabular import Dataset  # noqa: E402
from deepchecks.tabular.suites import data_integrity, train_test_validation  # noqa: E402
from sklearn.model_selection import train_test_split  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent.parent
LEAK_CHECKS = ("Train Test Samples Mix", "Feature Label Correlation", "Identifier Label Correlation",
               "Feature Label Correlation Change", "Data Duplicates", "Conflicting Labels")


def run_case(case_dir):
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    target = re.search(r'^TARGET\s*=\s*"([^"]+)"', code, re.M).group(1)
    df = pd.read_csv(case_dir / "data.csv")
    tr, te = train_test_split(df, test_size=0.25, random_state=42)
    cat = [c for c in df.columns if c != target and df[c].dtype != float and df[c].nunique() <= 30]
    ds_full = Dataset(df, label=target, cat_features=cat)
    ds_tr, ds_te = Dataset(tr, label=target, cat_features=cat), Dataset(te, label=target, cat_features=cat)
    failed = []
    for name, res in (("data_integrity", data_integrity().run(ds_full)),
                      ("train_test_validation", train_test_validation().run(ds_tr, ds_te))):
        for r in res.get_not_passed_checks():
            failed.append({"suite": name, "check": r.get_header() if hasattr(r, "get_header") else str(r),
                           "conditions": [c.details if hasattr(c, "details") else str(c) for c in getattr(r, "conditions_results", [])][:3]})
    leak = [f for f in failed if any(k.lower() in f["check"].lower() for k in LEAK_CHECKS)]
    return {"failed_checks": failed, "flagged_any": bool(failed), "flagged_leakage": bool(leak),
            "leakage_checks_failed": sorted({f["check"] for f in leak})}


def main():
    sys.path.insert(0, str(ROOT))
    gt = json.loads((ROOT / "eval" / "ground_truth.json").read_text())  # evaluator-side scoring only (tool never sees it)
    cases = sorted(gt) + ["factorial/comp_visit_history"]
    out = {}
    for c in cases:
        d = ROOT / ("corpus/" + c if "/" not in c else c)
        try:
            out[c] = run_case(d)
        except Exception as e:  # noqa: BLE001
            out[c] = {"error": repr(e)[:400]}
        out[c]["leaky"] = gt[c]["leaky"] if c in gt else True
        print(c, {k: out[c].get(k) for k in ("leaky", "flagged_any", "flagged_leakage", "leakage_checks_failed", "error")}, flush=True)
    leaky = [c for c in gt if gt[c]["leaky"]]
    clean = [c for c in gt if not gt[c]["leaky"]]
    for key in ("flagged_any", "flagged_leakage"):
        out[f"summary_{key}"] = {"recall": f"{sum(bool(out[c].get(key)) for c in leaky)}/{len(leaky)}",
                                 "false_alarms": f"{sum(bool(out[c].get(key)) for c in clean)}/{len(clean)}"}
        print(key, out[f"summary_{key}"])
    (ROOT / "runs_g1").mkdir(exist_ok=True)
    (ROOT / "runs_g1" / "deepchecks.json").write_text(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
