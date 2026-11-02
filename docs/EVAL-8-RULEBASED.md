# NullLab EVAL-8: a no-LLM, rule-based baseline against the loop (Mon Nov 2, 2026, SLT with ET alongside)

Cost: **$0**, no live call. Code: `baselines/rulefix.py`, driver `eval/run_rulefix.py`, tests `tests/test_rulefix.py`.
Raw outputs: `runs_rulefix/` (one JSON per case, `score.json`, `PREREG.md`, `PREREG.sha256`, `prereg_log.jsonl`).
Loop numbers are read, unchanged, from `runs_g5/score.json` and `runs_g6/score.json`.

## 0. Answer first

- **Preregistered comparison (G4/G5 cases): MIXED. It is not a PASS.**
  - Hard cases, sign right: loop **11/12**, rules **6/12** (4 hard cases measured once, counted x3). d_hard = **+5**, so the loop wins by more than the 3 required.
  - Clean false alarms: loop **1/12**, rules **0/12**. d_fa = **+1**, so the loop has **more** false alarms, and the second PASS clause ("no more clean false alarms") fails.
  - PASS needed d_hard >= 3 **and** d_fa <= 0. The first holds, the second does not. It is not a tie either (|d_hard| = 5).
- **Where the loop beats the rules (counts, 4 hard cases):** freight (a cancellation: the loop measured the right negative sign, the rules measured 0) and pump (a look-ahead feature: the loop +16 pp, the rules 0). On assay both get the sign, but the rules measure +10.8 pp against a reference of +29.9 pp.
- **Where the rules match or beat the loop:** the 4 clean G4/G5 cases (0 false alarms against the loop's 1/12), the textbook case (both reproduce ESL), and the real civil-war case. The rules measured +0.296 PR-AUC against the published +0.36 (within the preregistered 0.15, 3/3 seed CIs contain 0.36). The loop measured +0.231 / +0.203 / +0.203 and reproduced it in 1 of 3 repeats.
- **Caveat that matters:** the rule author had read every `train.py`, and the rules match code idioms of this benchmark. This favours the rules. It also means the rule results do not generalise beyond what the library recognises.

## 1. The rule library (frozen in `runs_rulefix/PREREG.md`, spec sha256 `8be1b7e5…`)

Five standard leakage remedies. Each has a detector (static look at `train.py`, a label-free dry run of the claim's own split, column statistics of `data.csv`) and a remedy (a source rewrite of `train.py`). Every rule whose detector fires is applied blindly. No model, no scoring, no look at results.

| Rule | Detector (fires when) | Remedy | Factor |
|---|---|---|---|
| R1 random hold-out rescore | the split function `tr, te = f(df, seed)` scores rows of which >= 50% are also training rows (dry run) | stratified random 25% hold-out | A |
| R2 refit inside folds | a top-level function builds a scaler / PCA / selector outside any Pipeline, calls `.fit`/`.fit_transform`, and every call to it passes un-sliced arguments | `scope`: fit on the training rows of the claim's own split, transform all rows. `hoist`: move a selector that sits before a CV loop inside the loop | B |
| R3 group-aware split | an integer column that `feats(df)` leaves out, not time-named, 3 <= nunique <= n/2 (most distinct values wins), and > 5% of scored rows share its value with a training row | GroupShuffleSplit, test 25%, on that column | A |
| R4 temporal split | a numeric column that `feats(df)` leaves out, name matches `year\|date\|time\|month\|week\|period`, nunique >= 5, and the split is not already ordered by it | earliest 75% train, latest 25% test | A |
| R5 drop duplicates | exact duplicate rows in `data.csv` | `drop_duplicates()` first thing in `claimed_eval` | A |

- **Factorial layout.** fix_A = fired rules among {R1, R3, R4, R5}; fix_B = R2; fix_both = all fired rules. Same sandbox (`sandbox/executor.run_factorial`), seeds 42/43/44, n_boot = 1000, **unpaired bootstrap**, and the same sign rule (`g4.case_sign`) as the loop. Verdict INFLATED iff sign is `+`.
- **Precedence** when several split rules fire: R4 > R3 > R1 (one splitter can exist).
- **Not in the library, so never fixed:** target encoding, label-conditioned imputation, look-ahead features, proxy features, any `feature`-kind change, tuning-on-all-rows.

## 2. Preregistration

- `PREREG.md` written **2026-11-02 02:49:20Z = 08:19:20 SLT / 2026-11-01 21:49:20 ET (EST)**, before any rule measurement on any benchmark case. sha256 `b10c5b88ad50525a8a643833017ed494b7ec5e2fe7dcede68970d90a6c3a3fd2`.
- It freezes: the rule spec and its hash; `baselines/rulefix.py` sha256 `4fbcc87e…` and `eval/run_rulefix.py` sha256 `2f987221…`; the sha256 of the two read-only loop score files; the agent-view hashes of every case; the comparison rule; and **which rules the detectors would fire per case**.
- The run stage refuses to start if either source or the spec hash differs from `PREREG.md` (tested). The first measurement landed at 08:20:17 SLT and the last at 08:44:16 SLT. Both sources still hash to the preregistered values after the runs.
- Rule development used scratch random data in tests only. No benchmark case was executed under the rules before the file existed.

## 3. Which rules fired (label-free; this table equals the one recorded in `PREREG.md` before measurement)

| Case | Group | Fired | Note |
|---|---|---|---|
| g4_freight_delay | hard | R3 | `c_318a2b` (520 values), 98% of scored rows share a carrier with training |
| g4_pump_inspection | hard | R3, R2 | R3 on `c_24a94d` (120 pumps); R2 scope on `select` (SelectKBest) |
| g4_crop_irrigation | hard | R2 | scope on `prepare` (StandardScaler, PCA) |
| g4_assay_replicates | hard | R3 | `c_2cd377` (700 compounds), 95% shared |
| clean_control, clean_group_correct, clean_wine_correct, g4_visit_history_clean | clean | none | the group-clean cases have an id column, but the claim's split is already group-pure (0% overlap) |
| civilwar_apparent | real | R1, R4 | R4 in force (precedence), time column `year` |
| esl_selection | textbook | R2 (hoist) | selector moved inside each CV fold |
| civilwar_temporal_clean, esl_selection_clean | real/textbook clean | none | already temporal / already inside the folds |
| leak_group, leak_proxy, leak_temporal | supplementary | none | |
| leak_prescale | supplementary | R2 (scope) | |

Totals over the 16 cases: R1 x1, R2 x4, R3 x3, R4 x1, **R5 x0** (none of the 16 datasets has a duplicate row, so R5 was not exercised on benchmark data; it is unit-tested on scratch data).

## 4. Results, G4/G5 synthetic cases (SYNTHETIC)

- **Inflation** = claimed (orig) minus fix_both, mean over seeds, in accuracy points. 95% CIs per seed are from the unpaired bootstrap (n_boot = 1000).
- **Truth** comes from `runs_g5/score.json['truth']` (builder reference patches, unchanged).
- **Loop** columns give the sign per repeat r1/r2/r3 and the mean inflation, from `runs_g5`.

| Case | Truth (ref both) | Rules: sign, verdict | Rules: inflation, CI per seed (42/43/44) | Rules n scored (orig/fix) | Loop r1/r2/r3 | Loop inflation |
|---|---|---|---|---|---|---|
| freight | − (−10.4) | **0, NOT INFLATED: wrong sign** | −0.3 pp; [−8.2,+1.2] [−3.6,+5.7] [−2.8,+6.9] | 731 / 695 (seed 42) | − − − (3/3 right) | −5.5 pp |
| pump | + (+16.0, B) | **0, NOT INFLATED: wrong sign** | +0.2 pp; [−1.5,+4.9] [−4.3,+1.7] [−3.1,+3.2] | 750 / 750 | + + + (3/3 right) | +15.4 / +16.0 / +16.0 |
| crop | 0 (−0.7) | 0, NOT INFLATED: right | −0.3 pp; [−5.1,+3.9] [−4.0,+5.1] [−5.3,+4.1] | 800 / 800 | INCONCLUSIVE, 0, 0 (2/3 right) | −0.7 pp |
| assay | + (+29.9, AxB) | + , INFLATED: right sign | **+10.8 pp**; [+5.5,+13.9] [+7.6,+15.6] [+7.2,+15.0] | 525 / 525 | + + + (3/3 right) | +29.9 pp |
| clean_control | 0 | 0 (no rule fired) | 0.0 pp; spans 0 | 450 / 450 | 0 0 0 | +0.4 / +0.8 / +0.8 |
| clean_group_correct | 0 | 0 (no rule fired) | 0.0 pp; spans 0 | 200 / 200 | 0 0 0 | +2.8 |
| clean_wine_correct | 0 | 0 (no rule fired) | 0.0 pp; spans 0 | 45 / 45 | 0, **+ (false alarm)**, 0 | +4.4 / **+39.3** / +4.1 |
| g4_visit_history_clean | 0 | 0 (no rule fired) | 0.0 pp; spans 0 | 573 / 573 | 0 0 0 | +3.7 / +2.9 / +2.2 |

Rules on the clean cases are exactly 0.0: no rule fires, so fix_both is the claim's own code and the same predictions come back.

### Factors (rules), pp
- assay: A (R3) +10.8, B 0.0, interaction 0.0.
- pump: A (R3) +0.2, B (R2) 0.0.
- crop: B (R2) −0.3.
- freight: A (R3) −0.3.

## 5. Results, real and textbook cases (reported, not part of the preregistered PASS)

Loop = `runs_g6` (3 repeats). The memorisation probe found Spark recognised both sources (EVAL-6, CONTAMINATED). The rules have no such risk.

| Case (provenance) | Published | Rules | Loop r1 / r2 / r3 |
|---|---|---|---|
| civilwar_apparent (REAL-PINNED, PR-AUC) | +0.36 (0.43 → 0.07) | **+0.296**, sign + 3/3 seeds, CI [.200,.401] [.185,.381] [.179,.373]; controlled .088 / .089 / .089 on 1785 rows (claimed .395 / .384 / .373 on 7140). Reproduces: yes (\|Δ\| = 0.064 ≤ 0.15). Published value inside 3/3 seed CIs | +0.231 / +0.203 / +0.203; reproduces 1/3 |
| esl_selection (TEXTBOOK, accuracy) | +0.47 (0.97 → 0.50) | **+43.3 pp**, sign + 3/3, CI [32,60] [26,54] [30,58]; controlled .54 / .58 / .56 = the builder reference exactly. Reproduces: yes (\|Δ\| = 0.037) | +52.7 / +54.9 / +43.3 pp; reproduces 3/3 |
| civilwar_temporal_clean (REAL-PINNED) | 0 | 0 (no rule fired), no false alarm | INCONCLUSIVE, INCONCLUSIVE, 0 |
| esl_selection_clean (TEXTBOOK) | 0 | 0 (no rule fired), no false alarm | 0 0 0 |

- The rules reached the right civil-war fix **because the column is named `year`**, so R4 could fire. R4 would be silent on the same data with hashed names (see section 9).
- The ESL hoist rule gives the same predictions as the hand-written correct protocol (tested bit for bit on scratch data).

## 6. Supplementary corpus leak cases (SYNTHETIC; no loop run, no preregistered truth beyond "leaky by construction" in `eval/ground_truth.json`)

| Case | Leak by construction | Rules |
|---|---|---|
| leak_prescale | scaling and selection fit on full data | R2 scope fired: sign + (2 of 3 seeds), +17.3 pp, n = 75. Partial: a second `StandardScaler` fit inside `claimed_eval` is not in a function the rule can wrap |
| leak_group | site id used as a feature, sites repeat across the split | none fired; 0.0 pp. **Missed** |
| leak_proxy | proxy feature carries the label | none fired; 0.0 pp. **Missed** |
| leak_temporal | random split on drifting data | none fired (hashed columns, no time name); 0.0 pp. **Missed** |

The rules caught 1 of these 4 leaks (counts, no preregistered pass number).

## 7. Where the rules over-correct and under-correct (plainly)

**Under-correct (the main failure).**
- **freight.** The planted error has two parts: target-mean encoding on all rows, and test-fold missing values filled with 0 instead of the training median. They partly cancel. The truth is that the claim is **understated** (−10.4 pp). No rule covers either part, and R3 changes the question. The rules measured 0 and said NOT INFLATED. The loop measured the right negative sign in 3/3.
- **pump.** The inflation is a look-ahead lag feature (`shift(-1)`), which is not in the library. R3 and R2 fired and changed nothing measurable (+0.2 pp). Truth +16.0 pp. The rules missed it. The loop got +15.4 to +16.0.
- **assay.** The rules fixed the split (+10.8 pp) and missed the label-conditioned imputation and its interaction. They measured about a third of the reference +29.9 pp. The sign is right.
- **leak_group, leak_proxy, leak_temporal:** silent.
- **Civil war:** the second published flaw (imputation using the outcome) is baked into the data and untouched, for both tools.

**Over-correct.**
- **No over-correction was measured:** 0 false alarms on 8 clean cases (4 synthetic, 4 real/textbook), and no clean case had a rule fire. This is a property of the detectors, which fire only on observed overlap or a visible idiom. It is not evidence that the remedies are safe to apply blindly.
- **Applying R3 to freight and pump** asks a different question from the claim's own. The excerpts say "existing carriers" and "the existing fleet", so a group split is a protocol the stated use does not want. The measured effect was about 0, so there was no alarm, but nothing in the rules stops this on other data.
- **R4 over R1 on civil war** is a precedence choice. It matched the published fix here.
- `clean_group_correct` and `g4_visit_history_clean` each have an id column. The dry-run overlap check is what keeps R3 from firing there, because their claimed split is already group-pure. What the rules would do with detectors based on column statistics alone was not run (UNVERIFIED).

## 8. Does the loop (Spark) beat the rules?

- **By the preregistered rule: no PASS, MIXED.**
  - The loop wins on hard-case signs: 11/12 against 6/12. Case by case it is better on 2 of the 4 (freight, pump); both are right on crop and assay.
  - It does not win on false alarms: 1/12 against 0/12.
- **The one loop false alarm** is clean_wine_correct r2 (+39.3 pp). It was a G5 plan that G6's tightened guard rejects in the offline replay (EVAL-6 section 3). No new loop run exists on those cases, so the preregistered comparison keeps the G5 count.
- **What this supports.**
  - On four synthetic hard cases built so that a standard fix is not enough, execution of a model-written, guarded fix gets the sign where a fixed rule library does not. That is freight and pump, and the size on assay.
  - On textbook-shaped cases (ESL selection, civil-war apparent error), a small rule library does as well as or better than the loop. It does so at $0, with zero false alarms, with no contamination risk and with deterministic output.
- **What it does not support.**
  - It does not show the loop beats rules in general. The rules were written by someone who had read the files. The loop's hard-case edge is concentrated in 2 of 4 cases.
  - 4 hard and 4 clean cases are counts. The x3 replication of a deterministic baseline is not independent evidence, and the loop's own repeats were weakly independent (EVAL-5).
  - Cases where the leak is a look-ahead feature, offsetting errors or label-conditioned imputation are where reading and rules fail and where a model-written fix pays. That is a small slice of the benchmark.

## 9. Honest limits and UNVERIFIED

- Rules match code idioms (a top-level split function, a transformer in a top-level function, a selector hoisted out of a CV loop). A claim written differently would not be fixed. This is **detected-not-applied** in the output when the idiom is missing (never triggered on these cases).
- Hashed columns carry no names, so R4 can only fire on civil war. How the rules would do with names on the synthetic cases is **UNVERIFIED** (not run).
- The comparator numbers are from G5 (guard without the justification rules) and G6 (with them). Planner prompts and the guard differ between them, as recorded in EVAL-5/6.
- The sandbox backend is the restricted subprocess one (no Docker). Elapsed times: synthetic cases 6 to 153 s, civil war 399 to 468 s each.
- `PREREG.sha256` covers `PREREG.md` only. `score.json` was recomputed after all runs (`python eval/run_rulefix.py score`).
- Tests: `tests/test_rulefix.py` (23, all offline): detection on every repository case, the hoist rewrite equals the hand-written clean protocol, scope fit uses training rows only, precedence, R5, the prereg refusal.

## 10. Reproduce
```
.venv\Scripts\python eval/run_rulefix.py detect                  # which rules fire, no measurement
.venv\Scripts\python eval/run_rulefix.py prereg --out <new dir>  # refuses to overwrite
.venv\Scripts\python eval/run_rulefix.py run   --out <new dir>   # needs PREREG.md in that dir; ~25 min (civil war dominates)
.venv\Scripts\python eval/run_rulefix.py score --out <new dir>
```
