# Research room: methodology review

Role: skeptical experimental-methods reviewer. This is an internal AI assessment, not an interview with a researcher or evidence of adoption. No browser, network, paid-model call or source modification was used in this review.

## Main recommendation

Build an **author-confirmed study/data contract with an answer-to-rerun path** before adding more autonomous debating roles. The useful unit is an unresolved research decision tied to an input version, not a transcript of agents agreeing with one another. The current engine already makes an important distinction between measured evidence, model-only judgments and unsupported or missing-information outcomes. The missing part is helping the author supply the necessary facts and continue the investigation.

## Observed evidence

The current CSV adapter accepts a free-text intended use, then feeds every numeric non-target column into a fixed Random Forest with shuffled stratified CV (`agent/intake.py`, `feats` and `claimed_eval`). It does not have structured predictor-availability, entity-role, time-role or target-population fields. A warning tells users to remove identifiers and confirm timing, but neither fact is represented as an enforceable input contract.

An offline synthetic probe is preserved in `out/research-room-methodology/probe-summary.json` and its adjacent case/job directories. It supplied 60 rows, a sensor, a repeated-unit identifier and `after_test_status`, a direct outcome proxy. Its intended use explicitly stated that screening happens before the final test, `after_test_status` is unavailable at screening, and deployment concerns previously unseen units. The adapter selected all three numeric predictors and used random record CV. The baseline obtained average precision **1.0**, while the audit correctly ended **NOT_TESTED**, with zero model calls. This is not a false empirical clearance. It shows that a new-input author can receive a spectacular but inappropriate starting evaluation before the instrument has represented the actual study question.

The probe was authored for this review and is development evidence. It is not a new held-out accuracy test or proof that the live Meta planner would miss the concern.

Other inspected facts:

- `agent.engine._context` sends a narrative intended use and preprocessing description but no structured availability or population contract.
- `NEEDS_INFORMATION` carries questions, yet the API/UI has no linked answer submission or immutable case revision that resolves them. A researcher must leave the workflow and manually edit/adapt files.
- Initial reviewer objections remain in the JSON. `unresolved_concerns` is elevated in the no-flaw branch, but there is no uniform issue ledger spanning measured and unmeasured outcomes.
- Group/time controls are conservatively descriptive/inconclusive because real group/time identities are absent from full measurement vectors. That restriction should remain until the statistical instrument supports the design.
- `export_bundle` correctly reserves a rerunnable experimental ZIP for measured results. Researchers also need an explicitly non-experimental methods report for useful abstentions and scope gaps; JSON alone is cumbersome to discuss with collaborators.

## Implement now

1. **Minimal structured author contract.** Ask what is predicted, when the prediction is made, which columns may be available then, and whether evaluation concerns new independent records, unseen entities or a later period. Show explicit predictor selection and non-predictor roles. Do not infer availability from column names. An author's availability statement is a declaration, not independently verified truth.
2. **Gate the generated baseline on that contract.** Exclude only explicitly selected non-predictor columns from a newly generated baseline, retain all original data bytes for provenance, and label the derived pipeline. If unknown timing/population or an unsupported grouped/temporal design prevents a meaningful generated evaluation, ask for the missing fact or return unsupported **before** expensive fitting/model calls. Do not silently replace a grouped/future-use question with random CV.
3. **Resolve questions through a new input version.** Give unresolved questions stable IDs. Record the author's answer and source of that answer, create a new case version with a parent-input hash, and start a new audit. Keep the earlier result unchanged. An answer alone must not upgrade an old run to accepted or verified clean.
4. **Produce a shareable decision report for every terminal state.** Separate author declarations, model hypotheses, deterministic guard findings, measured results, reviewer objections and open questions. A no-data Markdown/JSON report can be shared without implying it is a rerunnable measured bundle. Keep explicit warnings about what is not tested and whether source/data are included.

Acceptance checks: the probe's unavailable outcome proxy and identifier are not silently predictors; an unknown/unsupported study design stops or asks a question before fitting; answering creates a distinct input identity; original result files remain byte-identical; unmeasured reports never contain a fabricated effect or experimental-clearance label.

## Implement next

