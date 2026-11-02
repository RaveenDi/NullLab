# NullLab security model

Written 2026-11-02. Plain version: **the sandbox is a restricted local process, not a container boundary.** It stops accidents and casual or
naive exfiltration (no key leak, no ground-truth read, no network, no process spawn). It is not designed to stop a determined attacker who
can run arbitrary native code. Anything below marked **UNVERIFIED** has not been tested on this project.

## What runs untrusted code

NullLab executes Python it did not write: the `train.py` of the pipeline under audit, plus patches produced by the planner (compiled from a
constrained edit DSL; the model does not write free code on the G9 path, but older paths ran model-written `controlled_eval` functions).
Workers: `sandbox/run.py`, `sandbox/run_factorial.py`, the worker in `agent/cached_exec.py`, the pre-flight runner in `agent/smoke.py`, and the
behaviour-guard worker in `agent/guard_g9.py --worker`.

## What is blocked (restricted-subprocess backend)

Order in every worker: `preload_heavy()` (library imports, `train.py` NOT imported) then `_block_network()` then `import train` and the patch
modules. Since 2026-11-02 the module-level code of an untrusted `train.py` therefore runs **under** the block. Before this fix `import train`
ran first, so top-level code had network, unrestricted `open()`, `subprocess` and `ctypes` (found by the SRE/security review of 2026-11-02).

Blocked inside the worker after the hook is installed:

- Network: `socket.socket`, `socket.create_connection`, `socket.getaddrinfo` are replaced; audit events `socket.connect` / `socket.bind` raise.
- File access: `open()` (any mode, including write) is allowed only inside the temp working directory and the Python installation
  (`sys.prefix`, `sys.base_prefix`, `sys.exec_prefix`). Paths are resolved with `realpath` first (absolute paths, `..`, 8.3 short names, symlinks).
  Paths containing `ground_truth` or `/nulllab/eval/` are refused outright.
- Process creation: `subprocess.Popen`, `os.system`, `os.startfile`, `os.spawn*`, `os.exec*`, `os.posix_spawn`, `_winapi.CreateProcess`.
- `os.link`, `os.symlink`, `os.rename`, `os.replace`, `shutil.copyfile`, `winreg.OpenKey`.
- New native libraries: `ctypes.dlopen`, `ctypes.dlsym` (libraries sklearn needs are pre-loaded by `preload_heavy()` first).
- The environment is scrubbed (`PATH`, `SYSTEMROOT`, temp vars only), so no `MODEL_API_KEY` or other secret is inherited.
- Evaluator files (`eval/ground_truth.json` and similar) are never copied into the work dir: only `train.py` and `data.csv` are.

Resource limits (`sandbox/limits.py`, all workers except the unverified Docker path):

- Wall clock: the existing per-call timeout; on timeout the whole process tree is killed.
- Windows: the child is created suspended, put into a **Job Object**, then resumed (it never runs outside the job). Limits: committed memory per
  process (default **6144 MB**, env `NULLLAB_SANDBOX_MEM_MB`), **active process limit** (1, or 2 when the interpreter is a venv launcher that
  starts the base interpreter as a child), kill-on-close (no orphans). A child stopped by a limit is reported as `status: "error"`, `limit:
  "memory limit"` or `"process limit"`, and a line `[nulllab-sandbox] ... exceeded` is prepended to its stderr.
- POSIX: `RLIMIT_AS` (same memory default / env var) and `RLIMIT_NPROC` (current user load + 256, env `NULLLAB_SANDBOX_NPROC`), own process group
  killed on timeout. **UNVERIFIED**: written on Windows, not run on Linux or macOS. `RLIMIT_NPROC` is per user and counts threads, so it bounds a
  fork storm, it does not prevent a single fork. `os.fork` is not on the audit-hook block list.

Tests: `tests/test_sandbox_hardening.py` (hostile top-level code against all five workers; memory bomb; spawn limit; byte-identical comparison
with the pre-fix sandbox) and the 11 exfiltration tests of `docs/EVAL-3.md` / `tests/test_nulllab.py`.

## What is NOT blocked or not guaranteed

- **Not a container.** It is one OS process with a Python-level audit hook. Pure-Python hooks can be bypassed by native code (a compiled
  extension the code can import from an allowed location, a bug in the interpreter or a library). The Docker path (`--network=none --read-only`,
  memory and pid caps) exists in `sandbox/executor.py` and the `Dockerfile` but has **never been built or run: UNVERIFIED**. Do not rely on it.
- The allow-listed Python prefix (stdlib, site-packages) is **readable**, so installed packages and their data files can be read.
- Writes **inside** the working directory are allowed (it is a throwaway temp dir, deleted afterwards). Unlink, `listdir`, `mmap` and `stat`
  are not hooked.
- The memory limit is per process (committed memory), not per tree; up to the active-process limit processes can each use it. CPU time and disk
  space inside the work dir have no limit beyond the wall-clock timeout. Threads are not limited on Windows.
- Side channels (timing, CPU load, the content of the returned result vectors, error messages) are not addressed. A patch decides what it returns.
- Prompt injection through comments or the excerpt that reaches the planner: partly mitigated (edit DSL, behavioural guard, smoke lint, hash-frozen
  prompts) but there is **no adversarial test set yet: UNVERIFIED**.
- The Windows limits come from Job Objects; if the job cannot be created or assigned (for example an enclosing job that forbids it) the code warns
  and runs unlimited, unless `NULLLAB_SANDBOX_REQUIRE_LIMITS=1` is set, which makes it fail closed.
- `app/server.py` has no authentication or rate limiting; run it on localhost only.
- Dependencies are not hash-locked (see the supply-chain notes in the 2026-11-02 SRE review).

## What leaves the machine

- **Rules-only / mock mode and CI:** nothing. No network, no secrets.
- **Live mode** (`--live`, CLI only; never from the web server): the planner prompts go to `https://api.meta.ai/v1` (Meta Model API) with the
  `MODEL_API_KEY` bearer. The prompt contains the pipeline source (`train.py`) and the paper excerpt, and a limited description of the data. The
  exact content of every prompt is logged in `runs_*/live_calls_*.jsonl`; **an up-front manifest of what leaves the machine is not built:
  UNVERIFIED**. Check the prompt builders in `agent/` before using private data.
- The headline runs used `muse-spark-1.3-contributor`: Meta **may train on the data** sent to it (see the Meta Model API documentation). Use it only with
  non-private, disguised data. Raw datasets are not sent; the sandbox runs locally.

## Reporting an issue

Open a GitHub issue on the repository for non-sensitive problems. For a sandbox escape, a way to read evaluator files, or anything that could leak
a key or private data, do not post details publicly: contact the maintainer privately (address on the maintainer's GitHub profile) and include the
`train.py`/patch that reproduces it. There is no bug bounty and no response-time guarantee.
