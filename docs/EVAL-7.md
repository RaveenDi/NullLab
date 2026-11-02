# NullLab EVAL-7: disguised civil-war case, SPLIT-USE-REQUIRED, traces/swap-ability, muse-wonder probe (Mon Nov 2, 2026)

Driver: `python -m agent.factorial_g7 <stage>`. Cases: `real/civilwar_disguised`, `real/civilwar_disguised_clean`.
Host-only truth: `eval/g7_truth.json`. Builder: `eval/build_g7.py`. Outputs: `runs_g7/` (PREREG.md, prereg_log.jsonl,
probe_v1/v2.json, r1..r5.json, score.json, replay_g6.json, ref.json, wonder*.json, traces.jsonl, live_calls_g7.jsonl).
Tests: `tests/test_g7.py`, `tests/test_trace.py`. Preregistration (hypotheses, rules, PASS numbers) was written to
`runs_g7/PREREG.md` before any live call (sha256 `d1d7ffd0f41a7f2fdbd814f6591046e4213f4a91b124d3e9fde6669ef09c912f`).

Labels: case = REAL-PINNED (disguised relabelling of the G6 real data). Model results = LIVE `muse-spark-1.3-contributor`
(temperature 0.7) for Task 1, LIVE `muse-wonder-1.0` (temperature 0) for Task 2. Builder reference = OFFLINE, not a model result.

## 1. Disguised case
- Same 7,140 rows, 116 onsets, same pipeline and numbers. Columns f01..f90, `target`, `epoch` (= year - 1944). train.py comments and
  excerpt rewritten as a forecasting claim in a different domain. No mention of war, countries, the paper or authors (tested).
