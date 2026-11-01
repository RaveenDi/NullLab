# NullLab EVAL-5: G5, patch-fidelity guard + 3 repeats (Sun Nov 1, 2026, SLT with ET alongside)

All cases are **SYNTHETIC** (the G4 set, unchanged). Raw outputs: `runs_g5/`. Driver: `g5.py`. Guard: `agent/fidelity.py`.
Planner: `agent/factorial_g5.py`. Builder fixtures for tests: `eval/g5_fixtures.py`. Tests: `tests/test_fidelity.py`.

Sections 1 to 3 were written **before any G5 live call**. Results follow in section 4.

## 1. Guard design (written before running)

**Why.** In G4 the loop false-alarmed on clean_group_correct. The planner's free-form fix_B and fix_both dropped the feature most correlated with the label and switched to GroupKFold. Nothing checked that a "fix" changed only the step it named.

### (a) Structured edits, applied by code
- The planner no longer writes whole files.
- For each of A and B it returns `{"kind": "split" | "fit_scope" | "feature", "steps": {"<top-level function of train.py>": "<complete new def>"}}`. If A and B edit the same function, it also returns `both_overrides`.
- Code replaces exactly those defs in the ORIGINAL train.py (`fidelity.apply_edits`). It then runs the edited `claimed_eval(df, seed)`:
  - fix_A applies A's edits only.
  - fix_B applies B's edits only.
  - fix_both applies both.
- Everything not named stays byte-identical to the claim's code (up to AST unparse).
- Replacements may import only numpy, pandas or sklearn. `load` may not be edited.
- There is no `model` or `metric` kind. A fix may never change the model or the metric.

### (b) Deterministic fidelity check
`fidelity.check_static` compares the code reachable from the claimed `claimed_eval` with the code reachable from the controlled one. `train.X` references are resolved, and comparison uses set semantics. Any violation rejects the patch.

| Check | Rule | Allowed only if a declared kind is |
|---|---|---|
| LOCALITY | Top-level AST diff: the changed defs must equal the declared steps, and a declared step that does not change is an error. | n/a |
| MODEL | The set of learned components must be identical: estimator, transformer, selector and tuner constructors with normalised arguments. The set of label-driven selection calls must also be identical (`corrcoef`, `corr`, `f_classif`, `mutual_info_*`, `feature_importances_`, ...). | never |
| FEATURES | The `feats` step and the column filters (comprehensions with comparisons, `.drop(columns=)`) must be unchanged. | `feature` |
| SPLIT | No original splitter call may be removed or changed, and the `test_size`/`n_splits` defaults must be unchanged. Adding KFold, StratifiedKFold or GroupKFold (out-of-fold statistics inside training rows) is allowed. | `split` |
| SAMPLE SIZE (runtime) | The test n of each config, per seed, must equal the original's. | `split` |
| METRIC | Fixed by construction: the sandbox computes accuracy from (y_true, y_pred). | never |

### (c) Recover
- A rejection by any check, or an execution error, triggers **one** live retry. The retry carries the violation or error text.
- If the retry is still rejected or still fails, the case-repeat is **INCONCLUSIVE**, never FALSIFIED.
- A rejected patch is never executed.

### (d) Optional verifier call
Not used. The check stays deterministic and the cost stays lower.

**Known gap, stated before running.** A `feature` fix that removes a *named* legitimate column with a confident but wrong justification passes the guard. The G4 clean_wine_correct plan ("the label is a threshold on one column") is this kind of fix. The guard blocks only *label-driven* column choice.

## 2. Offline replay and tests (before any live call)
`runs_g5/replay.json`, `python g5.py replay`:
- **G4 clean_group_correct planner patch:** fix_B and fix_both are **REJECTED** (MODEL: `corrcoef` added, a label-driven feature choice). This holds even under the most permissive kinds. fix_A (GroupKFold, a declared split) passes the invariants. As a whole-file patch, it would still be rejected on STRUCTURE.
- **All other G4 planner patches** (4 hard + 3 clean), **all G4 builder reference patches** and the **spike planner patches** pass the invariants.
- **Structured fixtures:**
  - GOOD_SPIKE and GOOD_PUMP are accepted on all 3 configs, with "only step X changed" = the declared steps.
  - Executed, they reproduce the reference: spike I ≈ +20 pp; pump B = +16.0, A = 0.0.
  - BAD_GROUP_FEATURE_DROP fix_B and fix_both are rejected.
  - BAD_GROUP_MODEL is rejected: MODEL on fix_A, SAMPLE SIZE on fix_B.
