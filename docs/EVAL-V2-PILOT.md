# V2 internal synthetic pilot: original frozen score

The frozen engine produced **0 measured controls out of 3 flawed cases** in both the rules-only and Meta runs. Spark's first proposals matched the reference operations on 2/3 flawed cases; after one permitted repair on the parcel case, the retained proposals matched 3/3. All three were then rejected before control execution because the contract misread “No group or chronological structure is asserted” as a forecasting requirement. The original failures remain part of the score.

Spark returned `MODEL_NO_FLAW` for the three matched clean variants. These are **three model-only assessments, not measured clean findings or an estimate of empirical specificity**. No final critic reviewed measured evidence because no control reached measurement. Initial Wonder reviews were recorded, but there is no matched no-critic arm and no measured critic benefit.

The machine-readable adjudication is [v2_pilot_score.json](../eval/v2_pilot_score.json). It scores only the original `out/prospective-offline-results` and `out/prospective-live-results`, verifies their input/snapshot hashes against truth, and records the original artifacts' SHA-256 hashes. Later runs of stored plans under the repaired contract belong to `out/prospective-regression-results` and must be reported separately. No original outcome has been replaced or rescored using the repair.

| Case | Synthetic family / mechanism truth | Rules-only outcome | Original Meta outcome | Spark operation match, first → retained |
| --- | --- | --- | --- | --- |
| `nl-q7v2` | Industrial pump; full-data model reused in folds | `NOT_TESTED` | `UNSUPPORTED` | Yes → Yes |
| `nl-m4c8` | Industrial pump; matched fold-refit variant | `NOT_TESTED` | `MODEL_NO_FLAW` | No flaw proposed |
| `nl-b9r3` | Energy inverter; supervised selection before CV | `UNSUPPORTED` | `UNSUPPORTED` | Yes → Yes |
| `nl-t6n1` | Energy inverter; matched fold-local selection | `NOT_TESTED` | `MODEL_NO_FLAW` | No flaw proposed |
| `nl-h2s5` | Parcel logistics; training rows also scored | `NOT_TESTED` | `UNSUPPORTED` | No → Yes |
| `nl-w8k4` | Parcel logistics; matched disjoint holdout | `NOT_TESTED` | `MODEL_NO_FLAW` | No flaw proposed |

Each mode executed all six original baselines on seeds 42, 43 and 44. No numerical external reference was supplied, so baseline completion means execution of the supplied code, not reproduction of a published score. Rules proposed the reference control on 1/3 flawed cases, which was rejected by the same chronology bug; the other five rules outcomes were `NOT_TESTED`. Neither mode produced a measured counterfactual result on any of the six cases. There were no flaw proposals on the three clean cases, but rules coverage was absent and Meta assessments remained model-only.

The live run made **15 provider attempts**, all returning completed responses: nine Spark planner calls and six initial Wonder critic calls. Durable attempt reservations total **$2.070315**. The original totals file reports **$2.070313** because it sums estimates already rounded per job; the $0.000002 difference is rounding. These are reserved estimates, not billed cost. Recorded usage was 21,856 prompt tokens and 14,411 completion tokens, totaling 36,267. Median recorded Intake-to-finish time was 24.73 seconds live and 4.30 seconds rules-only; jobs used two workers, and these times exclude queue time. No comparison of customer time saved is supported.

The [instrument freeze](../eval/v2_protocol_freeze.json) preserves the exact raw-byte hashes and the coordinator's formatting-only transition before inference. A configuration deviation is explicit: the freeze recorded provider defaults of 90-second timeout, one retry and a $1 engine job cap; the scheduled live runner used a 120-second timeout, zero retries and $0.80 per case, bounded by 24 attempts/$4.80 total. The actual model IDs were `muse-spark-1.3` and `muse-wonder-1.0`. Statistics were scheduled with 300 bootstrap replicates but no control measurement reached that stage.

The six [fixtures](../eval/v2_cases), [truth](../eval/v2_truth.json), [freeze](../eval/v2_protocol_freeze.json) and [cohort note](../eval/V2-PILOT-NOTE.md) are now available locally in the repository. An AI reviewer constructed the cases from known instrument capabilities after the instrument was frozen, with fixed data seeds and no selection on measured effects. Truth stayed outside the case folders and model contexts until inference completed. There are three synthetic data families with one flawed/matched-clean pair each, 120 records per variant; repeated seeds and paired variants are not independent projects. No ambiguous or intentionally unsupported case families were included, so this is a limited pilot of the [broader protocol](../eval/V2-PROSPECTIVE-PROTOCOL.md).

