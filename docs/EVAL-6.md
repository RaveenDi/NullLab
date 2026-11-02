# NullLab EVAL-6: G6, a real published correction and a textbook case (Sun Nov 1, 2026, SLT with ET alongside)

Driver: `g6.py`. Cases: `real/`. Host-only truth: `eval/g6_truth.json`. Builder: `eval/build_g6.py`. Raw outputs: `runs_g6/`.
Tests: `tests/test_g6.py`. Sections 1 to 3 were written **before any G6 live call**; results follow in section 4.

## 1. The cases (provenance and sources)

### 1a. REAL-PINNED: civil-war onset, Muchlinski et al. (2016), reanalysed by Neunhoeffer & Sternberg (2019)
- **Original claim.** Muchlinski, Siroky, He, Kocher (2016), *Political Analysis* 24(1):87-103: a down-sampled random
  forest predicts civil war onset with ROC-AUC 0.91 ("cross-validated", their fn. 7) and offers superior predictive
  power to logistic regression.
- **Published flaw and correction.** Neunhoeffer & Sternberg (2019), "How Cross-Validation Can Go Wrong and What to Do
  About It", *Political Analysis* 27(1):101-106, doi:10.1017/pan.2018.39
  (author PDF https://sebastiansternberg.github.io/pdf/pa_cross_validation.pdf; replication doi:10.7910/DVN/Y9KMJW).
  The reported score is the **apparent error**: the CV-tuned caret model is scored with `predict()` on the same rows it
  was trained on. Their re-analysis (train 1945-1989, test 1990-2000) reports **PR-AUC 0.43 (apparent) vs 0.07 (out of
  sample)**, i.e. a published inflation of **+0.36 PR-AUC** (Sec. 4 and Online Appendix C.2).
  ROC-AUC values appear only in their Figure 1; read off the vector glyphs they are about 0.97 and 0.89 (**UNVERIFIED**,
  ±0.01, not stated in the text). ROC-AUC barely moves, which is why the case is scored on PR-AUC.
- **Data.** `SambnisImp.csv`, Harvard Dataverse doi:10.7910/DVN/KRKWK8 v1.0, file id 2701491,
  md5 `5e570898c1c9335c6eeb6515ec9c8a28` (checked by the builder). 7,140 country-years, 116 onsets; the 90 predictors of
  the re-analysis code (`R/reanalysis.R`) + `year` + `warstds`. Column names are kept (they carry the `year` semantics).
- **Code.** A Python port (sklearn 1.9.1) of the published R procedure: per-class down-sampled bagged trees (30 peace, 90
  war per tree, with replacement; 300 trees instead of 1,000 for runtime), mtry grid (2, 46, 90) tuned by 10-fold
  stratified CV ROC-AUC. The leaky step is `split_rows` returning the same rows for fitting and scoring.
  The docstring does not say this is wrong; the excerpt says the model is meant to forecast unseen country-years.
- **Builder check (offline, before preregistration):** apparent PR-AUC 0.395 / ROC-AUC 0.972 (seed 42); temporal hold-out
  PR-AUC 0.092 / 0.081 / 0.080 and ROC-AUC about 0.90 (seeds 42/43/44). So the port reproduces both published numbers
  to within about 0.04 PR-AUC; the port's own inflation is about +0.31.
- **Clean variant** `civilwar_temporal_clean`: the same pipeline trained on 1945-1989 and scored on 1990-2000
  (the re-analysis's Procedure 6).
- **Not built (time box):** Kapoor & Narayanan (2023, *Patterns*; arXiv:2207.07048, Table A1) document a *second* flaw in
  the same paper: train and test imputed together with `rfImpute` using the outcome (RF AUC reported 0.94, reproduced
  0.95, corrected 0.64). Their raw pre-imputation data is only in CodeOcean capsule doi:10.24433/CO.4899453.v1, which
  returned HTTP 403 to automated download on 2026-11-01, and the Dataverse package holds only the already-imputed file.
  The imputation leak is therefore baked into `SambnisImp.csv` and is **not** corrected by NullLab here.

### 1b. TEXTBOOK: ESL section 7.10.2 ("The Wrong and Right Way to Do Cross-validation")
- Hastie, Tibshirani, Friedman, *The Elements of Statistical Learning*, 2nd ed., 12th printing, pp. 245-247 (PDF via
  https://hastie.su.domains/ElemStatLearn/ , sha256 `8d098d65…`). N = 50 samples in two equal classes, p = 5,000
  standard Gaussian predictors independent of the labels; screen the 100 most label-correlated predictors on **all**
  samples, then 5-fold CV of 1-nearest-neighbour. The book reports an average CV error of **3%** over 50 simulations;
  the true error is **50%**. Published inflation: **+0.47 accuracy**. This is textbook-documented, **not** a published
  reanalysis of a paper.
- Our data is ONE draw (seed 7) of that setting. Builder check: wrong-way accuracy 1.00 / 0.98 / 1.00, right-way
  0.54 / 0.58 / 0.56 (seeds 42/43/44). Screening uses `SelectKBest(f_classif)`, which ranks exactly like |correlation|
  for two classes.
- Clean variant `esl_selection_clean`: the screen re-run inside each fold.

### 1c. Contamination risk
The civil-war case is a well-known paper with recognisable column names (`warstds`, `agexp`, ...), and ESL 7.10.2 is a
famous example. A recognised source could let Spark answer from memory. `g6.py probe` runs the existing probe
(`agent/extract.memorization_probe`, excerpt only) and the same question over the full agent view, before the runs.

**Probe result (run after preregistration, before the repeats; `runs_g6/probe.json`): CONTAMINATED.**
- civilwar_apparent: excerpt only → "Muchlinski et al. (2016) civil war onset replication data"; full view → names the
  paper's full title. **FAIL** on both probes.
- esl_selection: excerpt only → "UNKNOWN" (pass); full view → "The Elements of Statistical Learning". **FAIL**.
- So Spark recognises both sources. It may know the published critiques too. Any agreement between the loop and the
  published number on these cases cannot, by itself, separate "found by experiment" from "recalled". The measured
  numbers come from the sandbox, not from the model, but the model's choice of *what to fix* may be recalled.
  The project's de-identification rule ("if Spark names the source, replace the hero") is triggered; no de-identified variant was built in
  this time box (it would need a new preregistration).

## 2. Harness changes (before any live call)
- **Score metric.** `train.METRIC` (module level, so no fix can edit it) selects the metric. `sandbox/run_factorial.py`
  keeps float scores for a score metric; `sandbox/factorial_stats.score_factorial_stats` computes PR-AUC (sklearn
  `average_precision_score`) and ROC-AUC with the same UNPAIRED bootstrap (each config resampled independently; a
  replicate with one class in some config is dropped and counted). Accuracy cases are unchanged (tested).
- **Wide data.** `agent/factorial.agent_view` clips a data-head line longer than 10,000 characters (only the 5,001-column
  ESL case); every earlier case's view is byte-identical (tested).
- **Call cap.** `agent/llm.py`: G6 log `runs/live_calls_g6.jsonl`; the cap of 190 counts G5 + G6 calls.

## 3. Guard tightening (design written before running; `agent/fidelity.check_justification`)
- **FEATURE-REASON.** A `feature` fix that names a data column the original step did not name must cite a line copied
  verbatim (whitespace-normalised) from train.py or the excerpt (`X_code_line` or `edits[X].evidence`) that contains
  that column name. A column seen only in the data head cannot be justified, so it cannot be dropped. This checks that
  a reason exists in the files, not that the reason is correct.
- **SPLIT-USE.** A `split` fix that introduces an ordered hold-out (sort, `shuffle=False`, positional slice, comparison on
  a time-like column, `TimeSeriesSplit`, or a random splitter replaced by a deterministic range) is accepted only if the
  excerpt states a temporal intended use (forecast, future, later years, prospective, ...). Random and group hold-outs
  are not gated.
- **Feats inline.** A verbatim inline of `feats`' own comprehension is no longer a FEATURES violation (the G5 crop r1 and
  clean_control r1 false rejections).
- **Planner prompt.** `agent/factorial_g6.py` = the G5 prompt + one paragraph stating these rules and that drops are in
  points of `METRIC`. A design change made before any G6 call.
- **Offline replay** (`python g6.py replay`, `runs_g6/replay.json`) of every executed G5 plan:
  - all 11 hard-case plans and the 3 visit-history-clean plans are still **ACCEPTED**;
  - the G5 false alarm (clean_wine_correct r2) is now **REJECTED** twice: FEATURE-REASON (`c_55565a` is named nowhere
    in train.py or the excerpt) and SPLIT-USE (deterministic last-25% hold-out without a temporal claim);
  - 6 further clean-case plans that dropped a named column without a cited reason (clean_group r1-r3, clean_wine r1/r3,
    clean_control r2/r3) are now rejected. They had not caused false alarms, but they are the same unjustified class.
  - The structured G5 fixtures (GOOD_SPIKE, GOOD_PUMP) are still accepted.
- **Tests:** `tests/test_g6.py` (15) + `tests/test_fidelity.py` (17) pass.

## 4. Results (preregistered 2026-11-01 08:24:55Z = 13:54:55 SLT / 03:24:55 ET; first live call 08:25:47Z)
Rule sha256 `90f6f43d…` (`runs_g6/prereg_log.jsonl`, 37 records: rule, source hashes, prompts, 4 agent views, then
every B3 answer, planner plan and retry hashed before execution). Score: `runs_g6/score.json` (`python g6.py score`).
Builder reference (offline, before preregistration): `runs_g6/ref.json`.

### Acceptance (preregistered): **FAIL** (clause a)
| Clause | Measured | Pass |
|---|---|---|
| (a) civil war: loop reproduces the published correction in ≥ 2/3 repeats | **1/3** (sign right 3/3; magnitude off by > 0.15 in r2, r3) | **no** |
| (b) ESL: loop reproduces in ≥ 2/3 repeats | **3/3** | yes |
| (c) 0 loop false alarms on 6 clean case-repeats | **0/6** (2 INCONCLUSIVE, civil-war clean r1/r2) | yes |
| (reported) B3 gets it (leak, sign, within 0.15 of published) | civil war **3/3**, ESL **3/3** | |
| (reported) B3 false alarms on clean | **3/6** (civil-war clean 3/3, ESL clean 0/3) | |
| (reported) retries | 6 (r1: all 4 cases; r2: 2 clean cases) | |

### Per run: civil war (metric PR-AUC; published 0.43 → 0.07, inflation **+0.36**)
Inflation = claimed − controlled (fix_both); 95% CI per seed 42/43/44 from the UNPAIRED bootstrap (n_boot = 1000).

| Run | Claimed (per seed) | Controlled | Mean inflation | CI per seed | Published 0.36 inside CI | Sign | Reproduces? |
|---|---|---|---|---|---|---|---|
| builder ref (temporal split = published fix) | .395 .384 .373 | .092 .081 .080 | **+0.300** | [.19,.40] [.21,.40] [.20,.39] | 3/3 seeds | + + + | (reference) |
| loop r1 | .395 .384 .373 | .112 .269 .081 | +0.231 | [.14,.40] [−.11,.27] [.19,.39] | 2/3 | + 0 + | yes (|Δ| 0.129) |
| loop r2 | same | .174 .293 .077 | +0.203 | [.05,.37] [−.12,.26] [.19,.39] | 2/3 | + 0 + | **no** (|Δ| 0.157) |
| loop r3 | same | .174 .293 .077 | +0.203 | identical to r2 | 2/3 | + 0 + | **no** |
| B3 r1 / r2 / r3 | n/a | n/a | predicted +24 / +29 / +26 points | n/a | n/a | + | yes ×3 |

- **What the loop did.** Fix A (kind `split`) every time replaced the in-sample scoring with a **random stratified 80/20
  hold-out** of country-years, not the temporal hold-out the excerpt's "forecast" use implies and the reanalysis used.
  Fix B changed the mtry tuning (r1: fixed mtry to the first grid value, which removes tuning; r2/r3: `shuffle=False`
  tuning folds). The random hold-out has about 23 onsets per test set, so seed 43's CI spans 0; the mean lands at
  0.20 to 0.23 instead of 0.30 (port) / 0.36 (published).
- ROC-AUC alongside (claimed → controlled): about 0.97 → 0.89 to 0.95, matching the reanalysis' figure (0.97 → 0.89,
  digitised, UNVERIFIED).
- The direction is right in 3/3 repeats and the published number lies inside 2 of 3 seed CIs in every repeat; the
  preregistered magnitude tolerance (±0.15) was met in 1/3.

### Per run: ESL (metric accuracy; published 0.97 → 0.50, inflation **+0.47**)
| Run | Claimed | Controlled | Mean inflation | CI per seed | Published inside CI | Reproduces? |
|---|---|---|---|---|---|---|
| builder ref | 1.00 .98 1.00 | .54 .58 .56 | +0.433 | [.32,.60] [.26,.54] [.30,.58] | 3/3 | (reference) |
| loop r1 | same | .40 .40 .60 | +0.527 | [.30,.90] [.28,.88] [.10,.70] | 3/3 | yes |
| loop r2 | same | .40 .47 .47 | +0.549 | [.33,.80] [.25,.80] [.27,.73] | 3/3 | yes |
| loop r3 | same | .52 .56 .60 | +0.433 | [.28,.68] [.22,.60] [.20,.60] | 3/3 | yes |
| B3 r1-r3 | n/a | n/a | predicted **+47** points ×3 (the book's exact number) | n/a | n/a | yes ×3 |

Fix A (`fit_scope`) moved the screen inside the folds every time; fix B (`split`) changed the CV scheme (no effect).
n = 50, so CIs are about ±0.3.

### Clean variants
| Case | r1 | r2 | r3 | B3 |
|---|---|---|---|---|
| civilwar_temporal_clean | INCONCLUSIVE | INCONCLUSIVE | 0 (0 0 0), +0.003 | leak=true ×3, predicted +13 / +14 / +13.5 |
| esl_selection_clean | 0, 0.000 | 0, −0.060 | 0, +0.047 | leak=false ×3, 0 |

- Civil-war clean r1/r2: the planner tried to drop `army85`, `autch98`, `demch98`, `polch98` as "future-coded" (values
  dated 1985/1998 used for 1945-1989). The new FEATURE-REASON rule rejected it twice (no verbatim line names those
  columns) → INCONCLUSIVE, not a false alarm. B3 made the same argument and called the clean pipeline inflated (3/3).
  Whether those variables really leak is **UNVERIFIED**; the guard blocked the experiment that would have tested it.

### Run-to-run variance (SD of the loop's mean inflation across repeats)
civil war 0.016 (0.231 / 0.203 / 0.203; r2 and r3 identical plans at temperature 0), ESL 0.062 (0.527 / 0.549 /
0.433), ESL clean 0.054. B3: civil war 24 / 29 / 26 points, ESL 47 / 47 / 47.

### Memorisation probe: **contaminated** (section 1c). Spark names Muchlinski et al. (2016) from the excerpt alone and
ESL from the full agent view. B3 predicting exactly +47 points on ESL is consistent with recall.

### Calls and spend
34 live calls in `runs/live_calls_g6.jsonl` (12 B3, 12 planner, 6 retries, 4 probe; 86 of the 190 G5+G6 cap).
Meta spend $17.82 → **$20.66 (+$2.84** at per-call estimates), under the $3.50 G6 budget and the $30 cap.
Tests: 77 passed (section 6).

## 5. Honest verdict
- **Does NullLab reproduce a published correction?** Partly. On the real case it finds the documented flaw (in-sample
  scoring) in 3/3 repeats, executes a guarded fix and measures a positive inflation with the published direction, and
  the published +0.36 lies inside 2 of 3 seed CIs. But its fix was a random hold-out, not the temporal hold-out the
  claim's use requires, so it under-measured (+0.20 to +0.23) and met the preregistered magnitude tolerance in only 1/3
  repeats. **The preregistered G6 acceptance FAILS on clause (a).** On the textbook case it reproduces 3/3.
- **Execution vs reading on these cases: no win.** B3 (reading only) named the right flaw and a magnitude within 0.15 of
  the published number in 6/6 leaky runs, better than the loop's 4/6. Both sources are recognised by Spark, so these
  two cases cannot show that execution beats recall. Where the loop did better: B3 false-alarmed on the clean civil-war
  pipeline 3/3; the loop never false-alarmed (0/6), though 2 of those were INCONCLUSIVE.
- **What G6 does support:** the harness runs a real published pipeline on pinned public data and reproduces the
  published numbers in the builder reference (apparent 0.37 to 0.40 vs 0.43; out of sample 0.08 to 0.09 vs 0.07); the
  tightened guard removes the G5 false-alarm class without rejecting any G5 hard-case patch.
- **Gaps:** contamination (both sources recognised; no de-identified variant); the SPLIT-USE rule gates ordered splits
  but does not *require* a temporal split when the claim is a forecast; a fix that hard-codes a tuning parameter (r1)
  passed as `split`; 300 trees vs 1,000 in the port; PR-AUC via sklearn average precision vs the reanalysis' aucPRp;
  the Kapoor & Narayanan imputation correction (AUC 0.95 → 0.64) is not reproduced (data not downloadable).

## 6. Tests
`tests/test_g6.py` 15 tests (justification rules, feats inline, wine r2 now rejected, all G5 hard-case patches still
accepted, score-metric bootstrap, float scores through the sandbox, sandbox blocks `eval/g6_truth.json`, real-case agent
views isolated, earlier agent views unchanged) + `tests/test_fidelity.py` 17. Full suite: **77 passed** (2026-11-02).
