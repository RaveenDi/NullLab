# Current manufacturing evidence

These are development/demo results, not a held-out evaluation or a general success rate. Inputs derive from UCI SECOM, CC BY 4.0, McCann and Johnston (2008), DOI 10.24432/C54305. Archive SHA-256: eea568baf3c2229096d7d294cf0b096b5502bd96d92c0b80a65b84714059be8e. Original archive: 1,567 entities, 590 sensor columns, 104 defects; fixed zero replacement creates the supplied numeric CSV. Timestamps are retained but excluded from predictors.

| Experiment | Outcome | Interpretation |
|---|---|---|
| Initial screening control | PR-AUC 0.190 -> 0.154; +0.036; all three intervals cross zero | No effect detected for the tested control |
| Constructed pre-CV synthetic resampling | PR-AUC 0.983 -> 0.139; +0.844; three positive intervals | Large protocol effect; scored population and prevalence also change |
| Real Spark + Wonder audit | Spark independently proposed the same typed resampling fix; Wonder disputed interpretation | Disagreement retained; no claim that agents jointly confirmed the conclusion |
| Clean twin, rules only | Baseline executed, no rule proposed a control | NOT TESTED, not verified clean |

Failed/unsupported preliminary attempts are retained in local job logs. One failed because the old contract treated 'not a forecast' as affirmative forecasting; this was corrected with a regression test. Another failed because NumPy preprocessing discarded provenance in the guard; fixed-zero replacement was made explicit in dataset preparation, without changing the guard to force acceptance.

The controlled evaluation scores original records at defect prevalence about 0.066; the constructed leaky evaluation scores a balanced synthetic population at prevalence 0.5. Average precision depends on prevalence. The difference combines contamination removal and evaluation-population correction; it is not an isolated causal amount of leakage. Conditional unpaired row-bootstrap intervals do not include retraining or all group/time uncertainty. Seeds are fixed, not independent dataset replications.

The live audit made three attempts, reserved estimate USD 0.662912 (not billing), with 12,847 prompt and 5,081 completion tokens. Its critic identified missing preprocessing/prevalence context; later code exposes that metadata to future reviewers. The original disputed result is preserved, not rerolled or relabelled as accepted. No outside user, time saved, new-flaw discovery rate or multi-agent advantage is claimed.

Public recordings are in examples/secom/results.json; detailed audit-time manifests, plans, raw vectors and critiques accompany each record. Their recorded engine identity is historical even if current source subsequently changes. A fresh unseen evaluation with matched reading/execution/critic baselines remains required before claiming generalization.

## Internal synthetic pilot, reported separately

The six-case frozen pilot measured **0/3 flawed-case controls** because a contract bug misread negated chronology. Spark's initial operations matched the reference on 2/3, and its retained operations after a bounded repair on 3/3. Three matched clean variants received model-only no-flaw judgments. The original failures remain recorded. A separate post-fix regression using those same plans executed all three controls: two inflation findings, one inconclusive. It made zero new model calls and is development evidence. Detailed denominators, effect intervals, costs and limitations are in [EVAL-V2-PILOT.md](EVAL-V2-PILOT.md).

The [fixed eight-case follow-up](EVAL-V2-FOLLOWUP.md) added ambiguous and unsupported inputs. Its original score measured 1/2 supported flawed controls (disputed) and found no positive inflation effects. It exposed scaler tracing and scope-state defects; the repaired checks are reported separately as development evidence. Neither cohort establishes general accuracy or critic superiority.

## Fresh post-repair internal cases

A [ten-case evaluation](EVAL-V2-RELEASE.md) exposed an initial-critic contract ambiguity: 0/3 supported flawed controls reached planning/measurement. That original failure is retained. After a prompt repair, a distinct six-case confirmation with new fixed data measured 3/3 controls: DISPUTED feature screening, NO EFFECT DETECTED scaling, and a descriptive INCONCLUSIVE group split. Its three matched clean judgments were model-only. No positive inflation verdict or general accuracy claim follows. The two schedules used 26 attempts and $4.84735975 reserved, not billed, and never replaced original outcomes.
