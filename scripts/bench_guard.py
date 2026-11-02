"""Benchmark the G9 behavioural guard: time and peak memory of trace_run (worker subprocess) and behaviour_check, original vs current.

    python scripts/bench_guard.py --case civilwar_disguised --impl new
    python scripts/bench_guard.py --case civilwar_disguised --impl orig --rev HEAD~1   # original guard from git history (needs a git checkout)
    python scripts/bench_guard.py --case ehg_disguised --impl new --trees 20 --max-rows 1500

No model calls, no network. The plan is one known-correct DSL op for the case (civil war: temporal replace_split on `epoch`; EHG: move_into_fold of
`oversample`), i.e. what the live G9 guard runs. Wrap long runs in `timeout`: this script never gives up by itself except through --timeout (per worker).
Peak memory is sampled (every 0.1 s) over this process and its children (the worker subprocesses); the numbers are RSS in MB.
"""
import argparse
import ast
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PLANS = {
    "civilwar_disguised": {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "epoch"},
    "ehg_disguised": {"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"},
}


class PeakRss:
    def __init__(self):
        try:
            import psutil
            self.ps = psutil.Process()
        except ImportError:
            self.ps = None
        self.peak_self = self.peak_total = 0
        self._stop = threading.Event()

    def _sample(self):
        while not self._stop.wait(0.1):
            try:
                me = self.ps.memory_info().rss
                kids = sum(c.memory_info().rss for c in self.ps.children(recursive=True))
                self.peak_self = max(self.peak_self, me)
                self.peak_total = max(self.peak_total, me + kids)
            except Exception:
                pass

    def __enter__(self):
        if self.ps:
            self.t = threading.Thread(target=self._sample, daemon=True)
            self.t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()


def load_guard(impl, rev):
    if impl == "new":
        from agent import guard_g9
        return guard_g9
    src = subprocess.run(["git", "show", f"{rev}:agent/guard_g9.py"], cwd=ROOT, capture_output=True, check=True).stdout
    d = Path(tempfile.mkdtemp(prefix="guard_orig_"))
    (d / "guard_g9.py").write_bytes(src)
    spec = importlib.util.spec_from_file_location("guard_g9_orig", d / "guard_g9.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ROOT = ROOT  # guard_plan imports agent.edit_dsl from the repo; the worker runs from HERE (the temp copy)
    return mod


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="civilwar_disguised", choices=sorted(PLANS))
    ap.add_argument("--impl", default="new", choices=("orig", "new"))
    ap.add_argument("--rev", default="HEAD", help="git revision holding the original guard (impl=orig)")
    ap.add_argument("--trees", type=int, default=None, help="override N_TREES in the smoke profile (default: the case's own value)")
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--timeout", type=int, default=600, help="per worker run, seconds")
    ap.add_argument("--json", default=None, help="write the result record here")
    a = ap.parse_args()
    from agent import edit_dsl
    g = load_guard(a.impl, a.rev)
    case_dir = ROOT / "real" / a.case
    plan = {"factors": [{"id": "A", "ops": [PLANS[a.case]]}]}
    profile = {}
    if a.trees:
        profile["overrides"] = {"N_TREES": a.trees}
    if a.max_rows:
        profile["max_rows"] = a.max_rows
    src = (case_dir / "train.py").read_text(encoding="utf-8")
    comp = edit_dsl.compile_plan(src, plan)
    cfg = comp["configs"]["fix_all"]
    cols, fns = g._op_cols(plan), g._op_fns(plan)
    rec = {"case": a.case, "impl": a.impl, "profile": profile}
    with PeakRss() as pk:
        t = time.time()
        orig = g.trace_run(src, case_dir, 42, profile, fns, cols, timeout=a.timeout)
        rec["trace_orig_s"] = round(time.time() - t, 1)
        t = time.time()
        fix = g.trace_run(cfg["src"], case_dir, 42, profile, fns, cols, timeout=a.timeout)
        rec["trace_fix_s"] = round(time.time() - t, 1)
        rec["n_events"] = [len(orig.get("events", [])), len(fix.get("events", []))]
        rec["status"] = [orig.get("status"), fix.get("status")]
        print(json.dumps(rec), flush=True)
        t = time.time()
        r = g.behaviour_check(orig, fix, cfg["ops"], src, expect_resize=True, hold_steps=edit_dsl.holdout_steps(ast.parse(src)))
        rec["behaviour_check_s"] = round(time.time() - t, 1)
    rec["decision"], rec["problems"] = r["decision"], r["problems"]
    rec["facts"] = r["facts"]
    rec["peak_rss_mb_parent"] = round(pk.peak_self / 2**20)
    rec["peak_rss_mb_parent_plus_workers"] = round(pk.peak_total / 2**20)
    print(json.dumps(rec, default=str), flush=True)
    if a.json:
        Path(a.json).write_text(json.dumps(rec, indent=1, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
