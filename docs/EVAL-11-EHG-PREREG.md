# EVAL-11 / EHG preregistration: the G8 harness on the disguised EHG pair

Written Mon Nov 2, 2026, 12:40 SLT (02:10 ET), BEFORE any EHG live call. No live call has been made for this run (the call log
`runs_ehg/live_calls_ehg.jsonl` does not exist). Runner: `agent/factorial_ehg.py`. Tests: `tests/test_ehg_runner.py` (22, offline, pass).
Question: does the loop that was hardened in G8 find and size a flaw it was not written for, on real public data (EVAL-10: oversampling before
cross-validation, TPEHGDB features, our port of the published flaw), under the same disguise recipe as G7/G8? This is a NEW, separately
labelled run. It does not re-score, merge with or change G7 or G8, and G8 is still running under its own frozen hashes.

## 1. What is reused, what is new
Reused by import and NOT edited: `agent/factorial_g8.py` (pipeline, repair budgets, labels), `agent/factorial_g7.py` (validate_plan, guards, B3 prompt),
`agent/factorial_g5.py`, `agent/factorial_g6.py` (planner prompt), `agent/llm.py`, `agent/fidelity.py`, the sandbox and statistics. Their raw (CRLF as stored)
sha256 are identical to the values frozen in `docs/EVAL-9-G8-PREREG.md` (checked Nov 2 for g8, g7, llm, fidelity, g5, g6, stats, run_factorial,
executor), so this run uses exactly the G8 harness.
New: the case mapping, the run directory, the call log and cap, the acceptance numbers, the freeze/verify stages (this document and the runner).
- **Cases:** `real/ehg_disguised` (leaky) and `real/ehg_disguised_clean`. Same excerpt; train.py differs in 3 lines (EVAL-10).
- **Own paths:** everything in `runs_ehg/`: call log `live_calls_ehg.jsonl` (+ `.usage.jsonl`), traces `traces.jsonl`, prereg log `prereg_log.jsonl`,
  per-repeat `r1..r3.json`, `score.json`. `configure()` sets the env paths of the G8 modules to `runs_ehg/` and aborts if any path would fall back to
  `runs_g8/` (tested), so a running G8 job is never touched.
- **Caps:** per case unchanged (1 plan call + 1 repair each of guard / crash / bad_json = max 4 planner-side calls) plus 1 B3 call; **40 live calls in
  total for the run** (`llm.MAX_G8_CALLS` set to 40 in this process, counted on our own log, attempts counted before the request). Expected maximum
  is 6 x 5 = 30. Spend ceiling USD 3.00 (`NULLLAB_EHG_CEILING`); the run refuses to start if spent + worst case passes it.
- **SPLIT-USE-REQUIRED:** kept in the guard set exactly as in G8 and it applies only if the excerpt states a forecasting use. The excerpt has none of its
  14 trigger words (checked, logged in the freeze record: `forecast_words_in_excerpt: []` for both cases), so the rule is inert here by construction.
  The other guards (static fidelity, FEATURES-REASON, SPLIT-USE, SAMPLE SIZE) are unchanged.
- **B3:** the unchanged single reading prompt (`g7.B3_SYSTEM`), one call per case and repeat, same repeats and temperature, reported side by side.
- **Prompt:** the planner prompt is the unchanged G6 prompt (not tuned to this flaw). Prompt bundle sha256 equals G8's (`40dc30fe...`).

## 2. Protocol
Model `muse-spark-1.3-contributor` for every call, temperature **0.7**, reasoning_effort low (as `llm.py`), **3 repeats** (r1..r3) per case. Per repeat and
case: B3, then the G8 pipeline (plan, guard, sandbox 4 configs x seeds 42/43/44, n_boot 1000, unpaired bootstrap). Metric: **ROC-AUC** (train.py METRIC).
Measured inflation = claimed (orig) minus controlled (fix_both), mean over the 3 seeds; repeat sign from the 95 percent CI, category shared by >= 2 of 3
seeds. A recorded harness failure is not re-rolled; no repeat is re-run to replace a failure. Stages: `project | freeze | verify | run | score` (plus
offline `rulefix`, `hashes`, `usage`). `run` refuses unless `verify` passes (freeze present, all hashes recomputed from disk equal the freeze record).

