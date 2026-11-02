# EVAL-12 / G9: typed edit DSL + behavioural guard, OFFLINE engineering validation

Written Mon Nov 2, 2026, 13:10 SLT (02:40 ET, EST after US DST ended Nov 1; 07:40 UTC), BEFORE the replay validation was run.
**This is an ENGINEERING result about the harness. It is not a Meta-score claim, not a live G9 run, and not evidence about the model.**
No model call was made, nothing was spent. G7, G8 and EHG stay exactly as reported and frozen. G8 was running while this was built; its files were only read
(`runs_g8/` is not edited, `agent/llm.py`, `factorial_g7.py`, `factorial_g8.py`, `fidelity.py`, `sandbox/*` are not edited).
Code: `agent/edit_dsl.py` (ops, AST templates), `agent/contract_g9.py` (rule text for the planner, `check_plan`), `agent/guard_g9.py` (runtime guard),
`eval/validate_dsl_replay.py` (replay), tests `tests/test_dsl.py`, `tests/test_guard_g9.py`. Outputs: `runs_g9_offline/`.

## 1. What problem this answers (from the round-4 forensics, architect and skeptic notes)
1. The planner's unit of action was a free-written Python def. The guard then reverse-engineered intent from call names, so a correct fix could be rejected
   (EVAL-11 section 6: removing oversampling drops `NearestNeighbors`, which reads as "MODEL changed") and a wrong one could be accepted.
2. The rules were "taught only by the rejection text" (SPLIT-USE-REQUIRED), turning a deterministic rule into a stochastic retry with a budget of one.
3. A forced 2x2 layout made the model invent a second factor on one-flaw cases.
New: the planner names OPS (no code); the harness compiles them with AST templates; the rule spec is shown up front and available as a tool (`check_plan`);
the guard checks BEHAVIOUR (which rows are fit and which are scored) instead of constructor names; plans carry 1..3 factors.

## 2. FROZEN op list
FROZEN_OPSPEC_SHA256: `420a97b129734bc690153ff2122592c82eb4f1acf851eeac8aef94fa2834a320`
(sha256 of `json.dumps(OP_SPEC, sort_keys=True)` in `agent/edit_dsl.py`; `validate_dsl_replay.py` refuses to run if the code no longer hashes to this value.)

| Op | Parameters | What the template does | Leakage class it targets (my mapping) |
|---|---|---|---|
| `move_into_fold` | step, call | a resampler (`X, y = call(X, y, ..)`), a selector (`k = call(X, y, ..)` used as `X[:, k]`) or a fitted transformer class (`V = Cls(..).fit_transform(X)`) at the top level of `step` runs per fold, on training rows only | pre-processing / feature selection / resampling on train and test together |
| `drop_from_eval` | step, call | removes a label-using resampler or selector from the evaluation path; refuses a transformer | resampling or label-driven selection on the evaluation path |
| `replace_split` | step, kind (random, group, temporal), col | rewrites a hold-out step's body, a `train_test_split(np.arange(n))` call, or the CV splitter in `step` | no proper test set; temporal leakage; non-independence of samples |
| `retrain_inside` | step | a model fitted once before a `for tr, te` loop and used inside it is refitted on each fold's training rows | model state fitted on all rows reused to score held-out rows |

Not covered, by construction: duplicates between train and test, illegitimate features (there is no feature op), sampling bias of the data, metric changes, model or
hyperparameter changes. Statement shapes a template does not recognise raise `NOT_APPLICABLE` (a normal outcome, not a crash).

**Taxonomy source.** Kapoor and Narayanan, "Leakage and the reproducibility crisis in machine-learning-based science", arXiv 2207.07048. I fetched the abstract today
(Nov 2, 2026): it states "a fine-grained taxonomy of 8 types of leakage". **UNVERIFIED:** the per-type names and numbering used in the mapping column above are from
my memory of the paper, not read from the paper here. The op list is *derived from* those leakage classes, not a transcription of the paper's table.

**Honesty about how the ops were chosen (required reading before trusting any "held-out" claim).**
- Failures we had already observed informed which ops were implemented first and how: `move_into_fold` and `replace_split` (the two most-needed ops, per the architect
  note) were written after we had seen G5 to G8 and the EHG offline probe (oversampling before CV; random vs temporal hold-out on civil war; screening before CV in ESL).
  `drop_from_eval` was added with the EHG "oversampler removed" fix in view. `retrain_inside` came from the taxonomy only; no saved plan or case exercises it, it is tested
  on a synthetic source only.
