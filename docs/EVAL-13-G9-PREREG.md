# EVAL-13 / G9 preregistration: the fixed instrument on the disguised EHG pair (plus a civil-war regression check)

Written Mon Nov 2, 2026, BEFORE any G9 live call. No live call has been made (`runs_g9/live_calls_g9.jsonl` does not exist). Runner: `agent/factorial_g9.py`.
Tests: `tests/test_g9_runner.py` (29, offline). G7 (failed), G8 (passed clauses a to c, harness target missed) and EHG (G8 harness, not run live) stay as reported; G9 is a NEW, separately labelled run.

## 1. What is claimed, and what is not
Claim under test: **the fixed instrument removes harness failures and the guard false reject.** Instrument = typed edit DSL (`edit_dsl`) with the full contract shown to the planner up front
(`contract_g9`), behavioural guard (`guard_g9`), transport with deadlines and retries (`transport`), smoke pre-flight (`smoke`), cached parallel sandbox (`cached_exec`).
This is **not** a new Meta-score claim and **not** a discovery claim.

Stated plainly, before data:
* **EHG is NOT held out for the DSL.** The ops were informed by failures already seen (EVAL-12-G9-DSL section 2: `move_into_fold`, `replace_split`, and `drop_from_eval` with the EHG fix in view). A pass on EHG shows the instrument no longer blocks the known-correct fix and the model can express it; it is not evidence the DSL generalises.
* **The contract is announced to the planner.** SPLIT-USE-REQUIRED, which G8 taught only by rejection text, is now rule R-USE-REQUIRED shown up front. The civil-war pair therefore no longer tests whether the model finds the temporal split on its own; the earlier caveat ("the guard plus the model reproduce the published control") still applies, now with the rule disclosed in the prompt. EHG has no forecasting claim, so the rule is inert there.
* The civil-war pair is a same-instrument **regression check**, compared with G8, not a new test.
* Truth is read only by `score`. A test asserts that no truth number or source name appears in any agent view or prompt.
* A `no_flaw` verdict is a legal planner answer (nothing is run). On a leaky case it counts as direction not right; on a clean case as no false alarm.
* Comparators reported next to the result: G7 FAILED (docs/EVAL-7.md); G8 civil-war pair 4/5 direction, 0/5 clean false alarms, 4/5 magnitude, harness 1/10 (docs/EVAL-9-G8-RESULT.md); EHG offline rule baseline: no rule fires on either case, inflation 0.000, direction 0/1, 0 false alarms (docs/EVAL-11-EHG-PREREG.md section 5).

## 2. Protocol
Model `muse-spark-1.3-contributor`, temperature **0.7**, `reasoning_effort` low (as `llm.py`). Cases: `real/ehg_disguised` (leaky) and `real/ehg_disguised_clean`, **5 repeats** each (r1..r5);
`real/civilwar_disguised` and `real/civilwar_disguised_clean`, **3 repeats** each (r1..r3). 16 cases. `run r1..r5` does repeat k for every case with k <= its repeat count.
Per case: one B3 call (unchanged `g7.B3_SYSTEM`, same agent view) then the pipeline: plan -> JSON parse -> `check_plan(runtime=True)` (static contract, compile, behavioural guard)
-> smoke on a 200-row copy -> cached sandbox (orig + 3 configs x seeds 42/43/44) -> unpaired bootstrap, n_boot 1000, metric as in train.py (`g4.case_sign`), exactly the G8 statistics.
Repairs, one of each kind per case, so at most **5 planner-side calls per case**: `bad_json` (unparseable reply), `guard` (contract or behavioural rejection, reasons fed back), `smoke` (definitive smoke failure, its repair text fed back), `crash` (sandbox crash, stderr tail fed back).
A repair whose budget is spent ends the case as `INCONCLUSIVE (harness failure: <kind>)`. A non-definitive smoke failure (size-sensitive error on 200 rows) is logged and does not block.
The planner has no tool loop: the contract says check_plan is called by the harness. One factor (k=1) is measured as one fix; the frozen 3-config sandbox receives the same source three times (plumbing, not a factorial); k=3 is measured on `fix_all` only. Only `fix_both`/`fix_all` is scored.
**Transport.** `transport.install()` runs in the driver process: per-attempt hard deadline 420 s, total 1500 s, 2 retries (backoff 4 s, 12 s) on timeout, connection error, truncated body, 429/5xx; retries are logged apart (`live_calls_g9.transport.jsonl`) and are not model repairs.
Rationale: a call for which no reply was received yields no sample, so re-asking draws the first observed sample; a reply that was received is never re-rolled. Only an exhausted transport files `api_error`; at the next `run` such a case (no reply ever observed) is dropped from its `r<k>.json` and re-run, and that is logged in `prereg_log.jsonl` (`g9_transport_failure_forgotten`). Every other recorded harness failure is not re-rolled.
**Caps and spend.** Planner-side calls at most 90 (counted on our own log) and all calls at most 106 (`llm.MAX_G8_CALLS`), attempts counted before the request; own log `runs_g9/live_calls_g9.jsonl`, traces `traces.jsonl`.
The `bs.py` spend gate runs on every call and before every transport retry. Estimates: B3 0.08, plan/repair 0.12 USD per call. Ceiling **USD 12.00**: the run stops if spent + worst case passes it, and every call is refused when logged estimates plus one estimate per transport retry record plus the next call pass it.
**Projected spend** (`python -m agent.factorial_g9 project`): floor USD 3.20 (16 B3 + 16 plans, no repairs); worst case USD 10.88 (every case uses all 5 planner calls); 16 to 96 calls. Estimates, not billing; real tokens are logged next to them (`usage`).

