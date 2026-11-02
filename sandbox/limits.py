"""Resource limits for sandbox child processes (memory, process count, wall clock).

    run_limited(cmd, cwd, env, timeout, mem_mb=None) -> subprocess.CompletedProcess   (+ .limit_hit, .limits_applied)

Raises subprocess.TimeoutExpired on timeout (the whole process tree is killed first), exactly like subprocess.run.
`limit_hit` is None, "memory limit" or "process limit": set when the child failed and the evidence says a limit stopped it.

Windows : the child is created SUSPENDED, assigned to a Job Object, then resumed, so it never runs outside the job.
          JOB_OBJECT_LIMIT_PROCESS_MEMORY (per-process committed memory), JOB_OBJECT_LIMIT_ACTIVE_PROCESS (see _max_procs),
          JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (no orphans when the parent dies or the job handle closes).
POSIX   : resource limits applied in the child before exec (RLIMIT_AS; RLIMIT_NPROC when it can be sized safely). UNTESTED on this
          machine (written on Windows); see docs/SECURITY.md.

Memory default 6144 MB, override with env NULLLAB_SANDBOX_MEM_MB (or the mem_mb argument). Not a security boundary on its own:
the file / network / spawn bans live in sandbox/run.py::_block_network; this module bounds resource exhaustion.
"""
import os
import subprocess
import sys
import warnings

DEFAULT_MEM_MB = 6144


def _mem_limit(mem_mb):
    if mem_mb is None:
        try:
            mem_mb = int(os.environ.get("NULLLAB_SANDBOX_MEM_MB") or DEFAULT_MEM_MB)
        except ValueError:
            mem_mb = DEFAULT_MEM_MB
    return max(64, int(mem_mb))


def _classify(returncode, stderr, mem_hit):
    """Name the limit that (most likely) stopped a failed child, from the job's peak memory and the child's own error text."""
    if returncode == 0:
        return None
    low = (stderr or "").lower()
    if mem_hit or "memoryerror" in low or "unable to allocate" in low or "cannot allocate memory" in low:
        return "memory limit"
    if ("winerror 1816" in low or "not enough quota" in low or "winerror 1455" in low or "resource temporarily unavailable" in low
            or "cannot fork" in low or "blockingioerror" in low):
        return "process limit"
    return None


def _finish(cp, limit_hit, mem_mb, applied):
    cp.limit_hit = limit_hit
    cp.limits_applied = applied
    cp.mem_limit_mb = mem_mb
    if limit_hit:
        note = f"[nulllab-sandbox] {limit_hit} exceeded" + (f" ({mem_mb} MB)" if limit_hit == "memory limit" else "") + "\n"
        cp.stderr = note + (cp.stderr or "")
    return cp


