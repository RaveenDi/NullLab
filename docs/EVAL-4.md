# NullLab EVAL-4: G4, cases where reading should get it wrong (Sun Nov 1, 2026, about 12:10 to 12:50 SLT / 02:40 to 03:20 ET)

All cases are **SYNTHETIC**, built by the builder. Every number below was measured on this machine.
- Raw outputs: `runs_g4/` (ref, b3, plan, loop, score, prereg_log.jsonl) and `runs_live/` (the EVAL-2 rerun).
- Builder: `eval/build_factorial_g4.py`. Ground truth and reference patches: `eval/factorial_truth_g4.json` (evaluator only).
- Driver: `g4.py`.

**Result: acceptance FAILS on one clause.** The loop false-alarmed on 1 of 4 clean cases. The other two clauses pass: the loop got the sign right on 4/4 new cases, and B3 was wrong on 3/4.

## 1. Housekeeping
- **Separate output folders.** `pipeline.py` now writes LIVE runs to `runs_live/` and MOCK runs to `runs/`. It refuses to write a mock run into `runs_live/`.
- **Score and app.** `eval.score --live` reads and writes `runs_live/`. `app/server.py` serves `runs_live/` first.
- **Tests.** They redirect both folders to temp dirs; two new tests check this, and two more cover the G4 scoring helpers and agent-view isolation. **Final pytest: 45/45 passed**, including the exfil tests.
- **Call cap.** `agent/llm.py` has a G4 phase cap of 70 calls, logged in `runs/live_calls_g4.jsonl`. **43 were used.**
- **Unchanged.** The sandbox (network off, exfil tests) is unchanged and its tests pass.

## 2. Cases
Each case has two plausible flaws, A and B. Columns are hashed. Each excerpt states a claim.