- **Comparable-run view.** Show what changed in source, data, decision contract, predictors, metric, seeds, scored rows and prevalence. Numerical ranking is not meaningful across different populations/metrics. Display such differences before offering a delta; do not present an arbitrary before/after pair as a causal intervention.
- **Explicit baseline identity.** Prefer machine-readable `baseline_kind`/`reference_matched` distinctions over a lone `reproduced: true` when no external numerical reference exists. The current text caveat is correct; the structured record can be clearer for downstream readers.
- **Structured issue/evidence ledger.** Every specialist contribution cites an input, code location, artifact or author declaration. Preserve disagreements and an unresolved state. Agents can propose tests; only executed results or an explicitly documented author response can change the relevant evidence status.

## Later, with new validation

Paired row-aware and group/time-aware inference requires stable prediction-row identity from the real executor, a declared target population, and an appropriate resampling/coverage study. A smoke guard's row IDs or matching vector lengths do not supply that statistical contract. Extend the executor result schema first, then compare intervals on controlled designs; do not merely change the bootstrap or remove the current inconclusive safeguard.

Notebook/repository import, literature review, dataset search, broad experiment design and local open-weight reasoning should be separate adapters with their own evidence/access boundaries. Current binary sklearn pipeline checks do not validate those broader research capabilities. A visible “research room” should expose bounded roles and cited artifacts, not imply a comprehensive autonomous professor.

## Architecture implications

Add a small immutable study/workspace layer around the existing engine:

`Study brief -> declared data contract -> validated input version -> audit -> issue/evidence ledger -> author clarification -> new input version`.

Keep `agent.engine.run_audit` as the sole measurement path. Put author answers/declarations in hashed case inputs, not mutable conversation memory. Allow study/workspace history to reference jobs but not overwrite their result JSON. Feed the structured contract to planner and critic and include its outbound disclosure. Role outputs remain advisory until a deterministic check/experiment or explicit author-provided fact supports a state transition.

## Selection against the project scorecard

These are improvements to the existing Meta-driven evaluation instrument, not a new anti-project or chat-wrapper pivot. They use current licensed/synthetic inputs and have a bounded testable path. Their value hypothesis is a researcher reaching an actionable next step with fewer invalid evaluations; it is not a measured time-saving claim. Meta planning/critique remains in the substantive control-selection loop, while declaration validation remains deterministic. No judge score or guaranteed placement is inferred from this review.

## Discussion and agreed constraints

The researcher-workflow role independently reproduced an unseen-entity narrative accepted with a numeric identifier as a predictor. It challenged a per-feature questionnaire as impractical for SECOM's hundreds of columns. We converged on one availability declaration plus exception exclusions, population choice, conditional entity/time column and a compact role preview. Title/history should add no extra research paperwork.

The architecture role identified missing job recovery and asked whether answers should immediately unlock a run. My response: a new version must revalidate the entire contract; unknowns gate again, and answers never mutate or retroactively upgrade an old result. The coordinator accepted a bounded implementation of study roles, pre-execution gates, immutable clarification revisions, history/reopen and a review memo for unmeasured outcomes. New group/time split inference remains out of this implementation.

Represented-entity use is conditional: a record-level baseline may describe records for known entities, but does not establish independent-row uncertainty or unseen-entity performance. An author declaration should be visible as such. A known unavailable feature must not be selected merely because it is numeric; removing/excluding it creates a documented generated-pipeline revision.

## Independent implementation acceptance matrix

| Check | Required behavior |
|---|---|
| Confirmed independent-record task | Selected numeric predictors only; target excluded; role preview matches generated `feats` |
| Metadata includes string IDs/dates | Raw CSV retained; excluded metadata does not make the numeric predictor adapter reject an otherwise valid input |
| Unknown availability/population | NEEDS_INFORMATION before classifier fitting, executor dispatch or paid call |
| Unseen-entity/future generated design | Unsupported or missing-information gate; never silently random-CV the requested study |
| Invalid/target/unknown column role | Explicit validation error rather than accidental label inclusion or silently invented columns |
| Clarification revision | New case/input identity and parent lineage; old case and result bytes unchanged |
| Still-incomplete clarification | Remains gated; a submitted answer alone is not clearance |
| Baseline/abstention export | Clearly a review memo, with no invented counterfactual effect/control; sharing contents explicit |
| Compare changed studies | Flags different input/contract/population/metric/seeds/instrument; no unsupported causal delta |
| Represented entities | Descriptive conditional scope and unresolved dependence remain visible |

These are proposed acceptance conditions. They have not yet been verified against the coordinator's implementation.