## 3. Acceptance (computed by `score`; fixed here)
**EHG** (5 + 5): PASS iff all of (a) direction right (sign `+`) on the leaky case in **>= 4 of 5**; (b) **0** clean false alarms (sign `+`) in 5; (c) measured inflation within **0.15 of +0.43** (|mean - 0.43| <= 0.15) in **>= 3 of 5** leaky repeats.
Reference +0.430 is the offline measurement of this port (EVAL-11 section 3); the published range **+0.36 (SVM) to +0.49 (RF)** is shown alongside (`within_published_range`). Harness-INCONCLUSIVE counts in the denominator (5 per case) as not met on (a) and (c), never as a false alarm or a no-effect.
**Civil-war regression** (3 + 3): not worse than G8: direction right **>= 2 of 3**, **0 of 3** clean false alarms; both repeat sets must be complete. Magnitude (reference +0.36, tolerance 0.15) is reported, not a clause.
**Harness target** (not a pass clause, like G8): **0** harness-INCONCLUSIVE over all **16** cases. (The brief said 0/20; the specified cases total 16, so the denominator here is 16.) Also reported: harness failures by kind, guard harness failures, how many first plans the guard rejected, transport retries per case, calls and repairs, CIs, B3 gets-it (leak true, predicted fix_both >= 2 pp, within 0.15 of the reference) and B3 clean false alarms.
The instrument claim is supported only if the harness target is met AND no EHG case ends as a guard harness failure; a pass on the clauses with harness failures present is reported as such.

## 4. Known risks stated before data
* A guard that rejects the model's formulation twice ends a case as `harness failure: guard`; on a clean case an invented fix rejected twice is also filed that way (conservative accounting).
* The DSL cannot say feature edits, duplicates, or contiguous-fold splits (EVAL-12-G9-DSL section 8). The civil-war temporal inner-CV strictness (strict `<`) may reject legitimate plans (documented there, files frozen).
* One-flaw cases get one factor: no factorial attribution, only the sign and size of the total fix are scored.
* n = 5 and 3 per arm: counts, not rates; one harness failure fails nothing by itself but is listed.
* Offline engineering dry run (no model, a hand-written correct EHG plan through the real guard, smoke and cached sandbox, scratch directory): completed, measured +0.416, +0.445, +0.412 over seeds 42/43/44 in 95 s. This checks plumbing only; no model reply was involved.
* Contamination: not re-probed; EVAL-10 found no source recall, which shows only that the model did not name it.

## 5. Hashes (sha256 after CRLF to LF normalisation)
Rule: files `sha256(open(f,'rb').read().replace(b'\r\n', b'\n'))`; text `sha256(s.replace('\r\n','\n').encode('utf-8'))`; JSON payload `sha256(json.dumps(payload, sort_keys=True))`.
`freeze` writes values and payloads to `runs_g9/prereg_log.jsonl`; `verify` recomputes them from disk (and checks the op-spec hash `420a97b1...` and contract hash `2e682922...` against EVAL-12); `run` refuses unless `verify` passes. Any later edit invalidates this preregistration and the run must be relabelled.

