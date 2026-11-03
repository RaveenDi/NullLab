# Post-repair internal evaluation — 4 November 2026

This report retains a failed ten-case evaluation and a **separate** six-case confirmation after its critic-prompt repair. They must never be combined into a replacement success rate. These are coordinator-prepared and adjudicated synthetic cases, not a blinded benchmark, an external researcher study or a general reliability estimate.

## Original ten-case schedule

[Freeze and settings](../eval/v2_release/freeze.json), [truth](../eval/v2_release/truth.json), [original score](../eval/v2_release/score.json), [actual source snapshot](../eval/v2_release/instrument), [all scheduled outcomes](../eval/v2_release/results). Forty instrument/runner sources were captured before case preparation. Ten new fixed cases were scheduled once each in rules-only and Spark-plus-Wonder modes. Three flawed/clean pairs cover label screening, fitted scaling and entity separation; the latter adds a mechanism absent from the earlier two cohorts. Four further inputs cover unknown predictor timing, an unsupported generated forecasting baseline, an unavailable post-inspection predictor and multiclass rejection. Data seeds: 90401–90404. Case IDs do not disclose truth to the models.

The initial preparation runner had two lint issues (UTC alias and explicit loop binding). Its original bytes and manifest are retained beside a [pre-inference transition](../eval/v2_release/pre-inference-transition.json). Only that runner was refrozen before any measured/model outcome; product code, truth and case bytes did not change.

The experiment used Spark `muse-spark-1.3`, Wonder `muse-wonder-1.0`, low reasoning effort, 12,000 output tokens, 120-second timeout and zero transport retries. Each case had a $1 reservation/four-attempt cap; the cohort was bounded at $10/40 attempts. Seeds were 42, 43, 44, with 300 bootstrap replicates and two workers. The pre-run conservative historical/local reservation sum was $37.55886125; even the full envelope was below the documented $60 project ceiling. This is recorded-estimate accounting, not an independently checked account balance or bill.

| Original outcome | Rules only | Spark + Wonder |
|---|---|---|
| Supported flawed cases measured | 1/3: label screening, NO EFFECT DETECTED | **0/3** |
| Matched clean cases | 3/3 NOT TESTED, no counterfactual | 3/3 MODEL NO FLAW, no counterfactual |
| Missing predictor availability | NEEDS INFORMATION, before fitting | NEEDS INFORMATION, zero model attempts |
| Generated future-record task | UNSUPPORTED, before fitting | UNSUPPORTED, zero model attempts |
| Post-inspection predictor requires a feature edit | NOT TESTED | UNSUPPORTED, explicit feature-edit gap |
| Multiclass input | Rejected before fitting | Rejected before fitting, zero model attempts |

All seven other cases reproduced their baselines in each mode. Invalid multiclass rejection is an intended intake outcome, distinct from the three live orchestration failures. No positive inflation finding was issued. Model-only no-flaw judgments do not establish empirical clean specificity.

**Failure:** Wonder correctly described each of the three flawed mechanisms but labelled it `unsupported` with an empty `scope_gaps` array. Strict response validation refused the malformed abstention before Spark planning, retaining the original response and error. The initial reviewer had not received the edit contract, so “supported” was ambiguous between pipeline validity and instrument capability. Eleven provider attempts completed; reservations total **$2.03047350**, with 13,909 prompt and 8,489 completion tokens (22,398 total). These are reservations, not billed cost. No failed case was rerolled.

## Repair and distinct confirmation

The initial reviewer now receives the same intervention contract as the planner. Its prompt defines `supported` as sufficient information and expressible controls, including flawed pipelines; `unsupported` requires a concrete edit-list gap. The structured-output request and strict invalid-abstention rejection remain. The repair does not convert unsupported answers into supported ones, remove concerns or loosen guard acceptance. Two focused regressions verify prompt context/semantics and continued fail-closed handling. The engine suite passed **22 tests**. An intermediate duplicate keyword caused one test-collection error; it was corrected before confirmation preparation or inference.

[Exact engine transition](../eval/v2_confirmation/transition.json) records both raw-byte and LF-normalized before/after hashes. The original engine and all ten-case results remain intact. The separate [confirmation freeze](../eval/v2_confirmation/freeze.json) captures 41 actual source files, a new truth file, new case IDs and new CSV bytes before execution. Data seeds 91521–91523 were fixed without measuring effects. It reuses the same three pair templates deliberately: it is capability-informed confirmation of a repair, not unseen-mechanism generalization. Per-case limits remain $1/four attempts, with an overall $6/24-attempt envelope and no rerolls. It is a separate score, never a replacement for the 0/3 result above.

Confirmation outcomes are recorded in [the separate score](../eval/v2_confirmation/score.json) and [all original jobs](../eval/v2_confirmation/results). All six baselines completed in each mode. Live controls matched the three reference operations and passed runtime guards: **3/3 supported flawed controls measured**, with zero live harness failures. The three clean cases received model-only no-flaw answers, with no measured counterfactual and no empirical clearance.

| Separate confirmation case | Mean starting → control accuracy | Final live outcome |
|---|---|---|
| Label screening, cn-b4m8 | 0.610 → 0.559 | DISPUTED: seed signs 0, 0, +; Wonder retained the insufficient-evidence objection |
| Fitted scaling, cn-q2v9 | 0.824 → 0.824 | NO EFFECT DETECTED; all seed intervals include zero |
| Entity separation, cn-p8d6 | 0.873 → 0.507 | INCONCLUSIVE: descriptive group result despite Wonder's acceptance and positive row intervals |
| Three matched clean cases | Baselines only | MODEL NO FLAW; no empirical clean specificity |

Rules alone measured 1/3 flawed controls (label screening, INCONCLUSIVE) and left the other five cases NOT TESTED. The live workflow made **15 completed attempts**, reserving **$2.81688625**, with 29,301 prompt and 11,065 completion tokens (40,366 total). It produced no positive `INFLATED` verdicts. The two distinct schedules together used **26 attempts/$4.84735975 reserved**, below their combined $16/64-attempt envelope. None was rerolled. The conservative recorded total after both is $42.40622100, below $60; it is not billing or a live account-balance assertion.

The group result illustrates why the deterministic inference boundary remains necessary: Wonder accepted the control and described its row intervals as supportive, but the engine still refused a calibrated group-inflation conclusion. The scaler planner predicted a drop of 1 absolute accuracy unit while the measured change was essentially zero. Model effect forecasts are retained, not treated as calibrated estimates. Control execution coverage is not effect accuracy or scientific correctness.

## Interpretation limits

- Rules and the live planner-plus-critic workflow are compared with their different capabilities/costs. The planner's proposal is retained before execution; it is not an independent matched model-only arm. There is no separate no-critic arm or estimate of critic superiority.
- Mechanism truth specifies an admissible control, not a required numerical effect. Repeated seeds are not independent projects. No-control clean judgments are unmeasured.
- Group controls remain descriptive/inconclusive; fixed-prediction row intervals are not group-aware coverage evidence. All other intervals also exclude training uncertainty.
- Cases and adjudication are internal and informed by the supported edit vocabulary. No outside-user impact, time saving, broad accuracy or comprehensive research-professor claim follows.
- Exact source/case bytes and provider outcomes are retained. Later repairs or new cohorts cannot overwrite an original denominator or convert earlier failures into successes.
