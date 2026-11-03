"""Fixed eight-case internal follow-up: preserve all outcomes, never reroll.

Rules and live modes share fixed inputs and instrument. The reading assessment is
the live planner's retained proposal before execution, not an independent arm.
At most USD 8 reserved / 32 attempts; only code, claims and aggregates leave.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import run_audit, write_json
from agent.provider import Provider, ProviderConfig, read_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--out", default="out/followup-v2-results")
    args = parser.parse_args()
    freeze = json.loads((ROOT / "out/followup-v2-freeze.json").read_text())
    cases_root = ROOT / "out/followup-v2-cases"
    cases = sorted(p for p in cases_root.iterdir() if p.is_dir())
    if len(cases) != 8:
        raise ValueError("Exactly eight scheduled cases required")
    if [p.name for p in cases] != freeze["case_ids"]:
        raise ValueError("Scheduled case identities changed")

    def check_freeze():
        for name, expected in freeze["files"].items():
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f"Frozen instrument changed: {name}")
        for case in cases:
            for name, expected in freeze["case_files"][case.name].items():
                if hashlib.sha256((case / name).read_bytes()).hexdigest() != expected:
                    raise ValueError(f"Frozen case changed: {case.name}/{name}")

    check_freeze()
    config = ProviderConfig(
        api_key=read_config(args.env_file).get("MODEL_API_KEY", ""),
        base_url="https://api.meta.ai/v1",
        model="muse-spark-1.3",
        role_models={"critic": "muse-wonder-1.0"},
        reasoning_effort="low", max_tokens=12000, timeout_s=120, retries=0,
    )
    if not config.api_key:
        raise ValueError("An explicitly configured Meta credential is required")
    expected_settings = {
        "planner_model": config.model, "critic_model": config.role_models["critic"],
        "base_url": config.base_url, "reasoning_effort": config.reasoning_effort,
        "max_tokens": config.max_tokens, "timeout_s": config.timeout_s, "retries": config.retries,
        "max_usd_per_case": 1.0, "max_calls_per_case": 4, "n_boot": 300,
        "seeds": [42, 43, 44], "workers": 2, "scheduled_cases": 8,
        "max_reserved_usd_total": 8.0, "max_attempts_total": 32, "credential_values": "excluded",
    }
    if freeze["settings"] != expected_settings:
        raise ValueError("Provider/experiment settings differ from the prepared freeze")
    output = ROOT / args.out
    output.mkdir(parents=True, exist_ok=False)
    write_json(output / "schedule.json", {
        "case_ids": [p.name for p in cases], "freeze": freeze,
        "scope": "Internal AI-prepared synthetic follow-up; some mechanisms known from development",
        "max_reserved_usd": 8, "max_attempts": 32,
        "comparison": "Rules vs retained pre-execution planner proposal vs execution vs advisory critic; no independent no-critic arm",
    })
    outcomes = {}
    for mode in ("offline", "live"):
        def run(case, current_mode=mode):
            check_freeze()
            job = output / current_mode / case.name
            provider = Provider(config, job, max_usd=1, max_calls=4) if current_mode == "live" else None
            result = run_audit(case, job, live=current_mode == "live", critic=current_mode == "live", provider=provider, n_boot=300)
            print(json.dumps({"mode": current_mode, "case": case.name, "status": result["status"], "verdict": result["verdict"], "calls": result["ledger"]["calls"]}), flush=True)
            return result

        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes[mode] = list(pool.map(run, cases))
        check_freeze()
    # Ground truth is first accessed after all scheduled results, never in prompts.
    truth = json.loads((ROOT / "out/followup-v2-truth.json").read_text())
    if hashlib.sha256((ROOT / "out/followup-v2-truth.json").read_bytes()).hexdigest() != freeze["truth_sha256"]:
        raise ValueError("Truth changed after case preparation")
    write_json(output / "adjudication-input.json", {"truth": truth, "outcomes": outcomes})
    all_results = [r for results in outcomes.values() for r in results]
    write_json(output / "totals.json", {
        "scheduled_per_mode": 8, "attempts": sum(r["ledger"]["calls"] for r in all_results),
        "reserved_usd_rounded_job_sum": sum(r["ledger"]["est_usd"] for r in all_results),
        "verdicts": {mode: {r["case"]: r["verdict"] for r in results} for mode, results in outcomes.items()},
        "note": "All scheduled outcomes retained; reservations are not billed cost; no rerolls",
    })


if __name__ == "__main__":
    main()
