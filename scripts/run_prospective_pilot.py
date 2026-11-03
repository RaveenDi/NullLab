"""Bounded internal synthetic pilot. Paid inference requires owner authorization.

Six independently prepared cases, maximum four attempts and USD 0.80 reserved per
case (USD 4.80 / 24 attempts total). Truth is read only after all scheduled cases.
No failed case is re-rolled. No browser activity.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import run_audit, write_json
from agent.provider import Provider, ProviderConfig


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--env-file", default=".env")
    ap.add_argument("--cases", default="out/prospective-cases")
    ap.add_argument("--freeze", default="out/prospective-protocol-freeze.json")
    ap.add_argument("--truth", default="out/prospective-truth.json")
    ap.add_argument("--out", default="out/prospective-results")
    ap.add_argument(
        "--offline", action="store_true", help="Rules/local execution only; no credential access or model calls"
    )
    a = ap.parse_args()
    freeze = json.loads((ROOT / a.freeze).read_text())

    def check_freeze():
        for name, expected in freeze["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Instrument changed after pilot freeze: {name}")

    check_freeze()
    cases = sorted(p for p in (ROOT / a.cases).iterdir() if p.is_dir())
    if len(cases) != 6:
        raise ValueError("This approved schedule requires exactly six cases")
    output = ROOT / a.out
    output.mkdir(parents=True, exist_ok=False)
    config = None if a.offline else replace(ProviderConfig.from_env(a.env_file), timeout_s=120, retries=0)
    write_json(
        output / "schedule.json",
        {
            "case_ids": [p.name for p in cases],
            "freeze": freeze,
            "scope": "internal synthetic pilot designed from instrument capabilities; not a wild-paper benchmark",
            "mode": "offline rules and execution" if a.offline else "live planner and critic",
            "max_reserved_usd": 0 if a.offline else 4.8,
            "max_attempts": 0 if a.offline else 24,
        },
    )

    def run(case):
        check_freeze()
        job = output / case.name
        provider = None if a.offline else Provider(config, job, max_usd=0.8, max_calls=4)
        r = run_audit(case, job, live=not a.offline, critic=not a.offline, provider=provider, n_boot=300)
        print(
            json.dumps(
                {
                    "case": case.name,
                    "status": r["status"],
                    "verdict": r["verdict"],
                    "calls": r["ledger"]["calls"],
                    "reserved_usd": r["ledger"]["est_usd"],
                }
            ),
            flush=True,
        )
        return r

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, cases))
    check_freeze()
    # This is deliberately the first truth-file access in this process.
    truth = json.loads((ROOT / a.truth).read_text())
    write_json(
        output / "adjudication-input.json",
        {
            "truth": truth,
            "results": [
                {
                    "case": r["case"],
                    "status": r["status"],
                    "verdict": r["verdict"],
                    "initial_plan": r.get("plan"),
                    "summary": r.get("summary"),
                    "critic": r.get("critic"),
                    "guard": r.get("guard"),
                    "ledger": r["ledger"],
                }
                for r in results
            ],
        },
    )
    write_json(
        output / "totals.json",
        {
            "scheduled": len(cases),
            "completed": sum(r["status"] == "completed" for r in results),
            "attempts": sum(r["ledger"]["calls"] for r in results),
            "reserved_usd": sum(r["ledger"]["est_usd"] for r in results),
            "note": "All outcomes retained; score matched plan/no-execution vs execution vs critic using this one fixed plan per case. No re-rolls.",
        },
    )


if __name__ == "__main__":
    main()
