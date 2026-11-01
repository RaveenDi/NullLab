"""Sandbox runner. Executes claimed_eval (from train.py) and controlled_eval (from patch.py) for each seed,
then paired bootstrap on the accuracy delta. Run inside the sandbox (no network, temp dir, timeout set by executor).
Usage: python run.py --seeds 42,43,44 --n-boot 1000 --out result.json   (cwd holds train.py, data.csv, patch.py)"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _block_network():
    import socket

    class _NoSock:
        def __init__(self, *a, **k):
            raise OSError("network disabled in NullLab sandbox")

    def _no(*a, **k):
        raise OSError("network disabled in NullLab sandbox")
    socket.socket = _NoSock
    socket.create_connection = _no
    socket.getaddrinfo = _no

    def _audit(event, args):  # defence in depth: the experiment may not open evaluator-only files
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            p = os.fsdecode(args[0]).replace("\\", "/").lower()
            if "ground_truth" in p or "/nulllab/eval/" in p:
                raise PermissionError("evaluator-only path is off limits")
        if event in ("socket.connect", "socket.bind"):
            raise OSError("network disabled in NullLab sandbox")
    sys.addaudithook(_audit)


def paired_bootstrap(y1, p1, y2, p2, n_boot, seed):
    """Delta = acc(claimed) - acc(controlled). Test sets differ between protocols, so the two correctness vectors
    are resampled independently with a shared RNG stream per replicate ("paired" by seed/replicate)."""
    import numpy as np
    c1 = (np.asarray(y1) == np.asarray(p1)).astype(float)
    c2 = (np.asarray(y2) == np.asarray(p2)).astype(float)
    rng = np.random.default_rng(seed)
    d = np.empty(n_boot)
    for b in range(n_boot):
        d[b] = c1[rng.integers(0, len(c1), len(c1))].mean() - c2[rng.integers(0, len(c2), len(c2))].mean()
    lo, hi = np.percentile(d, [2.5, 97.5])
    return {"claimed_acc": float(c1.mean()), "controlled_acc": float(c2.mean()), "delta": float(c1.mean() - c2.mean()),
            "ci_lo": float(lo), "ci_hi": float(hi), "n_claimed": int(len(c1)), "n_controlled": int(len(c2))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="42,43,44")
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument("--out", default="result.json")
    ap.add_argument("--patch", default="patch.py")
    a = ap.parse_args()
    sys.path.insert(0, os.getcwd())
    import importlib.util
    import train  # heavy imports (sklearn, asyncio, ssl) first, then cut the network before any user patch executes
    _block_network()
    spec = importlib.util.spec_from_file_location("patch", a.patch)
    patch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(patch)
    df = train.load("data.csv")
    out = {"seeds": {}, "t0": time.time()}
    for s in [int(x) for x in a.seeds.split(",")]:
        y1, p1 = train.claimed_eval(df, s)
        y2, p2 = patch.controlled_eval(df, s)
        out["seeds"][str(s)] = paired_bootstrap(y1, p1, y2, p2, a.n_boot, s)
    out["elapsed_s"] = time.time() - out.pop("t0")
    with open(a.out, "w") as f:
        json.dump(out, f)


if __name__ == "__main__":
    main()
