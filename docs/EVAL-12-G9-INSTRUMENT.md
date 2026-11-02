# EVAL-12 / G9 instrument: Robustness

Written Mon Nov 2, 2026. Offline work only: no live API call, no spend, no edit to any file frozen by `docs/EVAL-9-G8-PREREG.md`
(`agent/llm.py`, `agent/factorial_g7.py`, `agent/factorial_g8.py`, `agent/fidelity.py`, `sandbox/*`, `runs_g8/` are untouched; their sha256 were re-checked at the end).
The DSL half of G9 is in `docs/EVAL-12-G9-DSL.md` (another builder). This file is the **Robustness** section: what failed in G7/G8 for reasons that are not the model,
and the three instrument pieces that remove those causes. None of it changes the question, the cases, the guard rules or the acceptance numbers of any earlier run.

## 1. Causes, from `forensics.md` / `architect.md`
| Failure | Cause | Piece |
|---|---|---|
| G8 r1 leaky: `TimeoutError`, case filed as `api_error` | `llm.py` `urlopen(timeout=300)` is a per-read socket timeout (no total deadline), no retry; the failure was recorded as the case outcome and never re-rolled | `agent/transport.py` |
| G7 r3: `to_numpy(kind=...)` `TypeError` after the plan was ACCEPTED, found after minutes in the sandbox | nothing ran the compiled code before the long run | `agent/smoke.py` |
| about 7 minutes per civil-war case, 3 cases sharing the CPU | inferred, not profiled | profile in section 4, `agent/cached_exec.py` |

## 2. `agent/transport.py` (task 1)
A drop-in for `llm.live_complete_ex` / `llm.live_complete` (same signature, same return). It **wraps** `llm`: it imports and reuses `_key`, `spend_ok`, the phase logs,
`MAX_G8_CALLS` / `MAX_G7_CALLS` / `MAX_LIVE_CALLS`, `_LOCK`, `_trace`, `replaying()` and `BS`; nothing in `llm.py` is edited. `transport.install()` rebinds the two names in a NEW
driver process; it must never be called inside the live G8 process. The key is read by `llm._key()` at call time and appears only in the request header.

* **Deadlines.** Each attempt runs in a daemon worker; the caller stops waiting after `attempt_deadline` (420 s) and the whole logical call after `total_deadline` (1500 s),
  so a socket that trickles bytes for ever cannot block the pipeline. `read_timeout` (300 s) remains the socket timeout. Optional streaming (`stream=True` or `NULLLAB_TRANSPORT_STREAM=1`):
  the socket timeout then acts as an idle timeout between chunks. **Streaming is UNVERIFIED against api.meta.ai** (parser tested on mocked SSE only); the default is non-streaming.
* **Retries.** 2 retries (3 attempts) with backoff 4 s, 12 s (`Retry-After` honoured, capped at 60 s) on: timeout, connection error/reset, truncated body, partial stream, HTTP 429/500/502/503/504.
  Other 4xx fail at once. The spend gate is re-checked before every retry. Spend is estimated like `llm.py` (a failed call is estimated once); an attempt that may have been billed
  (timeout, truncated body, partial stream) is charged again, a 429/5xx answered up front is not.
* **Retries are not repairs and select nothing.** Transport retries go to `<phase log>.transport.jsonl` (`counted_as_model_repair: false`), not to the phase call log, so `MAX_G8_CALLS`
  and `factorial_g8.CaseBudget` do not see them. Rationale, to be stated in the G9 preregistration: *a call for which no reply was received yields no sample, so re-asking draws the first observed sample;
  a reply that was received is never re-rolled* (empty content is a model outcome, as in `llm.py`: traced, then `LiveNotAllowed`). A call that timed out may still be billed by the provider: UNVERIFIED, the estimate covers it.
* **`api_error` only after exhaustion.** The final failure is `TransportError(OSError)`, which `factorial_g8.pipeline` already files as harness failure `api_error`.
* **Idempotent resume.** A transport failure writes no trace and no usage record. `factorial_g8.run` skips cases that have a record, so `transport.forget_transport_failures(runs_xx/r<k>.json)`
  removes the `api_error` records caused by transport failures (model-verdict records are never touched) and the next `run` re-runs those cases.