## 3. Truth (host only; never in the agent view)
`eval/g8_truth.json` (EHG, EVAL-10, Vandewiele et al., arXiv 2001.06296): published rows give inflation +0.358 (SVM+SMOTE) to +0.494 (RF+SMOTE); stored truth value
0.494. Our offline reference measurement on this port (no model, `runs_g8_cases/reference.json`, 10 seeds): 0.970 vs 0.540, **+0.430**. The scoring target is
**+0.430** (the measurement of THIS pipeline); the published range +0.36 to +0.49 is reported next to it. A test asserts that the constants in the runner equal the
truth file and that no truth number or source name appears in the agent view or prompts. The published size is for the authors' own feature sets, so only direction and
rough size are comparable (EVAL-10 section 5).

## 4. Acceptance (preregistered, computed by `score`)
PASS iff all of:
 (a) direction right (repeat sign `+`) on the leaky case in **3 of 3** repeats,
 (b) **0** false alarms (sign `+`) on the clean case over its 3 repeats,
 (c) mean inflation within **0.15 of +0.43** (|mean - 0.43| <= 0.15) on **>= 2 of 3** leaky repeats.
Harness-INCONCLUSIVE (crash, bad_json, guard, call_cap, budget, api_error, internal_error) counts in the denominator (3 per case) as **not met** on (a) and (c), is never a
false alarm and never a "no effect"; it is listed with its reason, and `harness_target_met` (0 of 6) is reported next to PASS. A missing repeat cannot pass.
Reported alongside (not acceptance): B3 gets-it (leak == true, predicted fix_both >= 2 pp, |pp/100 - 0.43| <= 0.15) and B3 false alarms on the clean case, calls and repairs per case,
CIs, whether the mean lies in the published range, rule-baseline result, estimated spend and real tokens.

## 5. Rule baseline (offline, $0, run before the freeze; `runs_ehg/rules.json`)
I ran `baselines/rulefix.py` (frozen EVAL-8 rule set, spec sha256 `8be1b7e5f7137c2778361217df0e7599095fed5c1cdf8a3bb4c3b8b939c40385`, no model) on both disguised cases through the same sandbox
and statistics (`python -m agent.factorial_ehg rulefix`, 3 seeds, n_boot 1000). **Result: no rule fires on either case** (fired = {}, not_applied = []), all four configs equal
the original, inflation 0.000, sign `0` on both. I had expected it might fire R1/R2-type rules here; it does not: R1 needs a top-level split function whose scored rows overlap the
training rows, R2 needs a scaler/PCA/selector, and neither idiom exists. So the rule baseline **misses the leak (0 of 1 direction right) and has 0 false alarms**; it cannot match the
loop unless the loop also reports no effect. The earlier worry that the rules baseline would match the loop here is therefore not supported by this offline run. This is one deterministic
measurement per case, not repeats, and the rule author wrote the rules without an oversampling idiom, so it says nothing about a rule that would.

## 6. Known risks stated before data (not tuned against)
- **Guard fit (offline probe, no model, no code changed afterwards):** with the unchanged static guard, a lone edit that removes oversampling from `claimed_eval` is rejected ("MODEL changed",
  NearestNeighbors removed), so the natural pair "A = move oversampling into `fold_train_set`, B = delete it from `claimed_eval`" is rejected. A plan whose fix A edits both functions and whose
  fix B edits `cv_scores` without changing behaviour passes the guard (test `test_guard_on_ehg_plans_offline`). Whether Spark finds an accepted formulation within one guard repair is
  UNVERIFIED; the likely failure mode is `INCONCLUSIVE (harness failure: guard)`, which counts as not met. I did not change the guard or the prompt in response; that would be a different protocol.
