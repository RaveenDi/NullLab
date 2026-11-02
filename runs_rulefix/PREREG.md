# EVAL-8 PREREGISTRATION: rule-based leakage-fix baseline (no LLM, $0)

Written 2026-11-02T02:49:20Z UTC = 2026-11-02 08:19:20 SLT / 2026-11-01 21:49:20 ET, BEFORE any measurement of the rule baseline on any benchmark case. Rule development used synthetic scratch data in tests only; no benchmark case was executed under the rules before this file existed.

## Rule set (frozen)

spec sha256: `8be1b7e5f7137c2778361217df0e7599095fed5c1cdf8a3bb4c3b8b939c40385`

```json
{
 "factor_A": [
  "R1",
  "R3",
  "R4",
  "R5"
 ],
 "factor_B": [
  "R2"
 ],
 "holdout": 0.25,
 "pipe_wrappers": [
  "ColumnTransformer",
  "Pipeline",
  "make_column_transformer",
  "make_pipeline"
 ],
 "rules": {
  "R1": {
   "detector": "claimed_eval calls a top-level split function `tr, te = f(df, seed)`; a label-free dry run of that call returns scoring rows of which >= 50% are also training rows",
   "family": "A",
   "name": "random hold-out rescore",
   "remedy": "replace the split function by a stratified (on TARGET) random hold-out, test_size=0.25, random_state=seed"
  },
  "R2": {
   "detector": "a top-level function F builds a scaler/PCA/selector (class name matches TRANSFORMER_RE) OUTSIDE any Pipeline/make_pipeline/ColumnTransformer, calls .fit/.fit_transform, and every call to F passes un-sliced arguments (no Subscript argument)",
   "family": "B",
   "name": "refit inside folds (scaling / feature selection)",
   "remedy": "mode scope (a split function exists): F's transformers are fit on the training rows of the claim's own split and transform every row; mode hoist (selection before a CV loop): the selector call moves inside the loop and is fit on each fold's training rows; no applicable idiom => reported as detected-not-applied"
  },
  "R3": {
   "detector": "an integer column that feats(df) leaves out of the model (metadata), is not time-named, has 3 <= nunique <= n/2 (the one with most distinct values is chosen), and > 5% of the claim's scored rows share its value with a training row (dry run of the claim's split)",
   "family": "A",
   "name": "group-aware split",
   "remedy": "replace the split function by GroupShuffleSplit(test_size=0.25, random_state=seed) on that column"
  },
  "R4": {
   "detector": "a numeric column that feats(df) leaves out, whose NAME matches year|date|time|month|week|period, nunique >= 5, and the claim's split is not ordered by it (max(train time) > min(test time) in the dry run)",
   "family": "A",
   "name": "temporal split",
   "remedy": "replace the split function by: sort rows by that column (stable), train = earliest 75%, test = latest 25%"
  },
  "R5": {
   "detector": "data.csv has >= 1 exact duplicate row",
   "family": "A",
   "name": "drop duplicate rows",
   "remedy": "df = df.drop_duplicates().reset_index(drop=True) as the first statement of claimed_eval"
  }
 },
 "split_precedence": [
  "R4",
  "R3",
  "R1"
 ],
 "time_name_re": "(year|date|time|month|week|period)",
 "transformer_re": "(Scaler$|^PCA$|^TruncatedSVD$|^SelectKBest$|^SelectPercentile$|^SelectFromModel$|^VarianceThreshold$|^Normalizer$|^PowerTransformer$|^QuantileTransformer$)"
}
```

Factorial layout: fix_A = fired rules of {R1, R3, R4, R5}; fix_B = fired rule R2; fix_both = all fired rules. Rules fire only if their detector fires (label-free), are applied blindly, with no model call. Precedence if several split rules fire: R4 > R3 > R1.

## Frozen sources and read-only inputs (sha256)

- `baselines/rulefix.py`: `4fbcc87ecce623c955012f390836894bd7e40fcbcf6d59390a4156de6c282cd7`
- `eval/run_rulefix.py`: `2f987221a6be28fc9cee9afd85409ef06bb118998ecaa58851d39a9f9c4a7332`
- `runs_g5/score.json`: `e3af92a0e5beb6fe21f0f40dc3a9f0d33531b9b5c736fb53cceb6138ccfd32ce`
- `runs_g6/score.json`: `15a7ad5d13f10f3dc153fb0a3fcf154548e2a3a6abdf16f876e1e787d7a3385c`

## Measurement

4 configs (orig, fix_A, fix_B, fix_both) x seeds (42, 43, 44), n_boot = 1000, UNPAIRED bootstrap, same sandbox (`sandbox/executor.run_factorial`) and statistics (`sandbox/factorial_stats.all_seeds`) as the loop. Metric = `train.METRIC` (PR-AUC for civilwar_*, accuracy otherwise).

## COMPARISON RULE (fixed before any measurement)