| File | sha256 (LF) |
|---|---|
| agent/factorial_g9.py | `c04a9ec522ca27652568a2ff974a8f06b925c54bc37c2daf89d7a7e1e5a49b4e` |
| agent/transport.py | `ddee7ac6af710640f19299af7df3ff0115aeef364d715bc70e3e8a4295c1aefa` |
| agent/smoke.py | `520c93d9b0c5e67c05e878628ce009b3d922b8190a18a6000f6d82a3161319e4` |
| agent/cached_exec.py | `5b5e82a45b3815bc57c88b1b0d579e147267e45426843aab98c795798375eef8` |
| agent/edit_dsl.py | `8964d560ce7a76acacb4828ef6db5ed198fa858fd34937daf46c72704239b1e5` |
| agent/guard_g9.py | `4a084a1c466b1e8ff53ce3da94307796dc7475c275e0fdb889888f182fa17dba` |
| agent/contract_g9.py | `99c3117dc9b592810d02489a30e9952969bc05092ae18b6430928339db91b011` |
| agent/llm.py | `230a54e8c1120c29b6a0531d0755d29918c33c47ff85d70b8b37432255afc8ab` |
| agent/factorial_g8.py | `0cf32783d3d7ef2cf8519cfa956197666d1b690ac2552ea5170858df260ed73c` |
| agent/factorial_g7.py | `dc17c381206872400fa14a99a3bd9ffb02240f370ac792189c5e7a30723290ce` |
| agent/factorial_g5.py | `b681cdb1e0372a52819ce02d925ebb45618b86a279d486002afef94782e627f8` |
| agent/factorial_g6.py | `83abdfb3b2cbee64b4d90595f7c60e8cc3fd94a661b1ba822d4978d286dd2f8d` |
| agent/factorial.py | `68d326f1bfd55a118efa402fcf60c47506a6c3ae499b5c2685e162aee7658ae3` |
| agent/fidelity.py | `9cde95bddadfb665ff30c33c020a5e9196d7dfec9163025978e025a2cb77e44a` |
| g4.py | `f6e9765cfd8ff6d59e20df9a1776da31b0794aa2c7b5dbb22ea236e32573d53a` |
| sandbox/executor.py | `3edf9ecc1db0a61129a2d02290ed337f71df7c6cea8cbb72bc1cbccddf8159dd` |
| sandbox/run.py | `3628a795cee96b1d4d7b5691f002980986465a8b0e9430e6793033d4a6149ad8` |
| sandbox/run_factorial.py | `0eb2130abbea85e38420d353eec4c99368e99d9ea5953b9a04c91d92d0e819cb` |
| sandbox/factorial_stats.py | `fcc8223659535bad0581ebd5eeb9bc2eb8b10f10e98c42137fb39f2d55a82495` |
| eval/build_g8_cases.py | `437332f18df7a27ae5d05ee277cf4af09393df995034f788cfd188e4257c55d8` |
| eval/g8_truth.json | `4875bf5386f4c32f8fac2d6088f99f3544a4067e2cfd3dedea01aec070117a4d` |
| baselines/rulefix.py | `5b9c687586e9d995ba80fd3f8c5d1668d2bff6ae10d8e555b0b2a685f31f537e` |

Prompts: planner system (contract included) `c678d32a64063bcb537df06a18609e438883300fb45c56487876d805f383a785`; B3 system `33829510dbda134a32ad8022484b3c8d25da64fc830c6f195708fff3399efb79`;
contract `2e68292243af1d4ebab3fed2fd75ee494f7b5ec8fa33acef2a363ddfd7ac0284`; op spec `420a97b129734bc690153ff2122592c82eb4f1acf851eeac8aef94fa2834a320`; bundle `f8cad87e2418c75231e2c3fa044f8cb1487ffa17397604045ab44d0f0ae1b1c6`.
Rules payload (repeats, caps, estimates, ceiling, references, tolerance, acceptance, transport and smoke settings) `e8a773b90974f1b57dd7cc3216493b00c3e5d512d876d0799837f436f52b45e1`.

| Agent view | agent_view text | planner user msg (rid "RID") |
|---|---|---|
| ehg_disguised | `a5475d96...` | `f268e588...` |
| ehg_disguised_clean | `bdc16bf4...` | `67dce159...` |
| civilwar_disguised | `38f96bd7...` | `0b86dea7...` |
| civilwar_disguised_clean | `7c43338c...` | `7650933a...` |

The EHG view hashes equal those frozen in EVAL-11 (same cases). This document's own LF sha256 is logged by `freeze` (kind `g9_prereg_doc`) and checked by `verify`.

## 6. Commands
```
.venv/Scripts/python.exe -m agent.factorial_g9 project
.venv/Scripts/python.exe -m agent.factorial_g9 verify               # must print VERIFY OK
.venv/Scripts/python.exe -m agent.factorial_g9 run 1 2 3 4 5        # LIVE (owner only), est. USD 3.20 to 10.88
.venv/Scripts/python.exe -m agent.factorial_g9 score
.venv/Scripts/python.exe -m agent.factorial_g9 usage
```

## 7. UNVERIFIED
Streaming (off); whether a timed-out request is billed; real per-call cost (estimates only); `pyflakes` branch of smoke lint; cache validity across machines; 3 concurrent cases on the sandbox CPU (time); whether Spark chooses the DSL ops or sizes the effect (the live question); op taxonomy names from memory (EVAL-12); the 0/20 versus 0/16 denominator in the brief.