The chronology defect motivated a generic contract repair. These cases now serve as development/regression evidence; a repaired rerun is not a fresh prospective test. This pilot establishes neither performance on independent real projects nor external-user value, calibrated scientific specificity, model superiority or collaboration benefit.

## Separate development regression after the contract repair

The later `out/prospective-regression-results` rerun used exactly the same six input manifests, retained plans and baseline records as the original live pilot. Independent adjudication verified all six matches, checked the evidence manifests, and recomputed point metrics from the stored prediction vectors. It made **zero new model calls**. The [development regression score](../eval/v2_regression_score.json) records the evidence, source hashes, per-seed effects and limitations. The original [pilot score](../eval/v2_pilot_score.json) remains byte-for-byte unchanged, with SHA-256 `c2fec394314acc5dd3296eab3e8d146ad75abe8ead2dbc18c6f1b2201eae6b5c`.

The repaired contract accepted and measured all three stored flawed-case controls. Two received `INFLATED`; supervised selection remained `INCONCLUSIVE` because seed 42's conditional interval includes zero. The three clean cases again received `MODEL_NO_FLAW` from their inherited plans; no new model assessment or clean control measurement took place.

| Case / control | Mean original → controlled accuracy | Mean difference, percentage points | Development verdict |
| --- | --- | --- | --- |
| `nl-q7v2` / refit inside each fold | 1.0000 → 0.5806 | +41.94 | `INFLATED` |
| `nl-b9r3` / selection inside each fold | 0.6583 → 0.5111 | +14.72 | `INCONCLUSIVE` |
| `nl-h2s5` / disjoint random holdout | 1.0000 → 0.4778 | +52.22 | `INFLATED` |

The recorded per-seed intervals below are unpaired row-bootstrap intervals conditional on fixed predictions, using 300 replicates. They omit model-training uncertainty and do not establish a general population-level coverage guarantee. Seeds and matched variants are not independent projects. No pooled confidence interval for the mean across seeds is claimed.

| Case | Seed | Original minus control, percentage points | Recorded 95% conditional interval, percentage points | Evaluated rows, original → control |
| --- | --- | --- | --- | --- |
| `nl-q7v2` | 42 | +40.83 | [30.83, 50.00] | 120 → 120 |
| `nl-q7v2` | 43 | +40.83 | [32.50, 49.60] | 120 → 120 |
| `nl-q7v2` | 44 | +44.17 | [35.83, 51.67] | 120 → 120 |
| `nl-b9r3` | 42 | +7.50 | [-5.00, 19.21] | 120 → 120 |
| `nl-b9r3` | 43 | +20.00 | [7.50, 31.27] | 120 → 120 |
| `nl-b9r3` | 44 | +16.67 | [4.17, 28.33] | 120 → 120 |
| `nl-h2s5` | 42 | +46.67 | [28.25, 63.33] | 120 → 30 |
| `nl-h2s5` | 43 | +50.00 | [33.33, 70.00] | 120 → 30 |
| `nl-h2s5` | 44 | +60.00 | [43.33, 78.42] | 120 → 30 |

The parcel control changes the number of evaluated rows and their class prevalence. Its score difference compares evaluation protocols and must not be called an isolated causal amount of leakage. The single-factor configurations use aliases across `fix_A`, `fix_B` and `fix_both`; their stored factorial interaction fields are not separate intervention evidence and are not interpreted here. No critic reviewed these measured effects, so this regression does not measure collaboration benefit or empirical clean specificity.

The recorded instrument change is confined to `agent/contract_g9.py`: original SHA-256 `7da895a5af54a20436c8009320908641dccea2f11cc75ba74382a36bfb953ba4`, regression SHA-256 `d319c638dd4ca2074e4f06af9e8dffdaef00a2fa182b867ee04171e222c9f81f`. The original pilot retained instrument hashes but no complete original instrument source snapshot was found; hashes identify bytes but cannot recreate missing source. This limitation is separate from the preserved case inputs and original result artifacts. The regression is evidence that the inspected defect was repaired on these development cases, not a new prospective success rate.
