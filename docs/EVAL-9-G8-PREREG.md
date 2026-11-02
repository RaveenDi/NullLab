# EVAL-9 / G8 preregistration: hardened loop, re-run of the disguised pair

Written Mon Nov 2, 2026, BEFORE any G8 live call. No G8 run has been made. This is a NEW, separately labelled run after a FAILED G7.

## Status of G7 (unchanged)
G7 (docs/EVAL-7.md) **FAILED its preregistered acceptance** (direction 3/5, clean false alarms 0/5, magnitude 3/5). It stays reported as failed.
Its results are never re-scored, re-counted or merged with G8. Two of its five leaky repeats were harness failures, not model verdicts
(r3: the accepted retry plan crashed in the sandbox, `to_numpy(kind=...)` TypeError; r4: the retry reply was not parseable JSON).
G8 changes the harness to handle those two failure classes. It does not change the question, the cases, the rules or the pass numbers,
and a G8 pass would not turn G7 into a pass.

## What changed (harness only)
Code: `agent/factorial_g8.py` (extends `agent/factorial_g7.py`, which is not edited), `agent/llm.py` (adds `live_complete_ex`, a G8 phase and an
optional `response_format`; `live_complete` unchanged for callers), `eval/regress.py`.
1. **Three separate repair budgets, one retry each:** `guard` (static guard / SPLIT-USE-REQUIRED / runtime fidelity rejection; rejection text fed back),
   `crash` (sandbox crash or timeout; the last 25 lines / 2000 chars of stderr fed back), `bad_json` (reply not parseable or schema-invalid; the bad
   reply and the parse error fed back; applies to any reply, including a guard or crash retry reply).
2. **Hard cap per case:** at most 1 plan call + 3 repair calls = **4 planner-side live calls** (plus 1 B3 call per case). Enforced before every call.
   Interpretation note: "max 3 live calls per case" was read as 3 repair calls on top of the plan call. If the owner meant 3 in total, set
   `CASE_CALL_CAP = 3` before the freeze (this document and the hashes below would then change).
3. **Honest labels.** A case ends as one of: `inflation found (interval above 0)`, `no effect (interval spans 0)`, `reverse effect`,
   `mixed across seeds`, or `INCONCLUSIVE (harness failure: crash|bad_json|guard|call_cap|budget|api_error)`. A second failure of a kind whose
   budget is spent ends the case with that harness label. A harness failure is **never** a model verdict, **never** a "no effect" and **never** a
   false alarm. It stays in the denominator (5 per case) and is listed with its reason in `score.json`.
4. **Spend control:** a projected-spend line is printed before the run (floor USD 1.80 with no repairs, worst case USD 4.80, 10 cases, ceiling
   USD 5.00 via `NULLLAB_G8_CEILING`); the run refuses to start if spent + worst case passes the ceiling. Own phase log
   `runs_g8/live_calls_g8.jsonl` with its own cap (70 calls, `MAX_G8_CALLS`), traces in `runs_g8/traces.jsonl`. Real `usage` tokens are logged
   next to the estimate (`live_calls_g8.usage.jsonl`, per-call `calls` in each case record, `usage` stage). These are estimates, not billing.
5. **JSON:** prompt-based JSON is kept. Native `response_format` `json_schema` is documented for `muse-spark-1.3` at dev.meta.ai/docs/structured-output
   (checked Nov 2, 2026), but it has **not been tested live** by us, and it is not tested on `muse-spark-1.3-contributor`: **UNVERIFIED, off**
   (`USE_NATIVE_SCHEMA = False`). Turning it on would be a different protocol.

## Protocol (identical to G7 except the harness above)
- Cases: `real/civilwar_disguised` (leaky) and `real/civilwar_disguised_clean`, the same v2 disguise as G7 (agent-view hashes below).
- Model: `muse-spark-1.3-contributor` for every call, temperature **0.7**, 5 repeats per case (r1..r5), reasoning_effort low (as `llm.py`).
- Per repeat and case: B3 (single reading prompt, unchanged text) then the loop: planner (unchanged G6 prompt; SPLIT-USE-REQUIRED not announced),
  guards unchanged (static fidelity, FEATURES-REASON, SPLIT-USE, SAMPLE SIZE, SPLIT-USE-REQUIRED), sandbox 4 configs x seeds 42/43/44,
  n_boot 1000, unpaired bootstrap, PR-AUC; repeat sign from the 95 percent CI, category shared by at least 2 of 3 seeds.
- A recorded harness failure is **not re-rolled**: no repeat is re-run to replace a failure.

## Acceptance (clauses IDENTICAL to G7)
PASS iff all of:
 (a) direction right (sign `+`) on the leaky case in >= 4 of 5 repeats,
 (b) 0 false alarms (sign `+`) on the clean case over 5 repeats,
 (c) mean inflation within 0.15 of +0.36 (|mean - 0.36| <= 0.15) on >= 3 of 5 leaky repeats.
