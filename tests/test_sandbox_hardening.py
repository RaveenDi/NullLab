"""Sandbox hardening (2026-11-02): the sandbox block must be active BEFORE the untrusted train.py module is executed, and child
processes are resource-limited. See docs/SECURITY.md.

Five worker types are attacked with a hostile train.py whose TOP-LEVEL code (module level, runs at import) tries:
  (a) a TCP connection to a local listening port, (b) reading a file outside the working dir, (c) writing a file outside it,
  (d) spawning a process, (e) loading a new ctypes library, (f) a memory bomb, (g) a process-spawn attempt (fork style).
Workers: sandbox/run.py (single), sandbox/run_factorial.py, agent/cached_exec.py, agent/smoke.py, agent/guard_g9.py (--worker).
Part (h) compares a legitimate pipeline byte-for-byte (ignoring elapsed times) with the pre-fix sandbox kept in
tests/fixtures/sandbox_baseline/ (verbatim copies of the baseline run.py / run_factorial.py).
"""
import json
import shutil
import socket
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import cached_exec, guard_g9, smoke  # noqa: E402
from sandbox import executor  # noqa: E402
from sandbox.limits import run_limited  # noqa: E402

BASELINE = ROOT / "tests" / "fixtures" / "sandbox_baseline"
CLEAN = ROOT / "corpus" / "clean_control"
BENIGN = "def controlled_eval(df, seed):\n    return [0, 1], [0, 1]\n"
WORKERS = ["run_single", "run_factorial", "cached_exec", "smoke", "guard_g9"]

# ------------------------------------------------------------------------------------------------ hostile payloads
ATTACKS = {
    "a_tcp_socket": "import socket\ns = socket.socket()\ns.settimeout(2)\ns.connect(('127.0.0.1', {port}))",
    "a_create_connection": "import socket\nsocket.create_connection(('127.0.0.1', {port}), 2)",
    "b_read_outside": "open(r'{outside_read}').read()",
    "c_write_outside": "open(r'{outside_write}', 'w').write('pwned')",
    "d_subprocess": "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'print(1)'])",
    "d_os_system": "import os\nos.system('echo pwned')",
    "e_ctypes_load": ("import ctypes\nctypes.WinDLL('shell32')" if sys.platform == "win32"
                      else "import ctypes\nctypes.CDLL('libm.so.6')"),
    "g_fork_style": "import multiprocessing as mp\np = mp.Process(target=len, args=([],))\np.start()\np.join()",
}
BOMB = ("chunks = []\nfor _ in range(30):  # 3 GB in total, capped on purpose so a missing limit cannot take the host down\n"
        "    chunks.append(bytearray(100 * 1024 * 1024))")


def hostile_train(stmt):
    """A train.py whose module-level code runs `stmt` and reports HOSTILE_BLOCKED / HOSTILE_SUCCEEDED (both end in an exception)."""
    body = "\n".join("    " + ln for ln in stmt.splitlines())
    return ("import sys\ntry:\n" + body + "\nexcept BaseException as e:\n    raise RuntimeError('HOSTILE_BLOCKED %r' % (e,))\n"
            "raise RuntimeError('HOSTILE_SUCCEEDED')\n\n"
            "def load(path='data.csv'):\n    return None\n\ndef claimed_eval(df, seed):\n    return [0, 1], [0, 1]\n")


def bomb_train():
    return BOMB + "\n\ndef load(path='data.csv'):\n    return None\n\ndef claimed_eval(df, seed):\n    return [0, 1], [0, 1]\n"


@pytest.fixture()
def listener():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)
    srv.settimeout(0.2)
    seen = []
    stop = threading.Event()

    def loop():
        while not stop.is_set():
            try:
                c, _ = srv.accept()
                seen.append(1)
                c.close()
            except OSError:
                pass
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    yield srv.getsockname()[1], seen
    stop.set()
    t.join(2)
    srv.close()


def make_case(tmp_path, train_src):
    d = tmp_path / "case"
    d.mkdir()
    (d / "train.py").write_text(train_src, encoding="utf-8")
    shutil.copy(CLEAN / "data.csv", d / "data.csv")
    return d


