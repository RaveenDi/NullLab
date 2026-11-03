# Eight-case internal follow-up

The original fixed follow-up measured **one of two supported flawed-case controls**. That measurement was disputed; there were **no positive inflation findings**. These results remain unchanged after the subsequent repairs. [Machine-readable adjudication](../eval/v2_followup_score.json) includes original result hashes and case denominators.

An independent AI reviewer prepared eight fixed synthetic cases after capturing the actual bytes of 36 instrument files, prompts and settings. It completed preparation before hitting a usage limit; the coordinator verified the snapshot, ran the schedule and adjudicated after all results were written. The cases include two matched flawed/clean pairs, two ambiguous cases and two unsupported cases across six mechanism families. Construction knew the instrument's capabilities, and resampling was already demonstrated on SECOM. This is internal synthetic evaluation, with no outside researcher or real-project generalization claim.

| Case | Category | Original rules outcome | Original live outcome | What the result establishes |
|---|---|---|---|---|
| fx-v5q8 | Whole-data fitted scaler | NOT_TESTED | UNSUPPORTED | Planner identified the reference operation; runtime provenance failed, so no control was measured |
| fx-c7m2 | Matched fold-local scaler | NOT_TESTED | MODEL_NO_FLAW | Model-only assessment; no empirical clean specificity |
| fx-b8w3 | Full-data balancing | NOT_TESTED | DISPUTED | A balancing-removal protocol ran; its difference was small and uncertain |
| fx-n4r9 | Matched training-fold balancing | NOT_TESTED | MODEL_NO_FLAW | Model-only assessment; no empirical clean specificity |
| fx-h3p6 | Unresolved entity population | NOT_TESTED | MODEL_NO_FLAW | Planner explained the conditional population issue, but the top-level state obscured it |
| fx-s9d1 | Unknown predictor timing | NOT_TESTED | MODEL_NO_FLAW | Missing timing was acknowledged; reviewer concerns did not affect the early-return state |
| fx-k2t7 | Known post-outcome predictor | NOT_TESTED | MODEL_NO_FLAW | Planner acknowledged feature removal was outside the DSL; the state failed to distinguish unsupported concern from no flaw |
| fx-f6j4 | Multiclass intake | INCONCLUSIVE / rejected | INCONCLUSIVE / rejected | Binary-only limit was enforced before inference; zero calls |

Seven original baselines completed per mode. No numerical external score was supplied; execution is not reproduction of a publication. The two flawed pipelines were recognized, but recognition is separate from a valid, measured control. The scaler operation matched the reference exactly. The balancing proposal removed balancing, rather than keeping it inside training folds; the guard accepted this alternative protocol and the critic disputed its interpretation. It changed accuracy from 0.6944 to 0.6889 (difference +0.0056); all three conditional intervals crossed zero. The evaluated prevalence changed from 0.50 to 0.25, so this is not an isolated causal leakage estimate.

There were 15 provider attempts: seven initial Wonder reviews, seven Spark proposals and one final Wonder review. Raw durable reservations total **$2.44894425**; the totals file sums rounded job estimates to $2.448943. Reservations are not billed cost. Recorded tokens: 18,006 prompt, 14,967 completion, 32,973 total. Median Intake-to-finish time was 2.93 seconds offline and 21.21 seconds live across the seven cases with intake events per mode, excluding queue time. The rejected multiclass case has no intake timestamp and is excluded from that timing denominator.

The initial critic's concerns were visible in the evidence but did not change three early no-flaw states. The UI did not issue empirical clean clearance, yet those labels still obscured actionable uncertainty or scope limits. There is no independent matched no-critic arm, empirical clean specificity estimate or demonstrated general multi-agent advantage.

## Repairs after inspecting this cohort

These cases became development evidence when their failures informed changes. The original snapshot and score remain separate from all repaired runs.

- Exact known row-preserving sklearn scaler implementations now preserve row identity through transform/fit_transform. Constructors are not misrecorded as data-processing helpers. Unknown/custom transformers do not inherit that identity, and missing scoring-model evidence fails closed.
- The author-level planner contract accepts explicit `needs_information` questions and `unsupported` scope gaps. These are abstentions, not evaluation clearance.
- An early no-flaw answer retains independent reviewer concerns as disputed, needs-information or unsupported, rather than discarding them. CI treats these outcomes as unresolved, and the UI exposes the next question or scope gap.

The repair suite passed 37 focused checks, including real transformer subprocesses and rejection of an unverified reordering subclass. Separate [development checks](../eval/v2_followup_regression.json) measured the stored scaler control: accuracy 0.7389 to 0.7444, difference −0.0056, with all intervals crossing zero (NO_EFFECT_DETECTED). The three stored-response fixtures now retain objections as DISPUTED. All four input identities and original baselines match their original records; zero new model calls were made. These responses to earlier prompts are fixtures, not valid replay against changed prompts or new inference. No repaired rerun is added to this original evaluation's success rate.