* **Tests** (`tests/test_transport.py`, 18, all mocked: opener, spend gate, key, sleep): success path keeps the log/usage/trace record formats; 503 then success completes with the retry logged apart; 429 with `Retry-After`;
  hang cut by the hard deadline and retried; a trickling socket cannot exceed the total deadline; three 503s give `TransportError` after exactly 2 retries and no trace/usage record; 4xx not retried;
  read timeout, truncated body, connection reset, partial stream and mid-stream cut retried; empty content not retried; spend gate and call cap kept; gate re-checked before a retry; routed through
  `factorial_g8.CaseBudget.call` (the retry is invisible to the budget, no repair spent) and through `factorial_g8.pipeline` (`api_error` only after exhaustion, resume re-runs it).

## 3. `agent/smoke.py` (task 2)
Run after the static guard accepts a plan and before the long sandbox run: `smoke.check_plan(case_dir, plan)` (or `smoke.smoke(case_dir, patches)` on compiled sources).

1. **Lint** of fix_A / fix_B / fix_both: syntax error and "name is bound nowhere in the file" with stdlib `ast` (flow-insensitive on purpose: it can only report names that cannot exist, so no false alarms).
   pyflakes is used instead when importable; it is **not installed in `.venv`, that branch is untested (UNVERIFIED)**.
2. **Smoke execution** in a restricted subprocess of the same kind as the sandbox (same interpreter and pinned libraries, scrubbed env, `-I`, `sandbox/run._block_network`): `controlled_eval` of the three configs
   for one seed on a 200-row copy of `data.csv`. Rows are evenly spaced **within each class** in the original order (never shuffled; up to 50 minority rows kept), because a plain 200-row slice of the
   1.6 percent-positive civil-war data has no positives in the early rows and made a valid plan fail with `a cannot be empty` (found while building this; that is why the downsampler is class-aware).
   The unchanged `claimed_eval` is not run, and module-level ensemble knobs (`N_TREES`, `N_ESTIMATORS`, ...) are shrunk to 8 after import: this changes speed, not which code paths run.
3. **Verdict**: `{ok, stage: lint|smoke, kind, message, config, line, code, definitive, elapsed_s, repair_text}`. `repair_text` is ready to append to a repair prompt
   ("PRE-FLIGHT FAILED (smoke) in fix_A at line 45: TypeError: ... offending code: ..."). `definitive=False` marks a failure that a tiny sample can cause by itself (ValueError, IndexError, ...), re-run once on 600 rows;
   the caller may warn instead of block on those. TypeError / AttributeError / NameError / ImportError / KeyError / SyntaxError / timeout are definitive.

**Replay of the recorded G7 r3 patch** (`runs_g7/r3.json`, case `civilwar_disguised`, final plan that was ACCEPTED by the guard and then crashed after minutes): caught in **3.4 to 6.1 s** wall
(limit 30 s; measured twice while a live G8 run used the CPU), `ok=False`, stage `smoke`, `TypeError: to_numpy() got an unexpected keyword argument 'kind'`, config fix_A, line 45,
code `order = np.argsort(df['epoch'].to_numpy(kind='stable'))`. Positive control: the plan the r3 CLEAN case ran with at full size passes smoke in about 5 s. (`tests/test_smoke.py`, 7 tests.)
What the smoke does not do: it does not judge whether a fix is methodologically right (that is the guard), and a green smoke does not guarantee the full run cannot fail (size-dependent failures, timeouts at full size).

## 4. Profile and `agent/cached_exec.py` (task 3)
**Profile first.** One serial case = `sandbox/run_factorial.py`: `orig` + `fix_A` + `fix_B` + `fix_both` per seed, seeds 42/43/44, every one single-threaded (`OMP_NUM_THREADS=1`).
Measured on `civilwar_disguised_clean` with the r3 clean-case plan, seed 42, one process, the G8 live run using other cores (`cProfile` on the first call only, so `orig` carries profiler overhead):

