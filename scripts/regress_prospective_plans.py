"""Post-pilot development regression: reuse final stored plans, zero model calls.

Original frozen pilot outcomes are never edited or rescored. These cases have now
informed an instrument correction and are development evidence for this run.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import run_audit, write_json

output = ROOT / "out" / "prospective-regression-results"
output.mkdir(parents=True, exist_ok=False)
original = ROOT / "out" / "prospective-live-results"
schedule = json.loads((original / "schedule.json").read_text())
files = schedule["freeze"]["files"]
write_json(output / "instrument.json", {"files": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in files},
    "scope": "development regression after the frozen pilot exposed a negation bug; no new model calls; original pilot preserved"})


def run(case_id):
    prior = json.loads((original / case_id / "result.json").read_text())
    result = run_audit(ROOT / "out" / "prospective-cases" / case_id, output / case_id,
                       plan=prior.get("plan"), n_boot=300)
    print(json.dumps({"case": case_id, "status": result["status"], "verdict": result["verdict"],
                      "summary": result.get("summary"), "calls": result["ledger"]["calls"]}), flush=True)
    return result


with ThreadPoolExecutor(max_workers=2) as pool:
    results = list(pool.map(run, schedule["case_ids"]))
write_json(output / "totals.json", {"cases": len(results), "measured": sum(bool(r.get("record")) for r in results),
    "verdicts": {r["case"]: r["verdict"] for r in results}, "calls": sum(r["ledger"]["calls"] for r in results),
    "note": "Development regression, not a new blinded success rate"})