```text
COMPARISON RULE (fixed before any measurement)
Unit: a case-repeat, as in EVAL-5. The loop has 3 live repeats per G4/G5 case (runs_g5/score.json), so 12 hard case-repeats
(4 hard cases) and 12 clean case-repeats (4 clean cases). The rule baseline is deterministic, so each case is measured ONCE and its
outcome is counted 3 times (x3) to put it on the loop's denominator. Per-case counts (out of 4 and out of 4) are reported next to
these, and the x3 replication is never presented as independent evidence.
Sign per seed: '+' if the 95% CI of drop_fix_both (orig - fix_both) is entirely > 0, '-' if entirely < 0, '0' if it spans 0;
case sign = the category shared by >= 2 of seeds 42/43/44, else 'mixed' (g4.case_sign). Verdict INFLATED iff sign '+'.
Truth for hard cases = runs_g5/score.json['truth'] (builder reference patches, unchanged). Clean truth = '0'.
Rules hard-correct = 3 x (number of hard cases whose rule sign == truth sign). Rules clean false alarms = 3 x (clean cases with sign '+').
Loop hard-correct and loop clean false alarms are read from runs_g5/score.json (acceptance clauses ii and i).
  d_hard = loop_hard_correct - rules_hard_correct;  d_fa = loop_false_alarms - rules_false_alarms.
PASS (the loop beats the rules) iff d_hard >= 3 AND d_fa <= 0.
RULES BEAT THE LOOP iff d_hard <= -3 AND d_fa >= 0.
Otherwise: TIE if |d_hard| <= 2 and d_fa == 0; else MIXED. A tie is reported as a tie, and MIXED with both numbers.
Reported alongside, NOT part of PASS: the 4 real/textbook cases (civilwar_apparent, civilwar_temporal_clean, esl_selection,
esl_selection_clean) against runs_g6 (3 repeats; the loop was CONTAMINATED there, see EVAL-6), and 4 supplementary corpus
leak cases (leak_group, leak_prescale, leak_proxy, leak_temporal) with no loop run to compare.
```

## Which rules fire (label-free detection, recorded before measurement)

| case | group | rules that fire | detected, not applied |
|---|---|---|---|
| g4_freight_delay | hard | R3 | - |
| g4_pump_inspection | hard | R3, R2 | - |
| g4_crop_irrigation | hard | R2 | - |
| g4_assay_replicates | hard | R3 | - |
| clean_control | clean | none | - |
| clean_group_correct | clean | none | - |
| clean_wine_correct | clean | none | - |
| g4_visit_history_clean | clean | none | - |
| civilwar_apparent | real_leaky | R1, R4 | - |
| esl_selection | real_leaky | R2 | - |
| civilwar_temporal_clean | real_clean | none | - |
| esl_selection_clean | real_clean | none | - |
| leak_group | supp | none | - |
| leak_prescale | supp | R2 | - |
| leak_proxy | supp | none | - |
| leak_temporal | supp | none | - |

## Frozen case files (sha256 of train.py / data.csv / excerpt.md)

- g4_freight_delay: train.py `a0dced72b4b8d3f0`, data.csv `ebf23132b1f98d91`, excerpt.md `a7fab92035493683`
- g4_pump_inspection: train.py `490555376a5bb203`, data.csv `84d7057db729e7d7`, excerpt.md `613fc304823ccee3`
- g4_crop_irrigation: train.py `e970d79c42f35ab7`, data.csv `9f1f96b697ee40e7`, excerpt.md `db65ce9360e9cb92`
- g4_assay_replicates: train.py `fe4f2863b3cd5e6f`, data.csv `9d36f508f66c141f`, excerpt.md `ac1ab58f9c06b641`
- clean_control: train.py `c7af24fe246f0444`, data.csv `541feae3d1a89000`, excerpt.md `1a76722b62ce674f`
- clean_group_correct: train.py `568e26a4769f597c`, data.csv `a9d3d56d7307802d`, excerpt.md `63590174beefa47d`
- clean_wine_correct: train.py `dfee05bec1a014b6`, data.csv `79a75519fb8a330d`, excerpt.md `6a8666a86aa1aa26`
- g4_visit_history_clean: train.py `4b01426b63260eba`, data.csv `996861ab0614a3b7`, excerpt.md `9ad445e6d06400ff`
- civilwar_apparent: train.py `8e5b90ad47db2958`, data.csv `9a8c27ad1c520b3c`, excerpt.md `67882ed6e0e4badf`
- esl_selection: train.py `e78ae10d78817666`, data.csv `0a4c2e2a3c279abe`, excerpt.md `69342720ac41c7bc`
- civilwar_temporal_clean: train.py `cf54a10e1f27d847`, data.csv `9a8c27ad1c520b3c`, excerpt.md `b88e6b6deda0468a`
- esl_selection_clean: train.py `8db1b544746579b7`, data.csv `0a4c2e2a3c279abe`, excerpt.md `37b35a04d7bd3fc6`
- leak_group: train.py `0390b234caefd657`, data.csv `866551f19e3bb556`, excerpt.md `d704804fda59f814`
- leak_prescale: train.py `fa1ac659ce9fd2c4`, data.csv `0b3c13eb8de5393b`, excerpt.md `f9cf52a0f3de7add`
- leak_proxy: train.py `3f1262e5c6080aff`, data.csv `252247264c1d82df`, excerpt.md `3f320642d9682304`
- leak_temporal: train.py `ff8d5309e2530caa`, data.csv `40d15c90a94cc16b`, excerpt.md `746af657775bb85c`

## Honest caveats stated before running
- The rules match code idioms of this benchmark; their author had read every train.py. The baseline is optimistic for rules.
- Synthetic columns are hashed (c_xxxxxx), so R4 (time-name regex) can only fire on columns with real names (civil war).
- No hard case has duplicate rows, so R5 is not expected to fire anywhere (checked: `df.duplicated().sum() == 0`).
- 4 hard cases and 4 clean cases are counts, not rates. The x3 replication of a deterministic rule is not independent evidence.
