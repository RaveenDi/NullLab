"""Plan -> Act -> Verify -> Recover orchestration for one case. Only touches the agent view + sandbox.
Usage: python pipeline.py [case ...] [--live]   (default: all cases, MOCK mode)
Outputs: MOCK -> runs/<case>.json ; LIVE -> runs_live/<case>.json (kept apart so a mock run or a test can never
overwrite live evidence; tests redirect both to a temp dir)."""
import json
import sys
import time
from pathlib import Path

from agent import extract, falsify
from sandbox import executor, verdict

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
RUNS = ROOT / "runs"            # MOCK outputs
RUNS_LIVE = ROOT / "runs_live"  # LIVE outputs only


def cases():
    return sorted(p.name for p in CORPUS.iterdir() if p.is_dir())


def run_case(case, mode="mock", n_boot=1000, timeout=120, out_dir=None):
    case_dir = CORPUS / case
    manifest = json.loads((CORPUS / "manifest.json").read_text())[case]
    log, t0 = [], time.time()

    def ev(phase, msg, **kw):
        log.append({"t": round(time.time() - t0, 2), "phase": phase, "msg": msg, **kw})

    # PLAN
    claim = extract.extract_claim(case_dir, mode)
    ev("Plan", f"claim extracted [{claim['mode']}]: {claim['claim']}", grounding=claim["grounding"])
    hyp = falsify.propose(case_dir, claim, mode)
    ev("Plan", f"3 hypotheses preregistered before any run (sha256 {hyp['prereg_sha256'][:12]}); primary {hyp['primary']}: "
               f"{hyp['broken_assumption']}", hypotheses=hyp["hypotheses"])
    # ACT
    ex = executor.run_experiment(case_dir, hyp["code_patch"], n_boot=n_boot, timeout=timeout)
    ev("Act", f"sandbox[{ex['backend']}] -> {ex['status']}", status=ex["status"])
    runs = [{"attempt": 1, "patch": "primary", "status": ex["status"]}]
    # RECOVER (one retry)
    if ex["status"] != "ok":
        ev("Recover", f"Act failed ({ex.get('stderr', ex['status'])[-200:]}); auto-retry once with a repaired patch")
        patch = falsify.recover(case_dir, claim, hyp, ex.get("stderr", ex["status"]), mode)
        ex = executor.run_experiment(case_dir, patch, n_boot=n_boot, timeout=timeout)
        runs.append({"attempt": 2, "patch": "recovered", "status": ex["status"]})
        ev("Act", f"retry -> {ex['status']}")
    out = {"case": case, "mode": claim["mode"], "provenance": manifest["provenance"], "claim": claim, "hyp": hyp,
           "runs": runs, "log": log}
    if ex["status"] != "ok":
        out["verdict"] = {"verdict": "INCONCLUSIVE", "per_seed": {}, "agree": False, "reason": "experiment did not run"}
    else:
        res = ex["result"]
        out["seeds"] = res["seeds"]
        out["verdict"] = verdict.verdict(res["seeds"])
        out["verdict"]["cites_ok"] = claim["grounding"]["precision"] == 1.0
        d = {s: round(r["delta"], 3) for s, r in res["seeds"].items()}
        ev("Verify", f"per-seed unpaired-bootstrap deltas per seed {d}; seed calls {out['verdict']['per_seed']} -> {out['verdict']['verdict']}")
    out["elapsed_s"] = round(time.time() - t0, 1)
    out_dir = Path(out_dir) if out_dir else (RUNS_LIVE if mode == "live" else RUNS)
    if mode != "live" and out_dir.resolve() == (ROOT / "runs_live").resolve():
        raise RuntimeError("refusing to write a MOCK run into runs_live/")
    out_dir.mkdir(exist_ok=True)
    (out_dir / f"{case}.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    mode = "live" if "--live" in sys.argv else "mock"
    sel = [a for a in sys.argv[1:] if not a.startswith("--")] or cases()
    for c in sel:
        r = run_case(c, mode)
        print(c, r["provenance"], r["verdict"]["verdict"], r["verdict"]["per_seed"], f"{r['elapsed_s']}s")