- **`tests/test_fidelity.py`: 17 passed.** It covers:
  - the replayed failure;
  - good legacy and structured patches;
  - feature, split and model rules;
  - structure violations;
  - the runtime n check;
  - Recover → INCONCLUSIVE, with no execution of a rejected patch;
  - Recover → accepted after a fixed retry.

## 3. Preregistration
- **Content:** the scoring rule (`g5.SCORING_RULE`), the B3 label-mapping keywords, source hashes of the guard, planner, B3, driver and fixtures, both system prompts, and the agent-view hashes of all 8 cases.
- **When:** all of it is logged in `runs_g5/prereg_log.jsonl` before the first G5 live call.
- **Per repeat:** every B3 answer and every planner plan is hashed and logged before execution. Every retry is logged when it happens.

**Repeats.** The only difference between repeats is the line `[repeat id: g5-rK]` in the user message, at temperature 0. B3's prompt is unchanged from G4.

**Planner prompt change.** The planner prompt differs from G4 in one way: it describes the structured-edit format and the guard's rules. That is a design change made before any G5 run, not tuning on results.

Acceptance (from the brief):
- (i) Loop clean false alarms ≤ 1 of 12.
- (ii) Loop sign correct in ≥ 10 of 12 hard runs. INCONCLUSIVE counts as wrong.
- (iii) B3 wrong in ≥ 6 of 12 hard runs.
- (iv) Every accepted patch passes the fidelity check. This is re-audited at scoring time.

## 4. Results (run 07:34 to about 08:05 UTC = 13:04 to 13:35 SLT / 02:34 to 03:05 ET)
**Calls.** 52 live calls, logged in `runs/live_calls_g5.jsonl` against a cap of 140: 24 B3, 24 planner, 4 retries.

**Spend.** Meta spend went from $13.10 to **$17.82** (+$4.72 at per-call estimates), under the ~$22 ceiling and the $30 cap.

**Scoring.** The score is in `runs_g5/score.json`. Rule sha256 `734de856…` was logged at 07:33:46Z, before the first call.

**Tests.** pytest 62/62, including the exfil tests and `tests/test_fidelity.py`.

### Acceptance (preregistered): **PASS**

| Clause | Measured | Pass |
|---|---|---|
| (i) loop clean false alarms ≤ 1/12 | **1/12** (clean_wine_correct r2) | yes |
| (ii) loop sign right on hard runs ≥ 10/12 | **11/12** (miss = crop r1 INCONCLUSIVE) | yes |
| (iii) B3 wrong on hard runs ≥ 6/12 | **9/12** | yes |
| (iv) every executed patch passes fidelity (re-audited) | 0 failures | yes |
| (reported) clean INCONCLUSIVE · retries · B3 clean false alarms | 0 · 4 · **7/12** | |

### Per case, per repeat
- **Drop** = orig − fix_both, in pp; positive means the claim was inflated.
- **CIs** are 95% CIs per seed (42/43/44), from an UNPAIRED bootstrap with n_boot = 1000.
- **B3** shows the predicted fix-both drop, the verdict and the mapped top culprit.

