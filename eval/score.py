"""Evaluator-only scoring + ablation. Run: python -m eval.score [--live]   (reads runs/*.json, or runs_live/*.json with --live)
Writes ablation.json next to the runs it scored. NullLab rows are labelled with the mode that produced them.
B0/B1 are scripted reimplementations (real deepchecks/giskard were not installed when this ran;
see real_suites below). B3 (single-prompt judgement, no execution) only runs in --live mode."""
import importlib
import json
import sys
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


def suite_availability():
    """Whether the real baseline suites are importable; if not, the reimplementations stand in (labelled)."""
    out = {}
    for mod in ("deepchecks", "giskard"):
        try:
            m = importlib.import_module(mod)
            out[mod] = getattr(m, "__version__", "installed (version unknown)")
        except Exception:
            out[mod] = f"not installed (reimplementation used; install with `pip install {mod}` to run the real suite)"
    return out


def main(pipeline_mode="mock", runs_dir=None):
    import pipeline
    rd = Path(runs_dir) if runs_dir else (pipeline.RUNS_LIVE if pipeline_mode == "live" else pipeline.RUNS)
    from baselines.checklist import b0_checklist, b1_groupkfold
    from baselines.single_prompt import b3_single_prompt
    runs = {c: json.loads((rd / f"{c}.json").read_text()) for c in GT}
    b0 = {c: b0_checklist(ROOT / "corpus" / c) for c in GT}
    b1 = {c: b1_groupkfold(ROOT / "corpus" / c) for c in GT}
    nl = {c: runs[c]["verdict"]["verdict"] == "FALSIFIED" for c in GT}
    b3 = {c: b3_single_prompt(ROOT / "corpus" / c, mode="live" if pipeline_mode == "live" else "mock") for c in GT}
    if all(v["flagged"] is None for v in b3.values()):
        b3out = {"status": "NOT RUN (mock mode; single-prompt judgement needs --live)", "per_case": b3}
    else:
        b3flags = {c: bool(v["flagged"]) for c, v in b3.items()}
        b3out = {"mode": "LIVE muse-spark-1.3 (one call per case, no execution)", "per_case": b3, **score_rows(b3flags)}
        b3out["loop_vs_single"] = ("NullLab loop vs single-prompt: compare recall/false-alarms rows; "
                                   "the loop wins only if its recall >= B3 with strictly fewer false alarms "
                                   "and >=1 non-checklist win (B0+B1+B3 all miss, loop falsifies with 3-seed CI).")
    out = {"B0": {"per_case": b0, **score_rows({c: v["flagged"] for c, v in b0.items()})},
           "B1": {"per_case": b1, **score_rows({c: v["flagged"] for c, v in b1.items()})},
           "B3": b3out,
           "real_suites": suite_availability(),
           "NullLab": {"mode": runs[next(iter(runs))]["mode"], "verdicts": {c: runs[c]["verdict"]["verdict"] for c in GT},
                       **score_rows(nl)},
           "grounding_precision": grounding(runs)}
    leaky = [c for c, g in GT.items() if g["leaky"]]
    out["non_checklist_win"] = {c: (nl[c] and not b0[c]["flagged"] and not b1[c]["flagged"]
                                    and (b3[c]["flagged"] is not True)) for c in leaky}
    (rd / "ablation.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    print(json.dumps(main("live" if "--live" in sys.argv else "mock"), indent=1))