def run_worker(kind, case, tmp_path):
    """Run one worker type on `case`; returns (status, text) where text is everything the worker said about the failure."""
    if kind == "run_single":
        r = executor.run_experiment(case, BENIGN, seeds=(42,), n_boot=5, timeout=90, backend="subprocess")
    elif kind == "run_factorial":
        r = executor.run_factorial(case, {k: BENIGN for k in ("fix_A", "fix_B", "fix_both")}, seeds=(42,), timeout=90)
    elif kind == "cached_exec":
        r = cached_exec.run_factorial_cached(case, {k: BENIGN for k in ("fix_A", "fix_B", "fix_both")}, seeds=(42,), timeout=90,
                                             cache_dir=tmp_path / "cache", workers=1)
    elif kind == "smoke":
        tmp = tmp_path / "smoke"
        tmp.mkdir()
        shutil.copy(case / "train.py", tmp / "train.py")
        shutil.copy(case / "data.csv", tmp / "data.csv")
        for k in ("fix_A", "fix_B", "fix_both"):
            (tmp / f"{k}.py").write_text(BENIGN, encoding="utf-8")
        r = smoke._run_smoke(tmp, (42,), 90)
    elif kind == "guard_g9":
        t = guard_g9.trace_run((case / "train.py").read_text(encoding="utf-8"), case, seed=42, timeout=90)
        r = {"status": "ok" if t["status"] == "ok" else "error", "stderr": f"{t.get('error', '')}\n{t.get('tb', '')}",
             **({"limit": "memory limit"} if "memory limit" in (t.get("error") or "") else {})}
    else:
        raise AssertionError(kind)
    return r["status"], (r.get("stderr") or ""), r


# ------------------------------------------------------------------------------------------------ (a)-(e), (g): hostile top-level code
@pytest.mark.parametrize("attack", sorted(ATTACKS))
@pytest.mark.parametrize("kind", WORKERS)
def test_hostile_top_level_code_is_blocked(kind, attack, tmp_path, listener):
    if attack == "g_fork_style" and sys.platform != "win32":
        pytest.skip("POSIX fork path is bounded by RLIMIT_NPROC only; UNVERIFIED on this machine (see docs/SECURITY.md)")
    port, seen = listener
    outside_read = tmp_path / "secret.txt"
    outside_read.write_text("TOPSECRET", encoding="utf-8")
    outside_write = tmp_path / "pwned.txt"
    stmt = ATTACKS[attack].format(port=port, outside_read=outside_read, outside_write=outside_write)
    case = make_case(tmp_path, hostile_train(stmt))
    status, text, _ = run_worker(kind, case, tmp_path)
    assert status == "error", (kind, attack, status, text[-400:])
    assert "HOSTILE_BLOCKED" in text and "HOSTILE_SUCCEEDED" not in text, (kind, attack, text[-600:])
    assert "TOPSECRET" not in text
    assert not outside_write.exists()  # (c) nothing was written outside the working directory
    assert not seen  # (a) the listening port never saw a connection


# ------------------------------------------------------------------------------------------------ (f): memory bomb
@pytest.mark.parametrize("kind", WORKERS)
def test_memory_bomb_is_killed_and_reported(kind, tmp_path, monkeypatch):
    monkeypatch.setenv("NULLLAB_SANDBOX_MEM_MB", "1536")
    case = make_case(tmp_path, bomb_train())
    status, text, r = run_worker(kind, case, tmp_path)
    assert status == "error", (kind, status, text[-400:])
    assert r.get("limit") == "memory limit" or "memory limit" in text, (kind, r.get("limit"), text[-400:])


# ------------------------------------------------------------------------------------------------ (g) + limits unit tests
PLAIN_SPAWN = ("import subprocess, sys\n"
               "for i in range(4):\n    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
               "print('SPAWNED_ALL')\n")


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object path; the POSIX RLIMIT_NPROC path is UNVERIFIED here")
def test_job_object_limits_process_spawn_without_any_audit_hook():
    """A plain interpreter (no sandbox hook at all) cannot create more than the job's process limit."""
    r = run_limited([sys.executable, "-I", "-c", PLAIN_SPAWN], timeout=60)
    assert r.limits_applied
    assert r.returncode != 0 and "SPAWNED_ALL" not in r.stdout
    assert r.limit_hit == "process limit", r.stderr[-400:]