- **Factorial attribution:** with one underlying flaw, the A/B split is arbitrary; only the sign and size of the fix_both inflation are scored.
- **Small n:** 3 repeats per case; 3/3 is strict and one harness failure fails PASS. The result is evidence about this pair, not a rate.
- **Contamination:** EVAL-10 probes (6 calls) found no source or domain recall, which shows Spark did not name the source, not that it has no memory.
- **Our port:** not the authors' code or feature sets; label REAL-PINNED with that qualifier (EVAL-10).

## 7. Hashes (sha256 after CRLF to LF normalisation)
Rule, stated because the G7 log hash did not match the file hash (cause not investigated; line endings are the likely one, the files are stored with CRLF on this machine): **every file is hashed as
`sha256(open(f,'rb').read().replace(b'\r\n', b'\n'))`**, text as `sha256(s.replace('\r\n','\n').encode('utf-8'))`, a JSON payload as `sha256(json.dumps(payload, sort_keys=True))`.
`freeze` writes these values AND the full payload into `runs_ehg/prereg_log.jsonl` (kinds `ehg_source_hashes`, `ehg_prompts`, `ehg_rules`, `ehg_agent_view_frozen` x2, `ehg_prereg_doc`);
`verify` recomputes them from disk and compares; a test recomputes the logged value independently with the formula above. Any later edit invalidates this preregistration and the run must be relabelled.

| File | sha256 (LF) |
|---|---|
| agent/factorial_ehg.py | `1ea35bbcc44ad49e984b3d95f4ec36a842319ee463201541b75aec6706fbf38d` |
| agent/factorial_g8.py | `0cf32783d3d7ef2cf8519cfa956197666d1b690ac2552ea5170858df260ed73c` |
| agent/factorial_g7.py | `dc17c381206872400fa14a99a3bd9ffb02240f370ac792189c5e7a30723290ce` |
| agent/llm.py | `230a54e8c1120c29b6a0531d0755d29918c33c47ff85d70b8b37432255afc8ab` |
| agent/fidelity.py | `9cde95bddadfb665ff30c33c020a5e9196d7dfec9163025978e025a2cb77e44a` |
| agent/factorial_g5.py | `b681cdb1e0372a52819ce02d925ebb45618b86a279d486002afef94782e627f8` |
| agent/factorial_g6.py | `83abdfb3b2cbee64b4d90595f7c60e8cc3fd94a661b1ba822d4978d286dd2f8d` |
| agent/factorial.py | `68d326f1bfd55a118efa402fcf60c47506a6c3ae499b5c2685e162aee7658ae3` |
| g4.py | `f6e9765cfd8ff6d59e20df9a1776da31b0794aa2c7b5dbb22ea236e32573d53a` |
| eval/build_g8_cases.py | `437332f18df7a27ae5d05ee277cf4af09393df995034f788cfd188e4257c55d8` |
| eval/g8_truth.json | `4875bf5386f4c32f8fac2d6088f99f3544a4067e2cfd3dedea01aec070117a4d` |
| eval/run_rulefix.py | `6540eee1eb86a0c0a70a62159ba0366b1d715f4080141c548b6116b31d0047ec` |
| baselines/rulefix.py | `5b9c687586e9d995ba80fd3f8c5d1668d2bff6ae10d8e555b0b2a685f31f537e` |
| sandbox/factorial_stats.py | `fcc8223659535bad0581ebd5eeb9bc2eb8b10f10e98c42137fb39f2d55a82495` |
| sandbox/run_factorial.py | `0eb2130abbea85e38420d353eec4c99368e99d9ea5953b9a04c91d92d0e819cb` |
| sandbox/executor.py | `3edf9ecc1db0a61129a2d02290ed337f71df7c6cea8cbb72bc1cbccddf8159dd` |


