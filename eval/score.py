"""Evaluator-only scoring + ablation. Run: python -m eval.score   (runs baselines, reads runs/*.json from pipeline.py)
Writes runs/ablation.json. NullLab rows are labelled with the mode that produced them."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GT = json.loads((ROOT / "eval" / "ground_truth.json").read_text())


def score_rows(rows):
    """rows: {case: bool flagged/falsified} -> recall on leaky, false alarms on clean."""
    leaky = [c for c, g in GT.items() if g["leaky"]]
    clean = [c for c, g in GT.items() if not g["leaky"]]
    return {"recall": f"{sum(rows[c] for c in leaky)}/{len(leaky)}", "false_alarms": f"{sum(rows[c] for c in clean)}/{len(clean)}"}


def grounding(runs):
    """Fraction of verbatim pointers present in sources over all cases (the pointers are checked in agent/extract.grounded)."""
    p = [r["claim"]["grounding"]["precision"] for r in runs.values()]
    return sum(p) / len(p)


def main(pipeline_mode="mock"):
    import pipeline
    from baselines.checklist import b0_checklist, b1_groupkfold
    runs = {c: json.loads((ROOT / "runs" / f"{c}.json").read_text()) for c in GT}
    b0 = {c: b0_checklist(ROOT / "corpus" / c) for c in GT}
    b1 = {c: b1_groupkfold(ROOT / "corpus" / c) for c in GT}
    nl = {c: runs[c]["verdict"]["verdict"] == "FALSIFIED" for c in GT}
    out = {"B0": {"per_case": b0, **score_rows({c: v["flagged"] for c, v in b0.items()})},
           "B1": {"per_case": b1, **score_rows({c: v["flagged"] for c, v in b1.items()})},
           "B3": {"status": "NOT RUN (UNVERIFIED)"},
           "NullLab": {"mode": runs[next(iter(runs))]["mode"], "verdicts": {c: runs[c]["verdict"]["verdict"] for c in GT},
                       **score_rows(nl)},
           "grounding_precision": grounding(runs)}
    leaky = [c for c, g in GT.items() if g["leaky"]]
    out["non_checklist_win"] = {c: (nl[c] and not b0[c]["flagged"] and not b1[c]["flagged"]) for c in leaky}
    (ROOT / "runs" / "ablation.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