Harness target, reported next to (not part of) PASS: **harness-INCONCLUSIVE 0/10**. If it is not 0/10 the result is reported with the failed
repeats listed; PASS or FAIL on (a) to (c) is computed with those repeats counted as not-met (a harness failure is not direction-right, not
magnitude-ok, and not a false alarm).
Reported alongside: B3 gets-it and false alarms, calls and repairs per case, INCONCLUSIVE counts, CIs, estimated spend and real tokens.
Hypotheses are those of G7: H1 (loop approaches builder reference ~ +0.30), H2 (no false alarm on the clean pipeline), H3 (B3 may match the loop).
Known context: the G7 loop measured +0.308 on every executed leaky repeat, 0.052 under +0.36.

## Pre-run checks (offline, no API; done)
- `eval/regress.py`: guard replayed on 63 stored first/second verdicts in runs_g5, runs_g6, runs_g7: **0 unexplained flips** under each generation's
  own rules. 2 explained flips (G5 r1 crop and clean_control: stored REJECT, now ACCEPT, because `agent/fidelity.py` was relaxed in G6 so that a verbatim
  inline of feats' comprehension is not a FEATURES change; the false rejection is documented in EVAL-5). Under TODAY's rules 11 more verdicts flip,
  all because of a rule added later (justification on G5 clean plans; SPLIT-USE-REQUIRED on the 3 G6 `civilwar_apparent` plans, the same 3 as `replay_g6.json`).
  Full list: `runs_g8/regress.json`.
- The two G7 failures replayed through the G8 repair path, labelled **replay, not a result**: model replies for the repair calls are mocks and the
  sandbox is stubbed; they show the state machine, the budgets (3 planner-side calls each), that stderr / the bad reply is fed back, and that the
  repaired r3 split function runs on the real data (5,712 train rows, 1,428 later test rows). They are not evidence that the real model repairs correctly.
- Tests: `tests/test_g8.py`, `tests/test_regress.py` (plus `tests/test_trace.py`, `tests/test_g7.py` unchanged and passing).

## Frozen sha256 (frozen Nov 2, 2026; also logged in `runs_g8/prereg_log.jsonl`)
Any later edit to these files invalidates this preregistration and the run must be relabelled.
| File | sha256 |
|---|---|
| agent/factorial_g8.py | `b0cdaa70952244c91ddbba6673620f7baa2ece6c19bc27934f46ee897f5a9a1d` |
| agent/factorial_g7.py | `8910b64b92497d4df04c4943be75f5f13e97076ef2cecce7caf476920ca71eee` |
| agent/llm.py | `35c0db9c52a0ea02c4292faee27bf10c70939d507f71b0203fc66802080dfe25` |
| agent/fidelity.py | `e4efb27a232247413e7e1966b88107ddb5c9d4466a5828b99c6bc88b25dba5a1` |
| agent/factorial_g5.py | `b681cdb1e0372a52819ce02d925ebb45618b86a279d486002afef94782e627f8` |
| agent/factorial_g6.py | `83abdfb3b2cbee64b4d90595f7c60e8cc3fd94a661b1ba822d4978d286dd2f8d` |
| eval/build_g7.py | `5acff1a45356e2a7d839d0b9b6f86ca45aaba78b5703a94255cb58459ea2486a` |
| eval/g7_truth.json | `d4a363118581da17283be62e2b0aff6e57bcb60d19ffbdea5ad9f937e05eec56` |
| sandbox/factorial_stats.py | `cc95a68df58d58b601182f145b189a7fd753a1320f565ce1405d054b9bcb960d` |
| sandbox/run_factorial.py | `68fdaf3ddf0e9600df4a3e3e3a9d6496e64010310bd3581182f45bdee0971f4f` |
| sandbox/executor.py | `3edf9ecc1db0a61129a2d02290ed337f71df7c6cea8cbb72bc1cbccddf8159dd` |
| eval/regress.py | `a1f8075722fd3fb941b77bf6add0de246eb2014877d9894216fa6ccaa63bece0` |
Rules/prompts: planner + B3 prompt bundle `40dc30fee676823fd090bea16586731a136f033b0ac845f8946ce32073d04bf9`; rules bundle (forecast words, repair kinds,
cap, temperature, repeats) `1d0c400e0c17fed26b993105b5ed9cf826384118e43b197de410f6be8bb019e8`; code bundle `6f7a3b22a3f3c75400b4bd7c7c444378ee2c2a5f18bffe477e90030d3e8885f6`
(bundle hashes are of the JSON in `prereg_log.jsonl`). Agent views: civilwar_disguised `fb303afe8a321164a3fefe0dbe043bb4c30ebf4d7ea8e24e878c3a06558c97ce`,
civilwar_disguised_clean `26576bf436356292bfeef8729cc9d8d9347199c3bc2c056e47ae55706dc88e29`.
(This document itself is not part of the frozen set; its sha256 is not self-referential.)

## How to run (after the owner's spend gate; NOT run now)
```
.venv/Scripts/python.exe -m agent.factorial_g8 project
.venv/Scripts/python.exe -m agent.factorial_g8 run 1 2 3 4 5
.venv/Scripts/python.exe -m agent.factorial_g8 score
```