- **EHG is therefore NOT a held-out case for this DSL.** Neither are civil war or ESL. A held-out check needs a case the ops were not designed from; none exists yet
  (see section 8). The known-correct fixes below are a *regression test of the implementation*, not evidence that the DSL generalises.
- The op list was frozen (hash above) before the replay was run. The implementation files were frozen too (section 6) and were not edited after the first replay run.

## 3. Contract and `check_plan` (what the planner sees up front)
`contract_g9.contract_text()` returns the full rule spec (12 rules, `R-OPS .. R-RUN`) plus the plan schema; its sha256 is recorded in `runs_g9_offline/summary.json`.
`check_plan(plan, case_dir, runtime=False)` is the tool form: structure, op parameters, step and call existence, columns, the time-column and temporal-use rules, SPLIT-USE-REQUIRED
(now stated, not taught by rejection), and a trial compile of every config. `runtime=True` additionally runs the behavioural guard. Plans carry 1..3 factors; the factorial layout
(`fix_A`, `fix_B`, .., `fix_all`) exists only when k >= 2, k == 1 gives one config `fix_all`; `verdict: "no_flaw"` is a legal answer. The old G8 sandbox expects `fix_A/fix_B/fix_both`;
`edit_dsl.legacy_sources` is a plumbing adapter only (k == 1 gives the same source three times, it is not a factorial).
SPLIT-USE-REQUIRED, which the skeptic called partly self-grading ("the guard plus the model reproduce the published control"), is kept and disclosed as rule R-USE-REQUIRED.

## 4. Behavioural guard (`agent/guard_g9.py`)
A compiled config is run once in an isolated interpreter (smoke profile: civil war `N_TREES=6`, EHG `N_TREES=20`, all rows). Row arrays carry row ids (`TracedArray`, propagated through
indexing, boolean masks, `np.concatenate/vstack`, `DataFrame/Series.to_numpy` called from the case module); every outermost sklearn `fit/fit_transform/predict/predict_proba/decision_function/transform/kneighbors`
is recorded with the rows it received, and functions named by an op are wrapped too. From the recording:
- **Which rows are FIT and which are SCORED:** per scoring event, the rows of the same estimator's latest fit (`self`) and of every upstream fitted component or named function seen since the previous evaluation
  event or most recently (`ctx`, e.g. `oversample`, `NearestNeighbors`, `SelectKBest`), intersected with the rows scored. The *evaluation* rows are the row ids of the returned `y_true`.
- **MODEL:** the scoring model class set must be equal, hyperparameter names equal, and values that are constants in the source equal (a value computed by a tuner may differ).
  A `NearestNeighbors` inside an oversampler is a component, not the scoring model, so removing the oversampler no longer reads as "MODEL changed".
- **Row count:** evaluation rows equal the original's unless a `replace_split` is present; removing synthetic rows from the scored set is the only other allowed change.
- **Per-op precondition and postcondition, checked by running:** `move_into_fold`: the original's scored rows were seen by `call`, the fixed config's are not, and `call` is still called.
  `drop_from_eval`: `call` is called in the original, receives the label, is on the evaluation path (scored rows pass through it or synthetic rows are scored); gone after the fix. `replace_split`: the
  original violates the relation (random: rows fit and scored overlap; group: a group is both; temporal: not all training rows strictly earlier), the fixed config satisfies it (temporal *direction* is checked,
  which the old static guard could not do). `retrain_inside`: scored rows no longer in the model's fit rows.
- **NOOP:** a config whose fit/score row sets, upstream row sets and counts all equal the original's is rejected.
- **Fail closed:** lost row provenance, or row ids rebuilt in the pipeline (`reset_index`, row drops) when a group or time column must be mapped, gives `UNVERIFIABLE`, which is not accepted.
Limits (also section 8): only outermost sklearn estimators are seen; custom numpy models are invisible; a pipeline that rebuilds row ids cannot be verified for group/temporal ops; the check is one smoke run, not a proof.