@pytest.mark.skipif(sys.platform != "win32", reason="Job Object path")
def test_job_object_memory_limit_without_any_audit_hook():
    code = "chunks = []\nfor _ in range(30):\n    chunks.append(bytearray(100 * 1024 * 1024))\nprint('ALLOCATED')\n"
    r = run_limited([sys.executable, "-I", "-c", code], timeout=60, mem_mb=1024)
    assert r.returncode != 0 and "ALLOCATED" not in r.stdout
    assert r.limit_hit == "memory limit"
    assert "memory limit exceeded (1024 MB)" in r.stderr


def test_run_limited_ok_and_timeout():
    r = run_limited([sys.executable, "-I", "-c", "print('hi')"], timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == "hi" and r.limit_hit is None
    import time
    t0 = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        run_limited([sys.executable, "-I", "-c", "import time; time.sleep(60)"], timeout=3)
    assert time.time() - t0 < 30


def test_mem_limit_env_override(monkeypatch):
    from sandbox import limits
    monkeypatch.setenv("NULLLAB_SANDBOX_MEM_MB", "777")
    assert limits._mem_limit(None) == 777
    monkeypatch.delenv("NULLLAB_SANDBOX_MEM_MB")
    assert limits._mem_limit(None) == limits.DEFAULT_MEM_MB == 6144
    assert limits._mem_limit(900) == 900


def test_preload_heavy_does_not_import_train(tmp_path):
    code = ("import sys, os\nsys.path.insert(0, os.getcwd())\nfrom run import preload_heavy\npreload_heavy()\n"
            "print('train' in sys.modules, 'sklearn.ensemble' in sys.modules, 'pandas' in sys.modules)\n")
    d = tmp_path / "w"
    d.mkdir()
    shutil.copy(ROOT / "sandbox" / "run.py", d / "run.py")
    (d / "train.py").write_text("raise SystemExit('train imported')\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "-I", "-c", code], check=False, cwd=str(d), env=executor._scrubbed_env(), capture_output=True, text=True, timeout=90)
    assert r.returncode == 0 and r.stdout.split() == ["False", "True", "True"], r.stderr[-400:]


# ------------------------------------------------------------------------------------------------ (h) byte-identical with the baseline
GENERIC_A = "import train\n\ndef controlled_eval(df, seed):\n    return train.claimed_eval(df, seed + 1000)\n"
GENERIC_B = "import train\n\ndef controlled_eval(df, seed):\n    return train.claimed_eval(df, seed + 2000)\n"
GENERIC_BOTH = "import train\n\ndef controlled_eval(df, seed):\n    return train.claimed_eval(df, seed + 3000)\n"
GENERIC = {"fix_A": GENERIC_A, "fix_B": GENERIC_B, "fix_both": GENERIC_BOTH}


def _strip(result):
    r = dict(result)
    r.pop("elapsed_s", None)
    return json.dumps(r)  # key order and number formatting included: this is the byte-level comparison


def old_single(case, patch_src, tmp, seeds, n_boot):
    tmp.mkdir()
    for n in ("train.py", "data.csv"):
        shutil.copy(case / n, tmp / n)
    shutil.copy(BASELINE / "run.py", tmp / "run.py")
    (tmp / "patch.py").write_text(patch_src, encoding="utf-8")
    cmd = [sys.executable, "-I", "run.py", "--seeds", ",".join(map(str, seeds)), "--n-boot", str(n_boot), "--out", "result.json"]
    r = subprocess.run(cmd, check=False, cwd=str(tmp), env=executor._scrubbed_env(), capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads((tmp / "result.json").read_text())


def old_factorial(case, patches, tmp, seeds):
    tmp.mkdir()
    for n in ("train.py", "data.csv"):
        shutil.copy(case / n, tmp / n)
    for n in ("run.py", "run_factorial.py"):
        shutil.copy(BASELINE / n, tmp / n)
    for k, v in patches.items():
        (tmp / f"{k}.py").write_text(v, encoding="utf-8")
    cmd = [sys.executable, "-I", "run_factorial.py", "--seeds", ",".join(map(str, seeds)), "--out", "result.json"]
    r = subprocess.run(cmd, check=False, cwd=str(tmp), env=executor._scrubbed_env(), capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stderr[-800:]
    return json.loads((tmp / "result.json").read_text())


@pytest.mark.parametrize("name", ["leak_prescale", "clean_control", "leak_group", "leak_proxy", "leak_temporal", "clean_group_correct"])
def test_single_pipeline_byte_identical_to_baseline(name, tmp_path):
    case = ROOT / "corpus" / name
    old = old_single(case, GENERIC_A, tmp_path / "old", (42, 43), 40)
    new = executor.run_experiment(case, GENERIC_A, seeds=(42, 43), n_boot=40, timeout=300, backend="subprocess")
    assert new["status"] == "ok", new
    assert _strip(new["result"]) == _strip(old)


@pytest.mark.parametrize("name", ["comp_visit_history", "g4_assay_replicates", "g4_freight_delay", "g4_pump_inspection",
                                  "g4_visit_history_clean", pytest.param("g4_crop_irrigation", marks=pytest.mark.slow)])
def test_factorial_pipeline_byte_identical_to_baseline(name, tmp_path):
    case = ROOT / "factorial" / name
    old = old_factorial(case, GENERIC, tmp_path / "old", (42,))
    new = executor.run_factorial(case, GENERIC, seeds=(42,), timeout=600)
    assert new["status"] == "ok", new
    assert _strip(new["result"]) == _strip(old)


def test_cached_exec_byte_identical_to_baseline(tmp_path):
    """The parallel / cached worker (also preloaded + blocked before import train) agrees with the old serial sandbox."""
    case = ROOT / "factorial" / "comp_visit_history"
    old = old_factorial(case, GENERIC, tmp_path / "old", (42, 43))
    cx = cached_exec.run_factorial_cached(case, GENERIC, seeds=(42, 43), timeout=600, cache_dir=tmp_path / "cache", workers=2)
    assert cx["status"] == "ok", cx
    assert _strip(cx["result"]) == _strip(old)


def _recorded_sources(case_name, train_src):
    """Compiled fix_A / fix_B / fix_both of the recorded FINAL plans in the run files (candidates, best first)."""
    from agent import fidelity
    out = []
    for f in ("runs_g9/r1.json", "runs_g9b/r4.json", "runs_g9/r2.json", "runs_g9/r3.json", "runs_g9b/r5.json", "runs_g7/r3.json"):
        p = ROOT / f
        if p.exists():
            rec = json.loads(p.read_text(encoding="utf-8")).get("loop", {}).get(case_name)
            fa = ((rec or {}).get("sources") or {}).get("fix_all")  # G9 runs record the compiled fixed source (it defines controlled_eval)
            if isinstance(fa, str):
                out.append((f, {k: fa for k in GENERIC}))
            edits = ((rec or {}).get("final_plan") or {}).get("edits")
            if edits:
                cfgs = fidelity.build_configs(train_src, edits)
                if all(cfgs[k]["src"] for k in GENERIC):
                    out.append((f, {k: cfgs[k]["src"] for k in GENERIC}))
    return out


@pytest.mark.slow
@pytest.mark.parametrize("name", ["ehg_disguised", "civilwar_disguised"])
def test_real_case_byte_identical_to_baseline(name, tmp_path):
    """Downsampled real case (same rows for old and new), recorded final-plan sources where a run file has them, else the generic fixed patch."""
    src = ROOT / "real" / name
    if not (src / "data.csv").exists():
        pytest.skip("gitignored real data absent")
    case = tmp_path / "case"
    case.mkdir()
    shutil.copy(src / "train.py", case / "train.py")
    train_src = (src / "train.py").read_text(encoding="utf-8")
    smoke.downsample_csv(src / "data.csv", case / "data.csv", 600 if name.startswith("ehg") else 250, smoke.target_of(train_src))
    old = patches = used = None
    for i, (f, cand) in enumerate(_recorded_sources(name, train_src)[:1]):
        try:
            old, patches, used = old_factorial(case, cand, tmp_path / f"old{i}", (42,)), cand, f"recorded final plan of {f}"
        except AssertionError:
            pass  # recorded source does not run on the downsample (size-sensitive): fall back
    if old is None:
        patches, used = GENERIC, "generic fixed patch"
        old = old_factorial(case, patches, tmp_path / "oldg", (42,))
    new = executor.run_factorial(case, patches, seeds=(42,), timeout=900)
    assert new["status"] == "ok", new
    assert _strip(new["result"]) == _strip(old), used
    print(f"{name}: byte-identical with {used} patches")