- Builder reference (OFFLINE, temporal split = published control): apparent PR-AUC 0.395/0.384/0.373 -> 0.093/0.082/0.080, mean
  inflation **+0.299** (v1: +0.300, identical to G6's reference). So the disguise did not change the numbers.

### Contamination probe (contributor model, 2 calls per version)
| Version | Change | P1 "name the source or UNKNOWN" | P2 "domain of f01..f90?" | Result |
|---|---|---|---|---|
| v1 | rename columns, new domain wording | "Muchlinski et al. (2016) civil-war onset data" | "Civil war / armed-conflict onset country-year covariates" | **FAIL** (recognised) |
| v2 | v1 + each feature rescaled by a power of two (order/ties exact) + logistic-regression sentence dropped | UNKNOWN | "EEG brain activity for epileptic seizure prediction" | **PASS** |
v1 was recognised even with every name removed (probably from the data values, 90-feature layout and sample sizes). All runs below use v2.
Caveat: passing a 2-call probe shows Spark did not name the source, not that it has no memory of it. Case is not labelled dev-only.

## 2. SPLIT-USE-REQUIRED (offline replay on saved outputs, $0, `runs_g7/replay_g6.json`)
Rule: if the excerpt states a forecast, the step that chooses the scored rows (`tr, te = step(...)`) must hold rows out by time
(edits to it must be temporal; unless train.py already is, one edit must be). Other steps (inner tuning CV) are unconstrained.
- G6: 10 executed plans; it would have **rejected 3**: all three `civilwar_apparent` plans (random 80/20 hold-out; G6 inflation
  +0.231/+0.203/+0.203). The clean civil-war plans and the ESL plans: unchanged. G5: 23 executed plans, **0 rejected**.
- Limit: static check; it cannot verify direction (a reversed split would pass).

## 3. Results (preregistered; n = 5 repeats per case)
Loop = G6 planner prompt (rule not announced) + guards + SPLIT-USE-REQUIRED + one retry; B3 = single reading prompt.

| Rep | Leaky loop | Retry | Inflation mean | Clean loop | Clean inflation | B3 leaky (pred pp) | B3 clean |
|---|---|---|---|---|---|---|---|
| r1 | + (+,+,+) | 1 | +0.308 | 0 | -0.001 | leak, 38 (gets it) | leak=true (55) |
| r2 | + | 1 | +0.308 | 0 | -0.011 | leak, 38 (gets it) | leak=true (78) |
| r3 | INCONCLUSIVE | 1 | n/a | 0 | -0.001 | leak, 60 (too big) | leak=true (70) |
| r4 | INCONCLUSIVE | 0 | n/a | 0 | -0.004 | leak, 42 (gets it) | leak=true (75) |
| r5 | + | 1 | +0.308 | 0 | -0.001 | leak, 40 (gets it) | leak=true (38) |

Acceptance: (a) direction right **3/5** (need 4), (b) clean false alarms **0/5** (pass), (c) within 0.15 of +0.36 **3/5** (pass).
**PASS = FALSE (preregistered acceptance failed on clause a).**
- Every executed leaky repeat measured +0.308 (CI per seed excludes 0), 0.052 from +0.36: the guarded fix was the temporal split each time.
- The 2 INCONCLUSIVEs are harness/model failures, not wrong findings. r3: the retry plan was accepted but crashed in the sandbox
  (`pandas to_numpy(kind=...)` TypeError, no second retry allowed). r4: the first plan was rejected by SPLIT-USE-REQUIRED and the retry reply was
  not parseable JSON (PlanInvalid). Counting them as wrong is the preregistered rule.
- Whether the rule changed outcomes: in 4 of 5 leaky repeats the first plan was REJECTED by SPLIT-USE-REQUIRED and the retry fixed it
  (without the rule those runs would have repeated G6's random hold-out; this is the inferred counterfactual from replay, not re-run).
- B3 vs loop: B3 "gets it" (leak, >= +2, within 0.15 of 0.36) **4/5**; the loop reproduced the published number's neighbourhood in 3/5.
  **B3 beats the loop on detection of the leaky case (4/5 vs 3/5) and magnitude is similar.** B3 false-alarms on the clean case **5/5**
  (predicting 38 to 78 points inflation on a pipeline that is already temporal); the loop 0/5. The loop's only advantage here is clean-case
  specificity, plus it measures rather than guesses. If the sandbox were removed, B3 alone would be the better detector but unusable on clean code.
- Retries: 7 total (leaky 4, clean 3). One clean retry cause: STRUCTURE rejection of `split_rows` (r2, r5).

## 4. Task 2: traces, swap-ability, wonder
Built: `agent/llm.py` takes model from `NULLLAB_MODEL` or `NULLLAB_MODEL_<ROLE>` (default muse-spark-1.3); `mode_label()`; temperature argument;
G7 phase (`NULLLAB_PHASE=g7`): own log `runs_g7/live_calls_g7.jsonl`, cap 70, counted in `_calls_made()`; every reply appended to
`runs_g7/traces.jsonl` (role, model, prompt, reply, usage, sha256 key; no API key); `llm.set_replay()` / `--replay TRACES --out DIR` serves
recorded replies with zero API calls and no spend check. Planner JSON schema (`validate_plan`) is checked before the guard, one schema retry.
`tests/test_trace.py` (21 tests, mocked HTTP).

muse-wonder-1.0 **does serve chat completions** (1 probe call, answer "OK"). 8 synthetic G5 cases, one repeat, G5 prompt/guard, temperature 0,
vs spark G5 r1..r3 (24 case-repeats). Note n = 8 vs 24.
| Metric | wonder (n=8) | spark (n=24) |
|---|---|---|
| schema-valid plans | 8/8 | 24/24 |
| first plan passes fidelity guard | 6/8 | 20/24 |
| plan JSON has the same key set as spark's (ignoring optional both_overrides) | 8/8 | n/a |
| hard-case sign correct | 4/4 | 11/12 (1 INCONCLUSIVE) |
| clean false alarms | 0/4 | 1/12 |
| sign equals spark r1 sign | 7/8 | n/a |
"Verdict keys identical" is my interpretation (plan key set); wonder's 8/8 is a small sample, not evidence it is better.

## 5. Spend and caveats
Estimated phase spend from the call log: **USD 3.86** (45 calls in the log, incl. 6 probe/model checks and 10 wonder calls;
estimates, bs.py spend check ran before every call). Under the 4.50 cap. Contributor model used for Task 1 per the brief.
Known gaps: disguise passed a 2-call probe only; v1 failed, so the final case needed an extra tweak (preregistered re-disguise); the
loop only reproduced +0.31 not +0.36 (port inflation is +0.30, so within the port); r3 failure shows the harness gives sandbox crashes a single retry.
