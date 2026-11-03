"""Separate six-case confirmation after the retained release-cohort critic failure.

New fixed CSV bytes and IDs; familiar mechanisms, internal coordinator evaluation.
Never replaces the original ten-case score. At most $6 reserved / 24 attempts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent import evidence
from agent.engine import preflight, run_audit, write_json
from agent.provider import Provider, ProviderConfig, read_config

BASE = ROOT / "eval/v2_confirmation"
SETTINGS = {"planner": "muse-spark-1.3", "critic": "muse-wonder-1.0", "effort": "low", "max_tokens": 12000, "timeout_s": 120, "retries": 0, "seeds": [42, 43, 44], "n_boot": 300, "workers": 2, "max_usd_per_case": 1, "max_calls_per_case": 4, "cases": 6, "max_reserved_usd": 6, "max_attempts": 24}
PAIRS = {"cn-b4m8": "rx-r7m2", "cn-t7r1": "rx-j4t9", "cn-q2v9": "rx-k8p3", "cn-h5a3": "rx-d2n6", "cn-p8d6": "rx-v5q1", "cn-w1j4": "rx-a9w4"}


def prepare():
    import numpy as np
    import pandas as pd

    BASE.mkdir(exist_ok=False)
    prior = ROOT / "eval/v2_release"
    names = set(json.loads((prior / "freeze.json").read_text())["files"])
    names.add("scripts/run_release_confirmation.py")
    files = {}
    for name in sorted(names):
        data = (ROOT / name).read_bytes()
        dest = BASE / "instrument" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        files[name] = evidence.file_hash(dest)
    write_json(BASE / "instrument-freeze.json", {"captured_at_utc": datetime.now(UTC).isoformat(), "files": files})
    rng = np.random.default_rng(91521)
    X = rng.normal(size=(176, 80))
    y = (X[:, 0] * 0.4 + rng.normal(size=176) > 0).astype(int)
    screen = pd.DataFrame(X, columns=[f"band_{i:02d}" for i in range(80)]).assign(event=y)
    rng = np.random.default_rng(91522)
    X = rng.standard_t(df=6, size=(180, 5)) * np.array([3, 0.2, 15, 70, 0.01])
    y = (X[:, 0] / 4 - X[:, 2] / 20 + rng.normal(size=180) > 0).astype(int)
    scale = pd.DataFrame(X, columns=[f"signal_{i}" for i in range(5)]).assign(event=y)
    rng = np.random.default_rng(91523)
    devices = np.repeat(np.arange(48), 4)
    X = rng.uniform(-3, 3, size=(48, 3))[devices] + rng.normal(scale=0.025, size=(192, 3))
    y = np.tile([0, 1], 24)
    rng.shuffle(y)
    group = pd.DataFrame(X, columns=["signature_a", "signature_b", "signature_c"]).assign(device=devices, event=y[devices])
    previous_truth = json.loads((prior / "truth.json").read_text())["cases"]
    truth, case_files, checks = {}, {}, {}
    for cid, old_id in PAIRS.items():
        d = BASE / "cases" / cid
        d.mkdir(parents=True)
        for name in ("train.py", "excerpt.md", "case.json"):
            data = (prior / "cases" / old_id / name).read_bytes()
            # New data with the same code contract: no observed-effect tuning.
            (d / name).write_bytes(data)
        family = previous_truth[old_id]["family"]
        frame = {"label_screening": screen, "fitted_scaling": scale, "entity_separation": group}[family]
        (d / "data.csv").write_bytes(frame.to_csv(index=False, float_format="%.9g").encode())
        truth[cid] = {**previous_truth[old_id], "prior_template_case": old_id}
        checks[cid] = preflight(d)["rows"]
        case_files[cid] = {p.name: evidence.file_hash(p) for p in sorted(d.iterdir())}
    write_json(BASE / "truth.json", {"cases": truth, "scope": "New data/IDs; same capability-informed templates after observing the critic-prompt defect. Internal confirmation, not blinded held-out mechanisms."})
    write_json(BASE / "freeze.json", {"prepared_at_utc": datetime.now(UTC).isoformat(), "files": files, "case_files": case_files, "truth_sha256": evidence.file_hash(BASE / "truth.json"), "settings": SETTINGS, "case_ids": sorted(truth), "preflight_rows": checks})
    print(json.dumps({"cases": 6, "captured_sources": len(files), "preflight_rows": checks}, indent=2))


def verify(freeze, *, current=True):
    for name, expected in freeze["files"].items():
        if evidence.file_hash(BASE / "instrument" / name) != expected or (current and evidence.file_hash(ROOT / name) != expected):
            raise ValueError(f"Instrument drift: {name}")
    if freeze["settings"] != SETTINGS or evidence.file_hash(BASE / "truth.json") != freeze["truth_sha256"]:
        raise ValueError("Settings or truth drift")
    for cid, files in freeze["case_files"].items():
        for name, expected in files.items():
            if evidence.file_hash(BASE / "cases" / cid / name) != expected:
                raise ValueError(f"Case drift: {cid}/{name}")


def run(env_file):
    freeze = json.loads((BASE / "freeze.json").read_text())
    verify(freeze)
    config = ProviderConfig(api_key=read_config(env_file).get("MODEL_API_KEY", ""), model=SETTINGS["planner"], role_models={"critic": SETTINGS["critic"]}, reasoning_effort="low", max_tokens=12000, timeout_s=120, retries=0)
    if not config.api_key:
        raise ValueError("Explicit Meta credential required")
    out = BASE / "results"
    out.mkdir(exist_ok=False)
    write_json(out / "schedule.json", {"freeze": freeze, "policy": "Once per mode; no rerolls; no independent no-critic arm. Original release cohort remains unchanged.", "project_ceiling_usd": 60, "pre_run_conservative_recorded_estimate_usd": "39.58933475", "bound_including_this_cohort_usd": "45.58933475"})
    for mode in ("offline", "live"):
        def one(cid, mode=mode):
            verify(freeze)
            job = out / mode / cid
            provider = Provider(config, job, max_usd=1, max_calls=4) if mode == "live" else None
            r = run_audit(BASE / "cases" / cid, job, live=mode == "live", critic=mode == "live", provider=provider, n_boot=300)
            print(json.dumps({"mode": mode, "case": cid, "status": r["status"], "verdict": r["verdict"], "measured": bool(r.get("summary")), "calls": r["ledger"]["calls"]}), flush=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(one, freeze["case_ids"]))
    verify(freeze)
    score()


def score():
    freeze = json.loads((BASE / "freeze.json").read_text())
    verify(freeze, current=False)
    truth = json.loads((BASE / "truth.json").read_text())["cases"]
    rows, hashes, reserves = [], {}, []
    usage = Counter()
    for mode in ("offline", "live"):
        for cid in freeze["case_ids"]:
            p = BASE / "results" / mode / cid / "result.json"
            r = json.loads(p.read_text())
            evidence.verify(p.parent / "inputs", r)
            if any(r["evidence"]["inputs"][n] != h for n, h in freeze["case_files"][cid].items()):
                raise ValueError("Result identity differs from frozen case")
            lp = p.parent / "provider-ledger.json"
            attempts = json.loads(lp.read_text())["attempts"] if lp.exists() else []
            reserves.extend(Decimal(str(a["reserved_usd"])) for a in attempts)
            for a in attempts:
                usage.update(a.get("usage", {}))
            if r.get("summary"):
                for seed, configs in r["raw"]["seeds"].items():
                    for name in ("orig", "fix_both"):
                        v = configs[name]
                        acc = sum(y == pred for y, pred in zip(v["y"], v["p"], strict=True)) / len(v["y"])
                        if abs(acc - r["record"]["stats"][seed]["full"]["acc"][name]) > 1e-12:
                            raise ValueError("Prediction vectors disagree with stored scores")
            hashes[p.relative_to(BASE).as_posix()] = evidence.file_hash(p)
            rows.append({"case": cid, "mode": mode, **truth[cid], "status": r["status"], "verdict": r["verdict"], "baseline": r.get("baseline"), "control_measured": bool(r.get("summary")), "plan": r.get("plan"), "guard": r.get("guard"), "summary": r.get("summary"), "independent_review": r.get("independent_review"), "critic": r.get("critic"), "error": r.get("error"), "attempts": len(attempts)})
    live = [r for r in rows if r["mode"] == "live"]
    total = {"scheduled_per_mode": 6, "supported_flawed": 3, "clean": 3, "supported_flawed_measured_live": sum(r["category"] == "supported_flawed" and r["control_measured"] for r in live), "clean_controls_measured_live": sum(r["category"] == "clean" and r["control_measured"] for r in live), "live_verdicts": dict(Counter(r["verdict"] for r in live)), "provider_attempts": sum(r["attempts"] for r in rows), "reserved_estimate_usd_exact": str(sum(reserves)), "token_usage": dict(usage)}
    if total["provider_attempts"] > 24 or sum(reserves) > 6:
        raise ValueError("Confirmation budget exceeded")
    write_json(BASE / "score.json", {"schema": "nulllab.release-confirmation-score.v1", "scope": "Separate internal six-case confirmation: new data, same known templates, after critic prompt repair. Never a replacement score for the ten-case cohort.", "totals": total, "results": rows, "result_sha256": hashes, "limitations": ["Small coordinator-prepared/adjudicated synthetic cases with familiar mechanisms; no external users or general accuracy estimate.", "No matched no-critic arm or measured critic superiority.", "No-control clean judgments are model-only, not empirical specificity.", "Group measurements are descriptive; row intervals are not group-calibrated."]})
    print(json.dumps(total, indent=2))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("prepare", "run", "score"))
    ap.add_argument("--env-file")
    args = ap.parse_args()
    if args.command == "prepare":
        prepare()
    elif args.command == "run":
        if not args.env_file:
            ap.error("run requires explicit --env-file")
        run(args.env_file)
    else:
        score()
