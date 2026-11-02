# EVAL-15 / G9b preregistration: continuation of the 8 G9 units that never produced an outcome

Written Mon Nov 2, 2026, BEFORE any G9b live call (`runs_g9b/live_calls_g9b.jsonl` does not exist). Runner: `agent/factorial_g9b.py` (imports `agent/factorial_g9.py` unmodified). Tests: `tests/test_g9b_runner.py` (28, offline).
G9 (docs/EVAL-13-G9-PREREG.md, `runs_g9/`) was stopped incomplete (`runs_g9/STOPPED.md`): 8 of its 16 units were recorded. This run is a **continuation** of the other 8, not a new experiment and not a re-roll.
It is labelled **G9b**. G7 (failed), G8 (met clauses a to c, harness target missed) and G9 as recorded stay as reported.

## 1. Why this is a continuation and not a re-roll
The 8 missing units are: `civilwar_disguised` (leaky) repeats 1, 2, 3 (started, three threads stuck inside the behavioural guard for about 90 minutes, no outcome, no model call in flight, no spend while stuck) and
`ehg_disguised` repeats 4, 5, `ehg_disguised_clean` repeats 4, 5, `civilwar_disguised_clean` repeat 3 (never started, queued behind the stuck units). **No stalled unit produced an observed outcome.**
(The planner's first reply to the three civil-war leaky units was received and written to the prereg log as `loop_planner` records by G9; the planner then sat in the guard. Those replies are not used: they are model samples whose pipeline never ended, and G9b asks the same prompt again. This is stated, not hidden. The G9 B3 answers for those three units were observed and are NOT asked for again, section 2.)
The cause was the speed of `agent/guard_g9.py` on the 7140-row civil-war pipeline (docs/EVAL-14-GUARD-SPEED.md). The guard was then sped up with **identical decisions**, shown by `tests/test_guard_g9_equivalence.py` (400 random traces, 500 random plan pairs, 7 real cases, all 82 replay plans) and recorded in `docs/FROZEN-CHANGELOG.json`.
Nothing else changed: prompts, contract, DSL, smoke, transport, cached sandbox, statistics, agent views, model, temperature and repeat ids are the G9 ones (checked by `verify` against the G9 freeze records, section 6).

## 2. Protocol (same as EVAL-13 section 2, with these exact differences)
Model `muse-spark-1.3-contributor`, temperature **0.7**, `reasoning_effort` low, same contract, DSL, behavioural guard logic, smoke pre-flight, transport (deadline 420 s, total 1500 s, 2 retries, retries logged apart and not model repairs), cached sandbox, 3 seeds (42/43/44), n_boot 1000, metric as in train.py.
Repeat id sent to the planner is the G9 one, `g9-r<k>`, so each G9b unit is the prompt the stalled G9 unit would have sent.
**Units (exactly 8):** `civilwar_disguised` (leaky) r1, r2, r3; `ehg_disguised` r4, r5; `ehg_disguised_clean` r4, r5; `civilwar_disguised_clean` r3. `run` refuses any unit that already has a loop record in `runs_g9/`, and `verify` fails if `runs_g9/` does not hold exactly the 8 other units. `runs_g9/` is only ever READ (to refuse recorded units, to cross-check the freeze records, to build the union in `score`); nothing is written there.
Differences from G9, all listed:
1. **Own directory** `runs_g9b/`: call log `live_calls_g9b.jsonl` (+ `.usage.jsonl`, `.transport.jsonl`), `traces.jsonl`, `prereg_log.jsonl`, `r<k>.json`, `score.json`. `configure()` refuses any path under `runs_g9`, `runs_g8`, `runs_ehg`, `runs_g7`.
2. **Caps:** at most **40 planner-side calls** for the whole run (8 units x 5), all attempts at most **48** (`llm.MAX_G8_CALLS`, counted on the own log before the request, B3 included). Ceiling **USD 4.00**, enforced (a) by projection: a unit starts only if est spent + the reserved worst case of units in flight + its own worst case + a retry margin (USD 0.24) fits under the ceiling, otherwise it is left unstarted (NOT recorded, not a failure, run `run` again later); (b) by the per-call check in `g9.Budget9.call` (harness failure `budget` when spent + one estimate would pass the ceiling); (c) by the `bs.py` spend gate on every call and before every transport retry.
3. **B3 (reading-only comparator):** one call per unit, except where `runs_g9/` already holds a usable B3 answer for that exact (repeat, case). That is the case for the three civil-war leaky units: their G9 B3 answers were observed, so a second sample would be a re-roll of a comparator. For those units `score` uses the G9 B3 answer and says so (`b3_from`). B3 is not an acceptance clause. B3 calls: 5.
4. **No forgetting of transport failures.** G9 allowed an exhausted transport (no reply ever observed) to be re-run at the next `run`. G9b does not: **any harness failure in G9b, an exhausted transport included, is recorded and not re-rolled**; it stays in the denominator. (A transport timeout inside the retry budget is retried and is not a failure; tested.)
5. Three units run concurrently, as in G9.

**Projected spend** (`python -m agent.factorial_g9b project`, estimates not billing): floor USD **1.36** (5 B3 + 8 plans, no repairs); one repair per unit USD 2.32; two repairs per unit 3.28; all-repairs worst case USD **5.20** (every unit uses all 5 planner calls), which is above the USD 4.00 ceiling, hence the per-unit admission rule; 13 to 45 calls (planner-side at most 40). Real tokens are logged next to the estimates (`usage`).

## 3. Acceptance clauses (EXACTLY those of EVAL-13 section 3, on the UNION of 16 units)
Evaluated on the union of the 8 recorded G9 units and the 8 G9b units, by `score` (it calls `g9.score_cases` on the union):
* **EHG** (5 + 5), PASS iff all of: (a) direction right (sign `+`) on the leaky case in **>= 4 of 5**; (b) **0 of 5** clean false alarms (sign `+`); (c) measured inflation within **0.15 of +0.43** (|mean - 0.43| <= 0.15) in **>= 3 of 5** leaky repeats. Published range +0.36 to +0.49 shown alongside. Harness-INCONCLUSIVE counts in the denominator (5 per case) as not met on (a) and (c), never as a false alarm and never as a no-effect.
* **Civil-war regression** (3 + 3), not worse than G8: direction right **>= 2 of 3**, **0 of 3** clean false alarms, both repeat sets complete. Magnitude (reference +0.36, tolerance 0.15) is reported, not a clause.
* Harness target (reported, not a clause): **0** harness-INCONCLUSIVE over all **16** units; also reported: guard harness failures, first-plan guard rejections, transport retries, calls and repairs, CIs, B3 gets-it and B3 clean false alarms.
`score` writes `runs_g9b/score.json` with the union result, the G9 units and the G9b units separately (`by_source`, `per_unit`) and sets **`complete: true` only when all 16 units exist** (a harness-INCONCLUSIVE record counts as existing; a missing unit does not). With fewer than 16 units the clause results read `NOT EVALUABLE`, never PASS or FAIL.

## 4. Guard-version labels (kept visible on every unit)
| Units | Produced by | `guard_g9.py` sha256 (LF) |
|---|---|---|
| the 8 recorded G9 units (`ehg_disguised` r1-3, `ehg_disguised_clean` r1-3, `civilwar_disguised_clean` r1-2), ran 2026-11-02 15:28-15:58 SLT (09:58-10:28 UTC) | the guard as it was when G9 ran, **before the speed fix** | `4a084a1c466b1e8ff53ce3da94307796dc7475c275e0fdb889888f182fa17dba` |
| the 8 G9b units | the **speed-fixed** guard | `983d2ffe81725ae2ed4703a287b74800270034af712185e2331218e18dce79b8` |
Decisions are identical per docs/EVAL-14-GUARD-SPEED.md (the one allowed difference: the `ctx` facts may list an extra component, because the old worker keyed objects by `id()` and could merge two estimators; no decision depends on it in the 82-plan replay or the real-case tests), so the union is valid. The label stays visible: `score.json` repeats the guard hash and the run window on every unit.

## 5. Stated plainly, before data
* **EHG is NOT held out for the DSL.** The DSL ops were informed by failures already seen (EVAL-12-G9-DSL section 2). A pass shows the instrument no longer blocks the known-correct fix and the model can express it; it does not show the DSL generalises.
* **G7 failed** its preregistered acceptance; **G8** met clauses a to c (civil-war pair, direction 4/5, 0/5 false alarms) with harness target missed (1/10). The **rules baseline on EHG fires nothing** (inflation 0.000, direction right 0/1, 0 false alarms; EVAL-11 section 5).
* **Reading-only (B3) matched the loop on EHG in the 3 recorded G9 repeats** (leak found with a predicted size inside 0.15 of +0.43 on the leaky case in 3/3, no clean false alarm in 3/3). The loop's added value over reading alone is therefore not established by EHG; the extra evidence the loop gives is the measured size on real data. On the civil-war clean case B3 raised a false alarm in both recorded G9 repeats; the loop did not (no flaw reported in both).
* **Counts, not rates.** 5 and 3 per arm; one harness failure fails a clause by itself only through the denominator.
* **Stalled units had no observed outcome**; the 8 recorded G9 units stay as recorded (EHG leaky r1-3 inflation found, mean +0.424 each; EHG clean r1-3 and civil-war clean r1-2 no flaw reported) and are scored as they stand.
* **Any harness failure in G9b is recorded and not re-rolled.** A unit left unstarted by the admission rule is not a failure and may be run later; the run is not complete until all 16 units exist.
* This is not a new Meta-score claim and not a discovery claim; it completes the G9 measurement of the instrument claim in EVAL-13 section 1.

## 6. Hashes, freeze and verification (sha256 after CRLF to LF normalisation)
Rule: files `sha256(open(f,'rb').read().replace(b'\r\n', b'\n'))`; text `sha256(s.replace('\r\n','\n').encode('utf-8'))`; JSON payload `sha256(json.dumps(payload, sort_keys=True))`.
`freeze` writes values and full payloads to `runs_g9b/prereg_log.jsonl` (kinds `g9b_source_hashes`, `g9b_prompts`, `g9b_rules`, `g9b_agent_view_frozen` x4, `g9b_prereg_doc`); `verify` recomputes everything from disk and compares with the last record of each kind, and also checks (read-only, against `runs_g9/prereg_log.jsonl`):
(i) the four agent views (file hashes, view text, planner user message) equal the G9 freeze records; (ii) the prompt hashes equal the G9 record; (iii) every code file equals its G9 record, except `agent/guard_g9.py`, whose change must be in `docs/FROZEN-CHANGELOG.json` with exactly the old and the new hash above, and `guard_g9.py` on disk must be `983d2ffe...`; (iv) `runs_g9/` holds exactly the 8 expected units and none of the 8 G9b units; (v) op-spec `420a97b1...` and contract `2e682922...` equal EVAL-12. `run` refuses unless `verify` passes. Any later edit invalidates this preregistration and the run must be relabelled.

| File | sha256 (LF) |
|---|---|
| agent/factorial_g9b.py | `4b6583c38dbe7e3e74cdff46d83789c2d79ac5a2eaadd48add9054447ce2ceee` |
| agent/factorial_g9.py | `c04a9ec522ca27652568a2ff974a8f06b925c54bc37c2daf89d7a7e1e5a49b4e` |
| agent/transport.py | `ddee7ac6af710640f19299af7df3ff0115aeef364d715bc70e3e8a4295c1aefa` |
| agent/smoke.py | `520c93d9b0c5e67c05e878628ce009b3d922b8190a18a6000f6d82a3161319e4` |
| agent/cached_exec.py | `5b5e82a45b3815bc57c88b1b0d579e147267e45426843aab98c795798375eef8` |
| agent/edit_dsl.py | `8964d560ce7a76acacb4828ef6db5ed198fa858fd34937daf46c72704239b1e5` |
| agent/guard_g9.py (speed-fixed) | `983d2ffe81725ae2ed4703a287b74800270034af712185e2331218e18dce79b8` |
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

Prompts (identical to the G9 freeze): planner system (contract included) `c678d32a64063bcb537df06a18609e438883300fb45c56487876d805f383a785`; B3 system `33829510dbda134a32ad8022484b3c8d25da64fc830c6f195708fff3399efb79`; contract `2e68292243af1d4ebab3fed2fd75ee494f7b5ec8fa33acef2a363ddfd7ac0284`; op spec `420a97b129734bc690153ff2122592c82eb4f1acf851eeac8aef94fa2834a320`; bundle `f8cad87e2418c75231e2c3fa044f8cb1487ffa17397604045ab44d0f0ae1b1c6`.
Rules payload (units, G9-recorded units, caps, estimates, ceiling, admission and B3 and no-reroll rules, references, tolerance, acceptance, union denominators, transport and smoke settings, both guard hashes): `23736b2ecff3f0a5d6f7d587f6f490cd0b65f873d66d76f4d89bd5bb72f19d43`.

| Agent view | agent_view text | planner user msg (rid "RID") |
|---|---|---|
| ehg_disguised | `a5475d962e2694b4b47e945639a761f99e4e992a14651e653cb07a81a12404bd` | `f268e588c36aa184c17f11b05badb7ceb77c99edab9f6493f836f0192c7261bf` |
| ehg_disguised_clean | `bdc16bf4406b0f1baa823c77be1665b851ec6091d45610f27eb8644aeafb1edb` | `67dce15923adc261150ec68b5d701c1b12d6a6ccbfd327156996894162aade70` |
| civilwar_disguised | `38f96bd7a996c278980f8fe33072761d04c6f1b943cbbd42e2a130eaf89ac56e` | `0b86dea7605c6ccbe36eca46da3e5815f0e6a5a7ee725d913b18806b555a33c2` |
| civilwar_disguised_clean | `7c43338c248832cb46d61c3d1f03e6850bfd64fccc9ed873d6969bfaca9aca93` | `7650933aff9f0279961c50511b41827258f7ffa924bdeb2f823f95f0ae57f143` |

These equal the values frozen for G9 (EVAL-13 lists the prefixes `a5475d96...`, `bdc16bf4...`, `38f96bd7...`, `7c43338c...`). This document's own LF sha256 is logged by `freeze` (kind `g9b_prereg_doc`) and checked by `verify`.

## 7. Commands
```
.venv/Scripts/python.exe -m agent.factorial_g9b project
.venv/Scripts/python.exe -m agent.factorial_g9b freeze
.venv/Scripts/python.exe -m agent.factorial_g9b verify          # must print VERIFY OK
.venv/Scripts/python.exe -m agent.factorial_g9b run             # LIVE (lead only), est. USD 1.36 to 5.20, ceiling 4.00; `run 4 5` restricts to repeats 4 and 5
.venv/Scripts/python.exe -m agent.factorial_g9b score           # union, runs_g9b/score.json
.venv/Scripts/python.exe -m agent.factorial_g9b usage
```

## 8. UNVERIFIED
That the speed-fixed guard reaches the same decisions on the 7140-row civil-war pipeline with a real model plan (compared with the original guard on a real plan only at 10/20/40 trees; the original never finished at full size, so full-size equivalence rests on the proof tests and on the identical results at smaller sizes, EVAL-14); the running time of a full civil-war unit under the fixed guard with three concurrent units; whether the three previously stalled civil-war plans, asked again, are accepted by the guard; whether a timed-out request is billed; real per-call cost (estimates only); `pyflakes` branch of smoke lint; cache validity across machines; whether Spark chooses the DSL ops or sizes the effect (the live question); the exact G9 B3 reuse choice (a design decision of this preregistration, not a result).