| Case (truth) | Rep | Loop sign (seeds) | Loop drop · I | Fix-both CI per seed | B3 | B3 wrong? |
|---|---|---|---|---|---|---|
| freight (−) | r1–r3 | **−** (− 0 −) ×3 | −5.5 · +4.2 ×3 | [−11.6,−1.9] [−9.0,+0.4] [−9.8,−0.5] (identical ×3) | +10 / +8 / +5, INFLATED ×3 | yes ×3 |
| pump (+, B) | r1 | + (+++) | +15.4 · −0.8 | [12.1,19.7] [10.8,18.3] [11.6,19.6] | +13, top = shift | no |
| | r2, r3 | + (+++) | +16.0 · 0.0 | [10.1,17.7] [14.4,22.4] [11.2,18.9] | +13 / +16, top = shift | no ×2 |
| crop (0) | r1 | **INCONCLUSIVE** | n/a | n/a | +4, INFLATED | yes |
| | r2, r3 | 0 (000) | −0.7 · −0.6/0.0 | [−6.2,3.1] [−4.0,5.1] [−5.1,3.7] | +4 / +5, INFLATED | yes ×2 |
| assay (+, AxB) | r1–r3 | + (+++) ×3 | +29.9 · **+12.8** ×3 | [20.9,30.1] [29.0,38.3] [26.3,35.0]; I CI [4.0,16.8] [6.1,19.2] [8.8,21.5] | +21/+22/+22, top = B | yes ×3 |
| clean_control | r1–r3 | 0 ×3 | +0.4 / +0.8 / +0.8 | all span 0 | +4.5/+7/+7, INFLATED ×3 | n/a |
| clean_group_correct | r1–r3 | 0 ×3 | +2.8 ×3 | [−2.4,10.3] [−6.1,7.0] [−2.5,10.1] | +34 INFLATED / 0 / +5 | n/a |
| clean_wine_correct | r1 | 0 | +4.4 | spans 0 | +5, NOT INFLATED | n/a |
| | **r2** | **+ (+++)** | **+39.3** | [24.4,57.8] [26.7,60.0] [13.3,51.1] | +6, INFLATED | n/a |
| | r3 | 0 | +4.1 · −25.0 | spans 0 | +26, INFLATED | n/a |
| g4_visit_history_clean | r1–r3 | 0 / 0 (00+) / 0 | +3.7 / +2.9 / +2.2 | r2 seed 44 [2.4,14.3]; all others span 0 | +11/+10/+6 | n/a |

### Run-to-run variance (SD of the loop's mean fix-both drop across 3 repeats)
**Loop:**
- freight 0.0, pump 0.3, crop 0.0 (2 measured), assay 0.0, clean_control 0.2, clean_group 0.0, visit_clean 0.8 pp.
- **clean_wine 20.2 pp** (4.4 / 39.3 / 4.1).
- On hard cases the planner converged to the same edits at temperature 0, so the repeats are **not** much more independent than one run. The variance shows up as **process** failures instead:
  - crop r1 was INCONCLUSIVE;
  - 4 retries in total;
  - the wine r2 plan.

**B3:** the predicted fix-both drop varies more, e.g. group 34 / 0 / 5 and wine 5 / 6 / 26 pp. Its hard-case verdicts were stable.

### What the guard did live
- **Retries (4):**
  - crop r1: FEATURES. The planner inlined `feats`' own comprehension, which is a **false rejection**; the guard is stricter than it needs to be. The retry then crashed with a NameError, so the run was INCONCLUSIVE.
  - clean_control r1: same FEATURES pattern; accepted after the retry.
  - visit_clean r2 and r3: SPLIT. The fix removed the out-of-fold KFold under the `fit_scope` kind; accepted after the retry.
- **clean_group_correct**, G4's failure, measured 0 on 3/3 repeats. The planner no longer dropped the label-correlated feature.
- **The remaining false alarm (wine r2) is the gap preregistered in §1.** The edits were:
  - A (kind `feature`) drops a *named* column, `c_55565a`, as a "leaky source measurement";
  - B (kind `split`) is an ordered last-25% split on class-sorted rows.

  Both edits are declared and in scope, so the guard accepted them. It is the same failure class as the EVAL-2 live rerun.

## 5. Honest reading
- **Supported, on 4 synthetic hard cases × 3 repeats:**
  - Executing guarded fixes gets the sign right where one-shot reading does not. Cancellation: B3 said "inflated" in 3/3 repeats; the loop measured "understated" in 3/3.
  - Benign: B3 false-alarmed in 3/3 repeats.
  - Synergy: B3 ranked the wrong culprit in 3/3 repeats.
  - Pump (wrong-culprit) did not fool B3 in any repeat.
- **Clean behaviour:** loop 1/12 false alarms vs B3 7/12 (B3's verdict). The guard fixed the G4 failure mode, a label-driven or undeclared model change.
- **Not supported:**
  - The guard does not stop a *declared* but unjustified fix. Wine r2 shows this.
  - Repeats at temperature 0 are weakly independent; the hard-case loop numbers were identical across repeats.
  - n = 8 synthetic cases built by us. These are counts, not rates.
- **Next guard step** (not run, would need a new preregistration):
  - a `feature` kind must cite a code or excerpt reason that the column is post-outcome;
  - a `split` change must match the excerpt's stated deployment, e.g. no ordered split unless the claim is temporal;
  - stop rejecting a verbatim inline of `feats`.
