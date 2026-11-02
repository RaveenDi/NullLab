"""Faster, output-identical drop-in for sandbox/executor.run_factorial (G9, EVAL-12 'Robustness'). WRAPS the sandbox; nothing in sandbox/* is edited.

What it changes (and nothing else):
  * The 'orig' configuration (train.claimed_eval) does not depend on the model's patch. Its result per seed is cached under
    sha256(train.py, data.csv, seed, library versions, runner file, sandbox env) -> y_true / y_score vectors. Reused across repairs, repeats and plans of the same case.
  * The remaining (config, seed) jobs run in parallel worker PROCESSES (restricted subprocesses, one interpreter each; same `-I`, scrubbed env,
    PYTHONHASHSEED=0, OMP_NUM_THREADS=1, sandbox/run._block_network() as in sandbox/run_factorial.py) instead of one long serial loop.
  * Same return shape as executor.run_factorial: {'status': 'ok'|'error'|'timeout', 'backend', 'result' | 'stderr'}. result == the uncached result
    except the wall-clock field 'elapsed_s' (a timing measurement; compare with strip_timing()). Everything the statistics read (the per-seed
    y and p vectors, 'metric') is byte-identical; tests/test_cached_exec.py checks that on a small corpus case.

Safe fallback: if any source uses process-global randomness (np.random.<fn>, random.<fn>), results could depend on the order of the serial
loop, so this module calls the unchanged executor.run_factorial instead (reason in ex['cached_exec']['fallback']).
Cache correctness limit: the key covers train.py + data + seed + library versions + the runner; it does not cover the OS/CPU. Same machine, same venv: identical."""
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("NULLLAB_EXEC_CACHE") or ROOT / "runs_cache")
CONFIGS = ("fix_A", "fix_B", "fix_both")
SAFE_NP_RANDOM = {"default_rng", "Generator", "RandomState", "SeedSequence", "PCG64", "Philox", "SFC64", "MT19937", "BitGenerator"}
LIBS = ("numpy", "pandas", "scikit-learn", "scipy")

WORKER = r'''import importlib.util, json, os, sys
sys.path.insert(0, os.getcwd())
import numpy  # noqa: F401  heavy imports before the network / file allow-list is applied
import train
try:  # same pre-load as sandbox/run_factorial.py
    from sklearn.neighbors import KNeighborsClassifier
    KNeighborsClassifier(n_neighbors=1).fit([[0.0], [1.0]], [0, 1]).predict([[0.2]])
except Exception:
    pass
from run import _block_network
_block_network()
jobs = json.loads(sys.argv[1])   # [[config, seed], ...]
mods = {}
for c in sorted({c for c, _ in jobs if c != "orig"}):
    spec = importlib.util.spec_from_file_location(c, c + ".py")
    mods[c] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mods[c])
df = train.load("data.csv")
metric = getattr(train, "METRIC", "accuracy")
conv = int if metric == "accuracy" else float
out = {"metric": metric, "res": {}}
for c, s in jobs:
    y, p = train.claimed_eval(df, s) if c == "orig" else mods[c].controlled_eval(df, s)
    out["res"][c + "|" + str(s)] = {"y": [int(v) for v in y], "p": [conv(v) for v in p]}
json.dump(out, open(sys.argv[2], "w"))
'''


@lru_cache(maxsize=1)
def library_versions():
    """Versions as seen by the sandbox interpreter (same sys.executable, isolated mode)."""
    code = ("import sys, json, importlib.metadata as m\n"
            "d = {'python': sys.version}\n"
            f"for n in {LIBS!r}:\n"
            "    try:\n        d[n] = m.version(n)\n    except Exception:\n        d[n] = None\n"
            "print(json.dumps(d, sort_keys=True))")
    r = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout.strip().splitlines()[-1])


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def cache_key(train_src, data_bytes, seed, versions=None, runner_sha=None):
    payload = {"train_py": _sha(train_src if isinstance(train_src, bytes) else train_src.encode("utf-8")), "data": _sha(data_bytes), "seed": int(seed),
               "versions": versions or library_versions(), "runner": runner_sha or _sha((ROOT / "sandbox" / "run_factorial.py").read_bytes()),
               "env": {"PYTHONHASHSEED": "0", "OMP_NUM_THREADS": "1"}, "kind": "orig_v1"}
    return _sha(json.dumps(payload, sort_keys=True).encode())


def uses_global_randomness(src):
    """True if the source calls the process-global RNGs (np.random.<fn> other than the generator constructors, or random.<fn>)."""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False
    rand_mod = any(isinstance(n, ast.Import) and any(a.name == "random" and not a.asname for a in n.names) for n in ast.walk(tree))
    for n in ast.walk(tree):
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        f = n.func
        if isinstance(f.value, ast.Attribute) and f.value.attr == "random" and isinstance(f.value.value, ast.Name) and f.value.value.id in ("np", "numpy"):
            if f.attr not in SAFE_NP_RANDOM:
                return True
        if rand_mod and isinstance(f.value, ast.Name) and f.value.id == "random":
            return True
    return False


def strip_timing(result):
    """The result without wall-clock fields: what must be identical between the cached and the uncached run."""
    r = dict(result)
    r.pop("elapsed_s", None)
    return r


