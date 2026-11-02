"""Sandbox runner for the 2x2 factorial (BRIEF-4). Runs inside the sandbox (temp dir, network cut, file allow-list).
orig = train.claimed_eval; fix_A / fix_B / fix_both = controlled_eval(df, seed) from fix_A.py / fix_B.py / fix_both.py.
Writes raw per-seed y_true / y_pred vectors only; ALL statistics are computed outside the sandbox (sandbox/factorial_stats.py)
so a patch cannot tamper with the numbers that decide the verdict.
Usage: python run_factorial.py --seeds 42,43,44 --out result.json"""
import argparse
import importlib.util
import json
import os
import sys
import time

CONFIGS = ("fix_A", "fix_B", "fix_both")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="42,43,44")
    ap.add_argument("--out", default="result.json")
    a = ap.parse_args()
    sys.path.insert(0, os.getcwd())
    from run import _block_network, preload_heavy
    preload_heavy()  # library imports + the KNN ctypes warm-up first (train.py NOT imported yet)
    _block_network()  # then the block, so train.py's module-level code runs sandboxed
    import train
    mods = {}
    for c in CONFIGS:
        spec = importlib.util.spec_from_file_location(c, c + ".py")
        mods[c] = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mods[c])
    df = train.load("data.csv")
    metric = getattr(train, "METRIC", "accuracy")  # G6: fixed by the ORIGINAL train.py (module level, not editable)
    conv = int if metric == "accuracy" else float  # score metrics keep the continuous prediction
    out, t0 = {"seeds": {}, "metric": metric}, time.time()
    for s in [int(x) for x in a.seeds.split(",")]:
        res = {}
        y, p = train.claimed_eval(df, s)
        res["orig"] = {"y": [int(v) for v in y], "p": [conv(v) for v in p]}
        for c in CONFIGS:
            y, p = mods[c].controlled_eval(df, s)
            res[c] = {"y": [int(v) for v in y], "p": [conv(v) for v in p]}
        out["seeds"][str(s)] = res
    out["elapsed_s"] = time.time() - t0
    with open(a.out, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
