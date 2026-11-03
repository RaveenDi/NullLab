"""Measure one case with the fixed rule library (no model). Local sandbox only.

This is the same measurement as eval/run_rulefix.run_case, kept here so agent code never reaches into the eval folder
(the agent must not be able to reach the evaluation folder, see tests/test_nulllab.py)."""
import hashlib
import time
from pathlib import Path

from baselines import rulefix
from agent import evidence

SEEDS, N_BOOT = (42, 43, 44), 1000


def run_case(case_dir: str | Path, seeds: tuple[int, ...] = SEEDS, n_boot: int = N_BOOT, timeout: int = 3000) -> dict:
    """Run the rule-library fixes on one case in the local sandbox and return the measurement record."""
    from sandbox import executor, factorial_stats
    case_dir = Path(case_dir)
    b = rulefix.build_configs(case_dir)
    patches = {k: b["configs"][k]["src"] for k in ("fix_A", "fix_B", "fix_both")}
    identity = evidence.capture(case_dir, sources=patches, context={"engine": "rules-v2", "seeds": list(seeds), "n_boot": n_boot})
    t0 = time.time()
    ex = executor.run_factorial(case_dir, patches, seeds=seeds, timeout=timeout)
    rec = {"case": case_dir.name, "tool": "rulefix (no LLM)", "seeds": list(seeds), "n_boot": n_boot, "bootstrap": "unpaired",
           "fired": b["det"]["fired"], "not_applied": b["det"]["not_applied"], "split_fn": b["det"]["split_fn"],
           "configs": {k: {"rules_applied": v["rules_applied"], "steps": v["steps"], "notes": v["notes"],
                           "src_sha256": hashlib.sha256(v["src"].encode()).hexdigest()} for k, v in b["configs"].items()},
           "sources": patches, "evidence": identity, "status": ex["status"], "elapsed_s": round(time.time() - t0, 1)}
    evidence.verify(case_dir, rec)
    if ex["status"] != "ok":
        rec["stderr"] = ex.get("stderr", "")[-1500:]
        return rec
    try:
        rec["stats"] = factorial_stats.all_seeds(ex["result"], n_boot=n_boot, expected_seeds=seeds)
    except ValueError as e:
        rec.update(status="error", stderr=f"invalid worker result: {e}")
        return rec
    rec["metric"] = ex["result"].get("metric", "accuracy")
    return rec