def canonical(result):
    return json.dumps(strip_timing(result), sort_keys=False)


def _cache_get(key, cache_dir):
    p = Path(cache_dir) / f"{key}.json"
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    except (OSError, ValueError):
        return None


def _cache_put(key, obj, cache_dir):
    d = Path(cache_dir)
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f)
    os.replace(tmp, d / f"{key}.json")  # atomic; two writers of the same key write the same bytes


def _worker_env():
    from sandbox import executor
    return executor._scrubbed_env()


def _run_worker(tmp, jobs, tag, timeout):
    out = tmp / f"out_{tag}.json"
    cmd = [sys.executable, "-I", "cx_worker.py", json.dumps(jobs), out.name]
    try:
        r = subprocess.run(cmd, cwd=str(tmp), env=_worker_env(), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    if r.returncode != 0 or not out.exists():
        return {"status": "error", "stderr": r.stderr[-2000:]}
    return {"status": "ok", **json.loads(out.read_text(encoding="utf-8"))}


def run_factorial_cached(case_dir, patches, seeds=(42, 43, 44), timeout=300, workers=None, cache_dir=None, use_cache=True):
    """Drop-in for sandbox.executor.run_factorial(case_dir, patches, seeds, timeout). Adds ex['cached_exec'] with what was reused / how long it took."""
    from sandbox import executor
    case_dir, cache_dir = Path(case_dir), Path(cache_dir or CACHE_DIR)
    t0 = time.time()
    train_src = (case_dir / "train.py").read_text(encoding="utf-8")
    for name, src in [("train.py", train_src)] + [(k, patches[k]) for k in CONFIGS]:
        if uses_global_randomness(src):
            ex = getattr(executor, "_run_factorial_original", executor.run_factorial)(case_dir, patches, seeds=seeds, timeout=timeout)
            ex["cached_exec"] = {"fallback": f"{name} uses process-global randomness; ran the unchanged serial executor", "wall_s": round(time.time() - t0, 2)}
            return ex
    data_bytes = (case_dir / "data.csv").read_bytes()
    seeds = [int(s) for s in seeds]
    keys = {s: cache_key(train_src, data_bytes, s) for s in seeds}
    orig = {s: (_cache_get(keys[s], cache_dir) if use_cache else None) for s in seeds}
    hits = [s for s in seeds if orig[s] is not None]
    jobs = [("orig", s) for s in seeds if orig[s] is None] + [(c, s) for s in seeds for c in CONFIGS]
    n_workers = max(1, min(workers or min(os.cpu_count() or 2, 6), len(jobs)))
    tmp = Path(tempfile.mkdtemp(prefix="nulllab_cx_"))
    try:
        for name in ("train.py", "data.csv"):
            shutil.copy(case_dir / name, tmp / name)
        shutil.copy(ROOT / "sandbox" / "run.py", tmp / "run.py")
        (tmp / "cx_worker.py").write_text(WORKER, encoding="utf-8")
        for k in CONFIGS:
            (tmp / f"{k}.py").write_text(patches[k], encoding="utf-8")
        # longest jobs first would need a cost model; all jobs cost about the same, so deal them round-robin
        chunks = [jobs[i::n_workers] for i in range(n_workers)]
        remaining = lambda: max(1.0, timeout - (time.time() - t0))  # noqa: E731
        with ThreadPoolExecutor(n_workers) as ex_:
            outs = list(ex_.map(lambda ic: _run_worker(tmp, [list(j) for j in ic[1]], str(ic[0]), remaining()), enumerate(chunks)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for o in outs:
        if o["status"] == "timeout":
            return {"status": "timeout", "backend": "subprocess", "timeout_s": timeout}
    for o in outs:
        if o["status"] != "ok":
            return {"status": "error", "backend": "subprocess", "stderr": o.get("stderr", "")}
    flat, metric = {}, None
    for o in outs:
        flat.update(o["res"])
        metric = o["metric"]
    result = {"seeds": {}, "metric": metric}
    for s in seeds:
        if orig[s] is None:
            orig[s] = flat[f"orig|{s}"]
            if use_cache:
                _cache_put(keys[s], orig[s], cache_dir)
        res = {"orig": orig[s]}
        for c in CONFIGS:
            res[c] = flat[f"{c}|{s}"]
        result["seeds"][str(s)] = res
    result["elapsed_s"] = time.time() - t0
    return {"status": "ok", "backend": "subprocess", "result": result,
            "cached_exec": {"orig_cache_hits": hits, "orig_computed": [s for s in seeds if s not in hits], "workers": n_workers,
                            "jobs_run": len(jobs), "wall_s": round(time.time() - t0, 2)}}


def install():
    """Rebind sandbox.executor.run_factorial to the cached version (process-wide; for NEW drivers only, never inside the live G8 process).
    factorial_g8._run_executor imports the module at call time, so the swap takes effect."""
    from sandbox import executor
    if not hasattr(executor, "_run_factorial_original"):
        executor._run_factorial_original = executor.run_factorial
    executor.run_factorial = run_factorial_cached


def uninstall():
    from sandbox import executor
    if hasattr(executor, "_run_factorial_original"):
        executor.run_factorial = executor._run_factorial_original
        del executor._run_factorial_original