# ------------------------------------------------------------------------------------------------ Windows
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    _K32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _NT = ctypes.WinDLL("ntdll")

    class _BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class _IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ("ReadOps", "WriteOps", "OtherOps", "ReadBytes", "WriteBytes", "OtherBytes")]

    class _EXT(ctypes.Structure):
        _fields_ = [("Basic", _BASIC), ("Io", _IO), ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    _K32.CreateJobObjectW.restype = wintypes.HANDLE
    _K32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    _K32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    _K32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p]
    _K32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    _K32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    _K32.CloseHandle.argtypes = [wintypes.HANDLE]
    _NT.NtResumeProcess.argtypes = [wintypes.HANDLE]

    _LIMIT_ACTIVE_PROCESS, _LIMIT_PROCESS_MEMORY, _LIMIT_KILL_ON_CLOSE = 0x8, 0x100, 0x2000
    _EXT_INFO_CLASS = 9
    _CREATE_SUSPENDED = 0x4

    def _max_procs():
        """Processes allowed in the job. 1 for a real interpreter; 2 when sys.executable is a venv launcher (python.exe in a
        venv's Scripts dir starts the base interpreter as a child, so the legitimate tree is two processes)."""
        try:
            return 2 if os.path.normcase(os.path.realpath(sys.prefix)) != os.path.normcase(os.path.realpath(sys.base_prefix)) else 1
        except Exception:  # noqa: BLE001
            return 2

    def _make_job(mem_mb, max_procs):
        job = _K32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObject failed")
        info = _EXT()
        info.Basic.LimitFlags = _LIMIT_ACTIVE_PROCESS | _LIMIT_PROCESS_MEMORY | _LIMIT_KILL_ON_CLOSE
        info.Basic.ActiveProcessLimit = max_procs
        info.ProcessMemoryLimit = mem_mb * 1024 * 1024
        if not _K32.SetInformationJobObject(job, _EXT_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info)):
            err = ctypes.get_last_error()
            _K32.CloseHandle(job)
            raise OSError(err, "SetInformationJobObject failed")
        return job

    def _peak_mb(job):
        info = _EXT()
        if _K32.QueryInformationJobObject(job, _EXT_INFO_CLASS, ctypes.byref(info), ctypes.sizeof(info), None):
            return info.PeakProcessMemoryUsed / (1024 * 1024)
        return 0.0

    def run_limited(cmd, cwd=None, env=None, timeout=None, mem_mb=None, max_procs=None):
        mem = _mem_limit(mem_mb)
        job = None
        try:
            job = _make_job(mem, max_procs or _max_procs())
        except OSError as e:
            if os.environ.get("NULLLAB_SANDBOX_REQUIRE_LIMITS"):
                raise
            warnings.warn(f"sandbox resource limits NOT applied: {e}")
        flags = _CREATE_SUSPENDED if job else 0
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=flags)
        applied = False
        try:
            if job:
                if _K32.AssignProcessToJobObject(job, int(proc._handle)):
                    applied = True
                elif os.environ.get("NULLLAB_SANDBOX_REQUIRE_LIMITS"):
                    proc.kill()
                    raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject failed")
                else:
                    warnings.warn("sandbox resource limits NOT applied: AssignProcessToJobObject failed")
                _NT.NtResumeProcess(int(proc._handle))
            try:
                out, err = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                if job:
                    _K32.TerminateJobObject(job, 1)
                proc.kill()
                proc.communicate()
                raise
            mem_hit = applied and mem >= 64 and _peak_mb(job) >= 0.9 * mem
            cp = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
            return _finish(cp, _classify(proc.returncode, err, mem_hit), mem, applied)
        finally:
            if job:
                _K32.TerminateJobObject(job, 1)  # nothing may outlive the call
                _K32.CloseHandle(job)

# ------------------------------------------------------------------------------------------------ POSIX
else:
    def _user_procs():
        """Number of tasks (processes + threads) owned by this user, or None if it cannot be counted (non-Linux)."""
        try:
            uid, n = os.getuid(), 0
            for d in os.listdir("/proc"):
                if d.isdigit():
                    try:
                        if os.stat(f"/proc/{d}").st_uid == uid:
                            n += len(os.listdir(f"/proc/{d}/task"))
                    except OSError:
                        pass
            return n
        except Exception:  # noqa: BLE001
            return None

    def run_limited(cmd, cwd=None, env=None, timeout=None, mem_mb=None, max_procs=None):
        import resource
        import signal
        mem = _mem_limit(mem_mb)
        nproc = None
        if max_procs:
            nproc = int(max_procs)
        elif os.environ.get("NULLLAB_SANDBOX_NPROC"):
            nproc = int(os.environ["NULLLAB_SANDBOX_NPROC"])
        else:  # RLIMIT_NPROC is per user and counts threads: allow the current load + headroom for BLAS / joblib threads only
            cur = _user_procs()
            nproc = cur + 256 if cur is not None else None

        def _pre():
            os.setsid()  # own process group: the timeout kills the whole tree
            resource.setrlimit(resource.RLIMIT_AS, (mem * 1024 * 1024, mem * 1024 * 1024))
            if nproc:
                resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        proc = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, preexec_fn=_pre)
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                proc.kill()
            proc.communicate()
            raise
        finally:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
        cp = subprocess.CompletedProcess(cmd, proc.returncode, out, err)
        return _finish(cp, _classify(proc.returncode, err, False), mem, True)


def limit_note(cp):
    """Fields a caller merges into an error result: {} when no limit was hit."""
    return {"limit": cp.limit_hit} if getattr(cp, "limit_hit", None) else {}


__all__ = ["run_limited", "limit_note", "DEFAULT_MEM_MB"]
