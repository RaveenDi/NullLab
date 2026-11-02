# G7 preregistration (written BEFORE any G7 live call; sha256 of this text is logged in prereg_log.jsonl)

Date written: 2026-11-02 02:43:35Z (SLT 2026-11-02 08:13). Phase owner: builder A. Nothing below is tuned after seeing results.

## Question
Does NullLab's loop (plan, guarded structured edits, sandbox run) still find and measure a published evaluation flaw
when the source paper cannot be recalled from the material (names, columns, domain all changed)? And does executing beat
a single reading prompt (B3)?

## Cases (same rows and numbers as the G6 civil-war case, REAL-PINNED, disguised)
- civilwar_disguised (leaky): columns f01..f90, target, epoch (= year - 1944). train.py scores the model on the rows it
  was trained on (split_rows returns the same rows for fit and score). Excerpt: a FORECASTING claim in another domain
  ('supplier-failure onset in a regional supply network', disguise version 1; versions 2, 3 are rebuilt wordings).
- civilwar_disguised_clean: the same pipeline, trained on epochs 1-45, scored on epochs 46-56.
- Truth (host only, eval/g7_truth.json): published inflation +0.36 PR-AUC (Neunhoeffer and Sternberg 2019:
  0.43 apparent vs 0.07 temporal hold-out). The builder reference port measures about +0.30 (G6 ref.json).

## Contamination probe (live, before the runs; protocol fixed here)
Per disguise version v, with the model used for the runs: (P1) full agent view, "name the dataset/paper/repository if you
recognise it, else UNKNOWN"; (P2) "what real-world domain do the numeric columns measure? one line". The version PASSES iff
P1 answer contains UNKNOWN and neither answer contains any of: war, conflict, civil, countr, nation, polit, sambanis,
muchlinski, regime, democr, cold war, hegre, fearon. If it fails, rebuild with version v+1 (wording changed, same data),
up to version 3. If version 3 still fails, the case is labelled DEV-ONLY in EVAL-7.md and the failure stated.

## Rules
- SPLIT-USE-REQUIRED (agent/factorial_g7.check_split_required): if the excerpt states a forecasting / next-period use
  (words: forecast, future, next period, next-period, next epoch, later period, later epoch, later year, prospective, temporal, chronolog, ahead, upcoming, unseen period), every 'split' fix must hold rows out by time (comparison with a time-like column, sort-by-time +
  slice, TimeSeriesSplit), and unless train.py already does so, at least one 'split' fix must. Otherwise the plan is
  REJECTED, one retry carrying the rejection text, then INCONCLUSIVE (never FALSIFIED). The planner prompt is the
  unchanged G6 prompt (the rule is NOT announced in the prompt).
- Schema: the planner JSON is validated (validate_plan) before the fidelity guard; one schema retry.
- Guards from G5/G6 unchanged (static fidelity, FEATURE-REASON, SPLIT-USE, SAMPLE SIZE).
- Measurement as G6: 4 configs x seeds 42/43/44, n_boot=1000, UNPAIRED bootstrap, metric PR-AUC; measured inflation =
  claimed (orig) minus controlled (fix_both), mean over seeds; sign per seed from the 95 percent CI; repeat sign = category of >= 2 of 3 seeds.

## Runs
5 repeats on each of the two cases, model muse-spark-1.3-contributor if the API accepts it (modelcheck), else muse-spark-1.3, temperature 0.7; per repeat B3 x 2 (single reading prompt,
baselines FACTORIAL_SYSTEM text) and the loop planner x 2 (hashed before execution), then the guarded loop.

## Hypotheses (stated before data)
H1. Without SPLIT-USE-REQUIRED the loop would repeat the G6 behaviour (random hold-out, magnitude under-estimated);
    with it, the accepted fix is temporal, so the measured inflation approaches the builder reference (about +0.30).
H2. The loop does not false-alarm on the clean pipeline (INCONCLUSIVE possible).
H3. B3 (reading only) still names the flaw and a magnitude near +0.36 on the leaky case; if so the disguise did not
    remove what B3 needs and the loop cannot claim a win from this case. B3 false alarms on the clean case are possible (G6: 3/3).

## PASS (preregistered; computed by `score`)
PASS iff all of:
 (a) direction right (repeat sign '+') on the leaky case in >= 4 of 5 repeats,
 (b) 0 false alarms (repeat sign '+') on the clean case over 5 repeats (INCONCLUSIVE is not a false alarm),
 (c) measured inflation within 0.15 of +0.36 (|mean inflation - 0.36| <= 0.15) on >= 3 of 5 leaky repeats.
Reported alongside (not acceptance): B3 gets-it / false alarms, retries, INCONCLUSIVE counts, CIs, spend, probe results.
B3 GETS IT iff leak == true AND predicted fix_both drop >= +2 points AND |drop/100 - 0.36| <= 0.15.
B3 false alarm on clean iff leak == true.
Budget: stop at an estimated USD 3.30 for this task (call estimates summed from runs_g7/live_calls_g7.jsonl).
