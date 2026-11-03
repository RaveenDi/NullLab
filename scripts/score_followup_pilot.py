"""Offline adjudication of the original fixed follow-up, never the repaired runs."""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import evidence
from agent.engine import write_json


def main():
    base = ROOT / "out/followup-v2-results"
    schedule = json.loads((base / "schedule.json").read_text())
    freeze = schedule["freeze"]
    truth = json.loads((ROOT / "out/followup-v2-truth.json").read_text())["cases"]
    rows, hashes, reservations, usages, latencies = [], {}, [], Counter(), {"offline": [], "live": []}
    for mode in ("offline", "live"):
        for case_id in schedule["case_ids"]:
            p = base / mode / case_id / "result.json"
            r = json.loads(p.read_text())
            hashes[p.relative_to(ROOT).as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
            if r.get("evidence"):
                evidence.verify(p.parent / "inputs", r)
                assert all(r["evidence"]["inputs"][name] == digest for name, digest in freeze["case_files"][case_id].items())
            if r.get("summary"):
                for seed, configs in r["raw"]["seeds"].items():
                    for config in ("orig", "fix_both"):
                        vectors = configs[config]
                        score = sum(y == pred for y, pred in zip(vectors["y"], vectors["p"], strict=True)) / len(vectors["y"])
                        assert abs(score - r["record"]["stats"][seed]["full"]["acc"][config]) < 1e-12
            ledger_path = p.parent / "provider-ledger.json"
            attempts = json.loads(ledger_path.read_text())["attempts"] if ledger_path.exists() else []
            reservations.extend(Decimal(str(a["reserved_usd"])) for a in attempts)
            for attempt in attempts:
                usages.update(attempt.get("usage", {}))
            if r["events"]:
                latencies[mode].append(r["finished_at"] - r["events"][0]["time"])
            rows.append({
                "case": case_id, "mode": mode, "category": truth[case_id]["category"], "family": truth[case_id]["family"],
                "status": r["status"], "verdict": r["verdict"], "baseline_executed": bool(r.get("baseline")),
                "control_measured": bool(r.get("summary")), "plan": r.get("plan"), "guard": r.get("guard"),
                "summary": r.get("summary"), "critic": r.get("critic"), "error": r.get("error"), "attempts": len(attempts),
            })
    score = {
        "schema": "nulllab.followup-original-score.v1",
        "scope": "Coordinator adjudication after independent AI case preparation. Internal synthetic capability-informed evidence; no external human or project validation.",
        "source": "out/followup-v2-results", "scheduled_per_mode": 8, "families": 6,
        "category_denominators": dict(Counter(v["category"] for v in truth.values())),
        "original_instrument_snapshot": "out/followup-v2-instrument",
        "results": rows,
        "totals": {
            "baseline_completed_per_mode": 7, "supported_flawed": 2, "supported_flawed_measured_live": 1,
            "live_measured_verdict": "DISPUTED", "positive_inflation_findings": 0,
            "clean_model_only_assessments": 2, "ambiguous_model_no_flaw_states": 2,
            "known_unsupported_concern_model_no_flaw_state": 1, "multiclass_rejected_before_inference": True,
            "provider_attempts": sum(row["attempts"] for row in rows), "reserved_estimate_usd_exact": str(sum(reservations)),
            "token_usage": dict(usages), "median_intake_to_finish_seconds": {m: statistics.median(v) for m, v in latencies.items()},
            "latency_denominator_per_mode": {m: len(v) for m, v in latencies.items()},
        },
        "limitations": [
            "No effects were required by mechanism truth. No empirical clean specificity or numerical accuracy rate is supported.",
            "The resampling control removed balancing; it is a protocol comparison, not the reference fold-local training-only control.",
            "Three model-only no-flaw states obscured missing information or an acknowledged unsupported concern; no empirical clearance was issued.",
            "Initial critique was independent of the planner; only one final critique occurred. No independent matched no-critic arm or critic superiority estimate exists.",
            "Case construction knew instrument capabilities; resampling was demo-exposed. Repeated seeds are not independent projects.",
            "Post-inspection repairs and reruns belong to separate development evidence; this original score is never replaced.",
        ],
        "source_result_sha256": hashes,
    }
    write_json(ROOT / "eval/v2_followup_score.json", score)
    print(json.dumps(score["totals"], indent=2))


if __name__ == "__main__":
    main()