| Case | Design intent | A | B |
|---|---|---|---|
| g4_freight_delay | CANCELLATION | carrier late-rate = groupby-target mean on all rows (L2/L1.2, inflates) | test-only `fillna(0)` for dwell time, while Methods say median imputation; dwell is missing more often on late shipments (deflates) |
| g4_pump_inspection | WRONG-CULPRIT | SelectKBest on all rows (textbook L1.3; here it is stable, so harmless) | `prev_load = shift(-1)`, which is actually the NEXT inspection (L2 look-ahead) |
| g4_crop_irrigation | BENIGN-SUSPICIOUS | scaler + PCA fit on all rows | grid search on all rows (4-point grid, n = 3200) |
| g4_assay_replicates | SYNERGY-2 (classes L1.2 × L1.4, vs the spike's L2 × L3.2) | failed reads imputed with the per-CLASS mean over all rows | triplicate wells split at random; the claim is about new compounds |
| g4_visit_history_clean | clean factorial variant of the spike | none (out-of-fold rate) | none (group split) |

The 3 corpus clean controls are frozen and were reused unchanged.

**Design iteration (before preregistration only).** Freight and assay were tuned 3 to 4 times, using the builder's reference patches only. No agent output existed yet, and no prompt was changed at any point.

## 3. Preregistration
`runs_g4/prereg_log.jsonl` holds 26 records. In order:
1. **Scoring rule**, sha `54c35b18…`, at 07:05:57Z = 12:35 SLT. It came first, together with every case's agent-view hashes.
2. **8 B3 calls**, 07:06 to 07:08Z.
3. **B3 label mapping**, `4db51fe8…`. In the pump case, B3's A and B are swapped relative to ours.
4. **8 loop-planner calls**, 07:08 to 07:12Z.

The loop then ran and finished at 07:14Z.

The prompts are the same as in the spike: `agent/factorial.py` and `baselines/single_prompt.py`. Both are untouched.

## 4. Results
Truth comes from the evaluator's reference patches. The loop runs Spark's own LIVE patches. Each case covers seeds 42/43/44, with n_boot = 1000 and an **unpaired** bootstrap. "Drop" means orig − fix_both, in pp.

| Case | Truth: sign / culprit (mean pp) | Loop (planner patches, executed) | B3 (reading only, 1 call) | B3 wrong? |
|---|---|---|---|---|
| freight (CANCEL) | **−** / none. Fix-both −10.4: the claim is UNDERSTATED. Fix-A alone +5.2 | **−** on 2/3 seeds; CIs [−11.6, −1.9], [−9.0, +0.4], [−9.8, −0.5]; mean −5.5. The planner itself had predicted +9 | leak = true, fix-both **+7** → sign +, verdict INFLATED | **yes** (sign and verdict) |
| pump (WRONG-CULPRIT) | **+** / B (shift); A = 0.0, B = 16.0, I = 0.0 | **+** 3/3 seeds, mean +16.0, culprit = the shift | ranked the shift first, fix-both +14 | **no**. Spark caught the subtle flaw; the temptation failed |
| crop (BENIGN) | **0** / none; fix-both −0.7 | **0** 3/3 seeds; CIs about ±5 around 0 | leak = true, fix-both **+3.5** | **yes** (verdict and sign) |
| assay (SYNERGY-2) | **+** / **AxB**: A 6.3, B 10.8, I 12.8, both 29.9 | **+** 3/3 seeds, both +30.7. I = +13.8, with CI excluding 0 on 3/3 seeds ([8.4, 21.5], [1.1, 13.5], [12.8, 25.3]) | ranked **B** first, fix-both +22, outside the loop CI on every seed | **yes**, but only on the culprit. B was the runner-up, 2.0 pp behind AxB |

### Clean cases (loop false alarm = fix-both sign +)

| Clean case | Loop fix-both CI per seed | B3 |
|---|---|---|
| clean_control | spans 0 ×3 | leak = true (false alarm) |
| clean_wine_correct | spans 0 ×3 (n = 45, very wide) | leak = true (false alarm) |
| g4_visit_history_clean | spans 0 ×3 | leak = false |
| **clean_group_correct** | **+ ×3**: [8.2, 20.7], [4.7, 18.4], [9.0, 21.1] | leak = false |

**Why the loop false-alarmed on clean_group_correct.** The planner hypothesised that "one measurement is target-leaky". Its fix_B and fix_both **drop the feature most correlated with the label** and switch to GroupKFold. So the 14 pp drop comes from removing a legitimate predictor, not from any leak. The loop measures whatever the patch does: nothing checks that a "fix" corrects only the named step and leaves the model the same.

### Acceptance (preregistered)

| Clause | Measured | Met? |
|---|---|---|
| Loop sign correct on ≥ 3/4 new cases | 4/4 | yes |
| B3 wrong on ≥ 2/4 new cases | 3/4 | yes |
| Loop false alarms on clean cases = 0/4 | **1/4** | **no** |
| Strict check: fix-both spans 0 on all seeds | 3/4 | (reported only) |
| B3 false alarms on clean cases | 2/4 | (reported only) |

**Overall: FAIL.**

## 5. EVAL-2 live rerun (`runs_live/`)
27 live calls: 18 for pipeline plus 9 for B3.

| Method | Recall | False alarms |
|---|---|---|
| Loop | 5/6 (leak_prescale INCONCLUSIVE again) | **1/3** |
| B3 | 6/6 | 0/3 |
| B0 | 0/6 | 0/3 |
| B1 | 1/6 | 0/3 |

- Grounding precision: 1.0.
- The earlier run had loop false alarms at 0/3. Live Spark is not reproducible run to run.
- **New false alarm: clean_wine_correct**, at +23 to +34 pp. The falsifier tested an *ordered* last-25% split. The wine rows are stored by class, so this is a distribution-shift test that the claim never made.
- **clean_group_correct was INCONCLUSIVE.**
- Same failure class as G4: the controlled experiment answers a different question than the claim.

## 6. Honest reading
- **What execution showed that reading did not:**
  - In **cancellation**, B3 and Spark's own planner both predicted "inflated". Executing the planner's own patches reversed the sign. That is the clearest case so far that execution can be essential.
  - In **benign**, execution cleared a confident false alarm: B3 said leak = true and +3.5 pp.
  - In **synergy-2**, execution found that the interaction dominates.
- **What failed:**
  - The wrong-culprit design did not fool Spark.
  - The synergy-2 culprit miss is narrow (2 pp).
  - The loop has a real, unguarded failure mode: an over-reaching "fix" that changes the model rather than the evaluation step. It produced a G4 false alarm, and in EVAL-2 a confounded "controlled" protocol produced another. On clean cases this makes the loop about as error-prone as reading: loop 1/4, B3 2/4.
- **Limits:** n = 4 new cases, all SYNTHETIC and built by us, and one B3 call per case at temperature 0. Nothing here is a rate.

## Spend
- Meta spend went from $10.67 to **$13.10** (+$2.43 at per-call estimates), using 43 of the 70 live calls allowed.
- That is within the $12 pre-approval and the $30 cap.
