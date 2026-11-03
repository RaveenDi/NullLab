# Research-room decisions — 3 November 2026

This is the record of an internal AI review commissioned by the owner. The roles reviewed code, ran offline synthetic workflow probes and exchanged findings. They were not external researchers or human interviewees. No browser walkthrough was performed. Original probe outcomes remain preserved; repairs are development evidence and do not replace the two frozen evaluation cohort scores.

## Findings and challenges

| Role | Finding | Challenge raised during discussion | Agreed response |
|---|---|---|---|
| Researcher/user advocate | Numeric IDs entered generated predictors, text metadata was rejected, saved runs could not be listed, and baseline-only export gave a misleading identity error. Its unseen-line toy case obtained AP 0.8704 but correctly remained NOT_TESTED. | A per-feature availability questionnaire would be impractical for SECOM's hundreds of features. A discussion transcript would not make a blocked study actionable. | Use one availability declaration plus explicit exclusions and entity/time roles; add history/reopen and an honest unmeasured assessment. |
| Experimental-methods reviewer | A toy unavailable target proxy plus repeated-unit ID obtained AP 1.0 before the study question had been represented. NOT_TESTED avoided empirical clearance, but the baseline was inappropriate for the declared unseen-unit task. | An author answer is a declaration, not verified truth. Random CV cannot answer an unseen-entity/future-use question. Group/time uncertainty must not be enabled by removing the current safeguard. | Gate incomplete/unsupported generated studies before fitting; preserve dependent-record caveats; create a new input version and re-audit after clarification. |
| Architecture/API reviewer | Questions had no revision path and durable job files lacked a recovery workflow. Code/data/config identity must remain authoritative. | A mutable chat workspace could silently change the evidence behind an old result. Exporting every file beside a snapshot could include unrelated private data. | Keep a single engine, create fresh generated cases, retain parent linkage, verify saved snapshots and export only manifest-bound inputs. |
| Coordinator | Actual recorded model contributions can be useful if their provenance and limits remain visible. | More personas or apparent agreement do not demonstrate better scientific results. | Render the existing planner, independent reviewer, final critique and deterministic execution as recorded evidence, without invented dialogue or a consensus score. |

The original role reports are [researcher workflow](researcher-workflows.md) and [methodology](methodology.md). The initial probes are under `out/research-room/researcher-workflows` and `out/research-room-methodology`; these ignored development directories are not public release evidence by default.

## Implementation decisions

1. **Keep the product narrow.** NullLab checks supported binary pipeline evaluations using typed controls and measured results. It does not train a new foundation model or become a universal research professor.
2. **Put the research question before the attractive score.** Capture decision time, population and predictor availability. Retain metadata in the CSV while excluding declared non-predictor roles from the fixed generated pipeline. Unknown facts ask questions; unsupported generated designs stop before fitting/model calls.
3. **Represent evidence types explicitly.** Author declarations, aggregate diagnostics, model judgments, guard decisions, baseline scores and measured effects are different records. A baseline or agent agreement is not empirical clearance.
4. **Continue through a new version.** Clarification creates a fresh case with parent linkage and a new audit identity. Old outcomes remain unchanged. Trusted custom code is never silently regenerated through a data-only clarification.
5. **Make every useful outcome recoverable.** List/reopen saved runs and render actual review contributions. Offer a verified assessment ZIP when no controlled experiment was measured, with explicit input-data/code disclosure. Keep measured bundles separate.
6. **Compare descriptively.** Verify inputs and protocols, show differences and refuse unsupported causal rankings. A changed population, declaration or pipeline is not an isolated treatment effect.

Two implementation roles reached usage limits after contributing changes and acceptance probes; the coordinator verified their code and completed the integration. Their partial completion is not treated as an independent release approval.

## Evidence retained from development

Nine independent acceptance variants exercised supported/unknown/unsupported studies and invalid role selections. The same original AP-1.0 probe CSV, when declared as an unseen-entity generated study, subsequently stopped as UNSUPPORTED with zero executor dispatches and zero model calls. This is a repair check on a known case, not a new success-rate estimate.

A supported independent-record study executed three seeds and obtained baseline AP 0.5417, ending honestly NOT_TESTED with no model calls. Both baseline-only and gated assessments exported with explicit no-counterfactual language; an unrelated extra snapshot file was excluded, and modified metadata was rejected. These artifacts are recorded in `out/research-room-methodology/implementation-acceptance`.

The reviewer also found a source-consistency gap: retaining the declared `PREDICTORS` constant while editing `feats()` bypassed the original generated-role check. Its probe remains `changed-generated-feats.json`. The required repair is full trusted-template validation, or an explicit custom-code boundary; checking the constant alone is insufficient. Current acceptance and regression status belongs in the coordinator's release report, not a rewritten original probe.

The coordinator implemented full normalized-template AST matching and pinned the intake template in instrument identity. Custom adapters retain a visible unverified-role warning. Revision lineage now includes exact parent input hashes and a verified linked-audit manifest when available; a changed parent cannot borrow the earlier audit identity.

A subsequent independent read-only review reproduced overlapping saved-view responses that could mismatch a conclusion/download, and stale running checkpoints after restart. Request generations and terminal-state display/comparison rules close those paths. Explicit reviewer abstentions now require actionable questions or scope gaps. An integrated API check also exposed a transient Windows atomic-replacement sharing failure; bounded retries preserve the prior complete checkpoint. The original failing XML is retained separately from repaired checks. See [workflow validation](../../RESEARCH-WORKSPACE-VALIDATION.md) for the integrated counts and real offline acceptance.

The client reviewer reported seven minimal-DOM regressions covering history/reopen, active-job separation, revisions, comparison and recorded-mode isolation. Those are code-level interaction checks, not a browser walkthrough or an end-user study.

## What remains uncertain

No outside researcher has used this workflow. Whether the brief improves completion, reduces invalid evaluations or saves time is unmeasured. No new general scientific-accuracy or critic-benefit claim follows from this discussion. Generated study gates do not validate a user's declarations. Custom pipelines need their own feature/protocol review. Group/time uncertainty, local open-weight model quality, notebook/experiment-tracker adapters and public hosted execution remain separate validation projects.

The [roadmap](../../RESEARCHER-ROADMAP.md) prioritizes these hypotheses by user decision and required evidence. The updated [architecture](../../ARCHITECTURE.md) describes the new workflow and its boundaries.
