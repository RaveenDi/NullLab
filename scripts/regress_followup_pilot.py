"""Development checks after the fixed follow-up; no network, no new model calls.

One stored scaler plan is measured with the repaired guard. Three pairs of stored
responses exercise objection handling under new code. Those responses do NOT
answer the new prompts and are not valid provider replay or new model inference.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import run_audit, write_json


def main():
    base = ROOT / "out/followup-v2-results/live"
    output = ROOT / "out/followup-v2-regression"
    output.mkdir(exist_ok=False)
    freeze = json.loads((ROOT / "out/followup-v2-freeze.json").read_text())
    instruments = {}
    for name in freeze["files"]:
        src = ROOT / name
        dest = output / "instrument" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        instruments[name] = hashlib.sha256(src.read_bytes()).hexdigest()
    write_json(output / "instrument.json", {"files": instruments, "scope": __doc__})
    results = []
    case_id = "fx-v5q8"
    original = json.loads((base / case_id / "result.json").read_text())
    results.append(run_audit(ROOT / "eval/v2_followup_cases" / case_id, output / case_id, plan=original["plan"], n_boot=300))

    class ResponseFixture:
        def __init__(self, traces):
            self.traces, self.used = traces, 0

        def complete(self, *args, role="planner", **kwargs):
            record = self.traces[self.used]
            assert record["role"] == role
            self.used += 1
            return record["reply"]

        def ledger(self):
            return {"calls": 0, "est_usd": 0, "fixture_responses": self.used}

    for case_id in ("fx-h3p6", "fx-k2t7", "fx-s9d1"):
        trace_path = base / case_id / "provider-traces.jsonl"
        traces = [json.loads(line) for line in trace_path.read_text().splitlines()]
        fixture = ResponseFixture(traces)
        result = run_audit(ROOT / "eval/v2_followup_cases" / case_id, output / case_id, live=True, critic=True, provider=fixture, n_boot=300)
        assert fixture.used == len(traces)
        result["mode"] = "development_response_fixture"
        result["fixture_note"] = "Stored responses to previous prompts. Offline objection-handling regression only; not provider replay or new inference."
        result["fixture_source_sha256"] = hashlib.sha256(trace_path.read_bytes()).hexdigest()
        write_json(output / case_id / "result.json", result)
        results.append(result)
    totals = {"note": __doc__, "new_provider_calls": 0, "verdicts": {r["case"]: r["verdict"] for r in results}, "measured": sum(bool(r.get("summary")) for r in results)}
    write_json(output / "totals.json", totals)
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