| Step | seconds |
|---|---|
| interpreter + numpy/pandas/sklearn imports (once per process) | 4.1 |
| load `data.csv` (7,140 x 92) | 0.07 |
| `orig` = `claimed_eval`, seed 42 (under cProfile; it is the same function the fixes re-run) | 51.5 |
| `fix_A` | 26.9 |
| `fix_B` | 37.7 |
| `fix_both` | 28.8 |
| one seed, four configs | about 145 |
| three seeds, serial (what a case runs) | **about 6.5 to 7.3 minutes** |

Where it goes: inside `claimed_eval` 97 percent is `tune_mtry` (3 `mtry` values x 10 folds x 300 trees = 9,000 `DecisionTreeClassifier.fit` calls + 300 for the final forest). Of the 51 s, the tree growing itself (`_fit`) is
35 s and sklearn input validation (`check_array`, `validate_data`, `type_of_target`) about 14 s of per-call overhead on 90-row fits. The model call is not the bottleneck (15 to 60 s per reply in `runs_g8/traces.jsonl`).
So the 7 minutes are **serial CPU in the sandbox**, and 1/4 of every case is the `orig` configuration, which does not depend on the model's patch and is recomputed for every case, repair and repeat.

**`agent/cached_exec.py`** wraps `sandbox.executor.run_factorial` (no edit): `run_factorial_cached(case_dir, patches, seeds, timeout)` has the same return shape.
(1) `orig` per seed is cached under sha256(train.py, data.csv, seed, library versions as seen by the sandbox interpreter, `run_factorial.py`, sandbox env). (2) The remaining (config, seed) jobs run in parallel
restricted worker processes (same `-I`, scrubbed env, `PYTHONHASHSEED=0`, `OMP_NUM_THREADS=1`, `_block_network`). (3) If any source uses process-global randomness (`np.random.<fn>`, `random.<fn>`)
it falls back to the unchanged serial executor. `install()` rebinds `executor.run_factorial` in a NEW process only (never the live G8 process).
**Equality.** The result equals the uncached result byte for byte except the wall-clock field `elapsed_s` (compare with `cached_exec.canonical()`); `tests/test_cached_exec.py` checks it on `corpus/clean_wine_correct`
(2 seeds, cold and warm cache, plus identical `factorial_stats.all_seeds` output), crash reporting, cache-key sensitivity, the global-randomness fallback and install/uninstall.
**Speed on the civil-war case** `civilwar_disguised_clean`, r3 clean plan, 4 workers, machine shared with the live G8 run (3 concurrent sandboxes), so absolute times are pessimistic for both modes:
uncached serial executor, 1 seed: **163.6 s** (so 3 seeds about 8 min); cached cold, 1 seed: **61.8 s** (4 jobs in parallel), output identical to the uncached run;
3 seeds with seed 42 cached: 139 s (11 jobs); 3 seeds with `orig` fully cached: **108 s** (9 jobs on 4 workers) against about 8 min serial, about 4.5x, and identical to the cold 3-seed result;
seed 42 equals the uncached seed 42 vector for vector. With 3 cases in flight the 4 workers per case compete for 8 cores, so expect less than the unloaded gain; the target "under 3 min per case" was met here only
for a warm `orig` cache or an idle machine (UNVERIFIED for 3 concurrent cases).

## 5. Tests run (offline)
`tests/test_transport.py` 18 passed; `tests/test_smoke.py` 7 passed; `tests/test_cached_exec.py` 5 passed; with `tests/test_g8.py`, `tests/test_trace.py`, `tests/test_ehg_runner.py` unchanged and passing.

## 6. UNVERIFIED
* Streaming and `stream_options.include_usage` against api.meta.ai (mock only); whether a client-side timeout is billed by the provider.
* The pyflakes branch of `smoke.lint` (pyflakes is not installed).
* Whether the real API's 429/5xx bodies/headers match the mocks (`Retry-After` parsing in seconds only).
* The cache is keyed on library versions and the runner but not on OS/CPU: valid on the same machine and venv only. Bit-identity was tested on this machine, not across machines.
* The smoke check is not a proof that the full run passes; `definitive=False` verdicts are heuristics.
* Using any of this in a live run is a different protocol and needs its own preregistration (G9); none of it was used in G8 or EHG.
