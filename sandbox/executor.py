"""Launches sandbox/run.py against an agent-view case dir + a patch. Backends:
  docker     : `docker run --network=none --read-only` (only if `docker info` answers quickly)
  subprocess : restricted fallback (isolated interpreter, scrubbed env, temp dir copy, network blocked in-process, timeout)
The ground-truth dir is never copied into the sandbox."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = "nulllab-sandbox:latest"


def docker_available() -> bool:
    if os.environ.get("NULLLAB_NO_DOCKER"):
        return False
    try:
        r = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, timeout=6)
        return r.returncode == 0 and bool(r.stdout.strip())
    except Exception:
        return False


def _scrubbed_env():
    keep = ("SYSTEMROOT", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT", "WINDIR")
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    env["PYTHONHASHSEED"] = "0"
    env["OMP_NUM_THREADS"] = "1"
    return env  # no MODEL_API_KEY or any other secret is forwarded


def run_experiment(case_dir, patch_src, seeds=(42, 43, 44), n_boot=1000, timeout=120, backend=None):
    """Returns {"status": "ok"|"timeout"|"error", "backend":..., "result":..., "stderr":...}"""
    case_dir = Path(case_dir)
    backend = backend or ("docker" if docker_available() else "subprocess")
    tmp = Path(tempfile.mkdtemp(prefix="nulllab_"))
    try:
        for name in ("train.py", "data.csv"):  # explicit allow-list: excerpt/ground-truth never enter the sandbox
            shutil.copy(case_dir / name, tmp / name)
        shutil.copy(ROOT / "sandbox" / "run.py", tmp / "run.py")
        (tmp / "patch.py").write_text(patch_src, encoding="utf-8")
        args = ["run.py", "--seeds", ",".join(map(str, seeds)), "--n-boot", str(n_boot), "--out", "result.json"]
        if backend == "docker":
            cmd = ["docker", "run", "--rm", "--network=none", "--read-only", "--tmpfs", "/tmp", "-v", f"{tmp}:/work",
                   "-w", "/work", IMAGE, "python"] + args
            env = None
        else:
            cmd = [sys.executable, "-I"] + args
            env = _scrubbed_env()
        try:
            r = subprocess.run(cmd, cwd=str(tmp), env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "backend": backend, "timeout_s": timeout}
        if r.returncode != 0 or not (tmp / "result.json").exists():
            return {"status": "error", "backend": backend, "stderr": r.stderr[-1500:]}
        return {"status": "ok", "backend": backend, "result": json.loads((tmp / "result.json").read_text())}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def run_factorial(case_dir, patches, seeds=(42, 43, 44), timeout=300):
    """2x2 factorial in the restricted-subprocess sandbox. patches = {"fix_A": src, "fix_B": src, "fix_both": src}.
    Returns raw per-seed y/p vectors for orig + the 3 fixes; statistics are computed by the caller."""
    case_dir = Path(case_dir)
    tmp = Path(tempfile.mkdtemp(prefix="nulllab_fx_"))
    try:
        for name in ("train.py", "data.csv"):
            shutil.copy(case_dir / name, tmp / name)
        for name in ("run.py", "run_factorial.py"):
            shutil.copy(ROOT / "sandbox" / name, tmp / name)
        for k in ("fix_A", "fix_B", "fix_both"):
            (tmp / f"{k}.py").write_text(patches[k], encoding="utf-8")
        cmd = [sys.executable, "-I", "run_factorial.py", "--seeds", ",".join(map(str, seeds)), "--out", "result.json"]
        try:
            r = subprocess.run(cmd, cwd=str(tmp), env=_scrubbed_env(), capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "backend": "subprocess", "timeout_s": timeout}
        if r.returncode != 0 or not (tmp / "result.json").exists():
            return {"status": "error", "backend": "subprocess", "stderr": r.stderr[-2000:]}
        return {"status": "ok", "backend": "subprocess", "result": json.loads((tmp / "result.json").read_text())}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