## 5. Replay method (no model, no spend)
`eval/validate_dsl_replay.py` reads every saved plan in `runs_g5`, `runs_g6`, `runs_g7` (first plan and, when different, the final retry plan, per case and repeat) and the plans present in
`runs_g8` at the moment of reading (first plans recovered from `traces.jsonl` by recomputing the exact planner user message; final plans from `r*.json`; G8 was still running, a snapshot
of what was read is stored in `summary.json`).
1. **Old guard decision:** `factorial_g7.guard(case, plan, rules=justification+split_required)`, i.e. TODAY's static rules (the strictest generation). The stored verdict at that plan's position in the log is recorded next to it.
2. **Translation to DSL:** a heuristic, per legacy edit (`translate_step`): a temporal marker (TimeSeriesSplit, comparison against a time-like column or a variable derived from it, sort+slice) -> `replace_split(temporal)` with
   the column named in the edit; random splitter/permutation on a hold-out step -> `replace_split(random)` (stratification is dropped, so this is an approximation); a group splitter whose group column is a string constant in the edit
   -> `replace_split(group)`; a local call that ran before the split and whose learners now run inside a fold loop -> `move_into_fold`. Everything else is recorded as **NOT expressible** with its reason: feature edits,
   unshuffled/contiguous folds (no such kind), tuner removal, free-form rewrites of a whole step, unparseable legacy text. A plan is *full* when every legacy edit translates, *partial* when only one of A, B does (the
   DSL plan then carries the translatable factor only; its new decision is for that sub-plan and is marked partial), *none* otherwise (decision NOT_EXPRESSIBLE). The translator is itself a heuristic; its output is stored per plan.