**Change before any live call (Nov 2, 2026).** `agent/factorial_ehg.py` was edited ONCE, after the first freeze and before any live EHG call (`runs_ehg/` holds no
`live_calls_ehg.jsonl`, no `traces.jsonl`, no `r*.json`; only `prereg_log.jsonl`, `rulefix_stage.log`, `rules.json`). Reason: its offline `rulefix` stage did
`from eval import ...`, which breaks the invariant that agent code never imports the evaluation folder (`tests/test_nulllab.py::test_agent_view_has_no_ground_truth`).
The stage now calls `agent.rules_measure.run_case` and `baselines.rulefix.spec_sha256`, and uses a verbatim copy of `eval/run_rulefix._row` (`_rule_row`) for the row;
two docstrings were reworded so the invariant's regex does not match them. Behaviour is unchanged (same measurement code, same row fields); nothing that feeds a
live call (prompts, rules bundle, agent views, G8 harness) changed: the prompts, rules bundle `04811c80...` and view hashes below are identical to the first freeze.
`freeze` was re-run and `verify` passes. `agent/rules_measure.py` (not a frozen file) got a one-line docstring rewording for the same regex.
Superseded (first freeze, kept in `runs_ehg/prereg_log.jsonl` as the earlier records): agent/factorial_ehg.py `e5c5f4ef35701e6cf5c2e7b18f5c372f847404235463ac3dfb6837dab3f96e38`.
The log is append-only; `verify` checks the LAST record of each kind.

Prompts: planner system `5596b60c851d9a943ff532db3a26f66ed16cbf218e0f5dee0401f01c31be2557`; B3 system `33829510dbda134a32ad8022484b3c8d25da64fc830c6f195708fff3399efb79`; bundle
(`{"planner_system","b3_system"}` JSON, identical to G8's) `40dc30fee676823fd090bea16586731a136f033b0ac845f8946ce32073d04bf9`.
Rules bundle (forecast words, repair kinds, caps, temperature, repeats, seeds, n_boot, guard rules, tolerance, reference, range, acceptance, ceiling): `04811c80ec5e971c39b180f50609b45b87be250e45c1f1d371db53515747971d`.

| Agent view | train.py | data.csv | excerpt.md | agent_view text | planner user msg (rid "RID") |
|---|---|---|---|---|---|
| ehg_disguised | `ec467eb0a0abb298...` | `4116c7323991d9f4...` | `6f83de23fe2c283f...` | `a5475d962e2694b4b47e945639a761f99e4e992a14651e653cb07a81a12404bd` | `f268e588c36aa184c17f11b05badb7ceb77c99edab9f6493f836f0192c7261bf` |
| ehg_disguised_clean | `35721f4e21241b09...` | `4116c7323991d9f4...` | `6f83de23fe2c283f...` | `bdc16bf4406b0f1baa823c77be1665b851ec6091d45610f27eb8644aeafb1edb` | `67dce15923adc261150ec68b5d701c1b12d6a6ccbfd327156996894162aade70` |

Full train.py / data.csv / excerpt.md hashes are in the freeze records. `runs_ehg/rules.json` (output, not frozen input) sha256 `f44f1a47e56c14eb902ad3e63f65f77a3447f87508ecfe78b50aa05c7210a9ca` (raw bytes).
This document is not part of the code set; its own LF sha256 is logged by `freeze` (kind `ehg_prereg_doc`) and checked by `verify`.

## 8. Spend and calls (estimates, not billing)
Floor USD 1.08 (6 B3 at 0.08 + 6 plans at 0.10, no repairs); worst case USD 2.88 (all three repairs on every case); ceiling USD 3.00. Calls: 12 minimum, 30 maximum, hard cap 40.
Real `usage` tokens are logged next to the estimate (`live_calls_ehg.usage.jsonl`, per-call records in `r*.json`, `usage` stage).

## 9. How to run (the author ran `project`, `rulefix`, `hashes` and `freeze`; the `run` stage was NOT run)
```
.venv/Scripts/python.exe -m agent.factorial_ehg verify          # must print VERIFY OK
.venv/Scripts/python.exe -m agent.factorial_ehg run 1 2 3       # LIVE, est. USD 1.08 to 2.88, max 30 calls (cap 40)
.venv/Scripts/python.exe -m agent.factorial_ehg score
```