3. **New guard decision:** `check_plan(dsl_plan, case, runtime=True)`: static contract, compile of every config, runtime behavioural guard on every config. ACCEPT, REJECT (with reasons), UNVERIFIABLE, or HARNESS_CRASH.
4. **Known-correct fixes** (section 6, P2) and **known-wrong ops on the clean twins** are run as one-factor plans.
Clean-control cases: `clean_control, clean_group_correct, clean_wine_correct, g4_visit_history_clean, civilwar_temporal_clean, civilwar_disguised_clean, esl_selection_clean, ehg_disguised_clean`.
"Rightly rejected" (for P3), fixed before running: an old (today's rules) REJECT on a clean-case plan is rightly rejected unless every one of its reasons is a documented over-strict rule
(`FEATURE-REASON` blocking a testable hypothesis, EVAL-6 and the forensics note; `FEATURES changed` on a verbatim inline of `feats`, EVAL-5 section 4). The EHG MODEL-on-resampler over-strictness (EVAL-11 section 6) has no saved plan.
Honest wrinkle: on a clean pipeline, any compiled "fix" is an invented fix; the old guard accepting some of those on retry is itself a weakness, and the new guard is not required to accept them.

## 6. PASS CRITERIA (preregistered before the replay was run)
Computed by `validate_dsl_replay.py`, written to `runs_g9_offline/summary.json`. The result is PASS only if all three hold; otherwise it is reported as FAIL with the offending rows.
- **P1, crashes:** 0 crashes on compiled code over all translated plans and the known cases. Crash = a compiled config that raises, times out, produces no output, or fails to compile for an INTERNAL reason, or a harness exception.
  `NOT_APPLICABLE`, `PRECONDITION`, `NO_SUCH_STEP`, `BAD_PARAM` are rejections, not crashes. (If the original itself does not run in the smoke profile the plan is UNVERIFIABLE, not a crash.)
- **P2, false rejects on known-correct fixes:** 0 of 5 rejected (every one must be ACCEPT): EHG `move_into_fold(claimed_eval, oversample)`; EHG `drop_from_eval(claimed_eval, oversample)`;
  civil-war disguised `replace_split(split_rows, temporal, epoch)`; civil-war apparent `replace_split(split_rows, temporal, year)`; ESL `move_into_fold(claimed_eval, screen)`.
  Companion check P2b (reported, same weight): the matching ops on the clean twins (EHG clean x2, civil-war disguised-clean, civil-war temporal-clean, ESL clean) must not be ACCEPT (0 false accepts).
  *These five were used while building the ops, so P2 is a regression test, not a held-out test.*
- **P3, no clean-control plan newly accepted that the old guard rightly rejected:** among replayed plans on clean-control cases whose old (today's rules) decision is REJECT and rightly rejected (section 5), 0 have a new decision of ACCEPT.
- Reported with n, not part of PASS: the old-versus-new crosstab (all plans and expressible plans), coverage (full / partial / none), counts by generation, UNVERIFIABLE counts, the old over-strict clean rejections and what the new guard did with them.

FROZEN_FILE agent/edit_dsl.py `8964d560ce7a76acacb4828ef6db5ed198fa858fd34937daf46c72704239b1e5`
FROZEN_FILE agent/guard_g9.py `4a084a1c466b1e8ff53ce3da94307796dc7475c275e0fdb889888f182fa17dba`
FROZEN_FILE agent/contract_g9.py `99c3117dc9b592810d02489a30e9952969bc05092ae18b6430928339db91b011`
FROZEN_FILE eval/validate_dsl_replay.py `d32cc6b1dcf1e3727ff6b58556bea51c6d0041df4c6bc2300421ba01b7119361`
(sha256 after CRLF to LF normalisation, as in EVAL-11. Contract text sha256 `2e68292243af1d4ebab3fed2fd75ee494f7b5ec8fa33acef2a363ddfd7ac0284`. The tests were written before the freeze and are not part of the frozen set. Any later edit to a frozen file
invalidates this preregistration; the replay must then be re-run and relabelled.)

Development honesty: while building I ran the templates and guard on EHG, ESL, civil war and `g4_pump_inspection`, fixed three bugs found that way (missing base-class estimator wrappers, a size-only no-op signature, row ids rebuilt by
`reset_index`) and improved the translator's coverage detection (module string constants, derived time variables) using translate-only runs that produce no guard decisions. No replay decision was seen before the freeze.

## 7. Results
(Filled in after the run, below. The sections above were not changed after the run.)

Run: Mon Nov 2, 2026 (wall time 173 s, 3 workers, 0 model calls). Raw outputs: `runs_g9_offline/summary.json`, `decisions.json` (one row per plan with old/new decisions, reasons and the
translation), `known_cases.json`, `table.md` (82-row old-vs-new table), `run.log`. The four frozen files hashed to the frozen values at run time (`unfrozen_mismatches: []`).
Plans replayed: **n = 82** (G5 28, G6 18, G7 17, G8 19 as present at read time: `r1..r5.json`, traces sha256 `9286a316...`), of which 42 are on clean-control cases.

**PASS (engineering criteria only): P1 true, P2 true, P3 true.**
| Criterion | Result |
|---|---|
| P1 crashes on compiled code | **0** of 82 translated plans (53 had a compilable DSL plan) + 10 known cases; no timeouts, no INTERNAL compile errors |
| P2 false rejects on known-correct fixes | **0 of 5** (EHG move_into_fold ACCEPT; EHG drop_from_eval ACCEPT; civil-war disguised temporal ACCEPT; civil-war apparent temporal on `year` ACCEPT; ESL screen moved ACCEPT) |
| P2b known-wrong ops on clean twins | **0 of 5** accepted (all REJECT: EHG clean x2 `NOT_APPLICABLE` (nothing before the fold to move); civil-war clean x2 `PRECONDITION` (split already temporal); ESL clean `NOT_APPLICABLE`) |
| P3 clean-control plans newly accepted that the old guard rightly rejected | **0 of 9 candidates** (4 REJECT by the new guard, 5 NOT_EXPRESSIBLE, so 5 of the 9 are "not accepted" only because the DSL cannot say what the model wrote) |
Measured on the EHG pair (runtime, smoke): oversampler rows seen by the scored rows: original 447 overlapping rows and 224 synthetic scored rows; after `move_into_fold` 0 overlap and 0 synthetic scored; after `drop_from_eval` 0 and 0.
The scoring model stays `RandomForestClassifier` with identical hyperparameters, which is the EVAL-11 section 6 false reject (a "MODEL changed" verdict on removing oversampling) not occurring.

**Old guard (today's static rules) versus new guard, all 82 plans** (old = `factorial_g7.guard` with justification + split_required; new = contract + compile + runtime guard):
| old \ new | ACCEPT | REJECT | UNVERIFIABLE | NOT_EXPRESSIBLE | total |
|---|---|---|---|---|---|
| ACCEPT | 12 | 19 | 1 | 15 | 47 |
| REJECT | 1 | 20 | 0 | 14 | 35 |
| total | 13 | 39 | 1 | 29 | 82 |
Among the 53 plans with at least one translatable factor (7 full, 46 partial): old ACCEPT 32 / REJECT 21; new ACCEPT 13, REJECT 39, UNVERIFIABLE 1. By generation, new decision: G5 ACCEPT 3, REJECT 5, UNVERIFIABLE 1, NOT_EXPRESSIBLE 19;
G6 ACCEPT 2, REJECT 7, NOT_EXPRESSIBLE 9; G7 ACCEPT 4, REJECT 12, NOT_EXPRESSIBLE 1; G8 ACCEPT 4, REJECT 15. Stored (live-time) verdicts for the same plans: ACCEPT 56, REJECT 26.
Coverage: full 7, partial 46, none 29 (of 82). Not-expressible edits by reason (per edit, A and B counted separately): contiguous/unshuffled folds 33, free-form rewrite 32, feature edit 16, already-fold-scoped or structural rewrite 10,
unrecognised split replacement 7, time column not identifiable 4, group column not identifiable 3, unparseable legacy text 2.

**What the new decisions mean (read before quoting any number).**
- All 13 new ACCEPTs are on *leaky* (non-clean) cases and are the intended fixes: civil-war temporal hold-out (8 final retry plans, G7 and G8), ESL screen moved into the fold (2), assay-replicates group split (3). **No clean-control plan was accepted by the new guard** (0 of 42).
- The 19 "old ACCEPT, new REJECT" are mostly not disagreements about the fix: 15 plans were rejected because the excerpt states a forecasting use and their only translatable factor is a random hold-out (R-USE-REQUIRED, the same rule that rejected them live in G7/G8, now stated up front);
  most of the remaining ones are clean-case plans rejected as a no-op (the split is already temporal, 15 plan-configs) or by a postcondition. They show the contract is stricter in the intended places, not that old accepts were wrong.
- **Likely false reject, found by the replay (not in P2, not fixed because the files are frozen):** 7 clean-case plans (all `civilwar_disguised_clean`) with an inner `replace_split(tune_mtry, temporal)` were rejected by the strict postcondition "every training row strictly earlier than every scored row" (180 of 180 pairs). With `TimeSeriesSplit` on integer epochs
  the fold boundary falls inside an epoch, so the max training epoch equals the min test epoch. This is a guard strictness choice (strict `<`), probably too strict for CV-style temporal splitting; a v2 would need a documented tolerance (for example `<=` for CV folds) and a new preregistration. On a leaky case it would reject a legitimate inner temporal CV.
- Plans on clean cases for which the old guard's rejection was a documented over-strict rule (10 plans, G5 `clean_group_correct`, `clean_control`, G6 `civilwar_temporal_clean`): the new guard returned NOT_EXPRESSIBLE for 9 and REJECT for 1. **So the replay does not show the new guard rescuing the documented old false rejects**; the only demonstration of the EVAL-11 false-reject fix is the EHG known-correct pair (no saved EHG plan exists).
- 1 plan is UNVERIFIABLE (G5 pump inspection: `add_lag` calls `reset_index`, so row ids are rebuilt and the group column cannot be mapped), which is the fail-closed behaviour working as designed and a real coverage limit.
- Of the 53 translatable plans, 46 carry 1 factor and 7 carry 2 (a factorial layout only there): a one-flaw case no longer needs an invented factor B (the 2x2 forced layout caused the G8 r1 violation and the EHG rejection).

Tests: `tests/test_dsl.py` (23) and `tests/test_guard_g9.py` (9) pass offline (`.venv/Scripts/python.exe -m pytest tests/test_dsl.py tests/test_guard_g9.py`, about 40 s). `tests/test_g7.py`, `test_g8.py`, `test_ehg_runner.py` were not touched.


## 8. Limits and UNVERIFIED
- **No held-out case.** All four ops were designed with G5 to G8 and the EHG probe in view. A real held-out check needs a leakage case outside the op list's design set (for example a cross-validated pipeline with a
  scaler/PCA in a helper function, or duplicate rows), run live, preregistered. Not done here.
- The replay checks that the harness accepts known-correct fixes and rejects invented ones; it does not show that the model will *choose* these ops, find them, or size the effect. That is the (unrun) live G9 question.
- The translation from legacy free-text edits to ops is heuristic and the "not expressible" share is large. A plan counted as expressible may differ in detail from what the model wrote (for example stratification is dropped).
- The runtime guard is one smoke run per config; it sees outermost sklearn estimators and functions named in ops, not arbitrary numpy models. Pipelines that rebuild row ids (`reset_index`) make group/temporal ops UNVERIFIABLE.
- `retrain_inside` and the transformer-class shape of `move_into_fold` are covered by synthetic tests only. Transformer chains inside a helper (for example `prep_full`, `prepare`) are NOT_APPLICABLE in v1.
- Dropping a label-driven selector with `drop_from_eval` satisfies the written precondition but changes what the model sees; whether that is a legitimate "evaluation fix" is a methodology call the owner must make before using it live.
- Taxonomy names/numbering from memory: UNVERIFIED (section 2). Smoke profile (`N_TREES` reduced) preserves provenance and structure, not model quality; no accuracy or inflation number comes from this work.
- G8 was still running during the replay; the G8 plans used are those present at the time of reading and are listed in the snapshot.
