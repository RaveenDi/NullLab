# Research-room review: practical researcher workflow

Role: internal AI researcher/user advocate. This is a product hypothesis and an offline software probe, **not an interview, external-user study or researcher adoption evidence**. No browser walkthrough, paid inference, model call or source edit was performed by this reviewer.

## What I tested

I created a fresh isolated workspace under `out/research-room/researcher-workflows/workspace`, then used the actual FastAPI `TestClient`, CSV intake, queued worker and current engine. Data were fixed before execution: seed 36631, 120 synthetic records, six repeated production-line identifiers, two numeric sensor features and balanced binary labels. The intended-use statement explicitly described production lines absent from the training sample. Labels depend on line identity in this toy construction; it is a workflow stress case, not a claim about manufacturing data.

The complete probe and JSON results are `out/research-room/researcher-workflows/probe.py` and `probe.json`. The job artifacts are `workspace/out/jobs/27168b4a-f47d-4b71-b8e4-9f0848e79c1e` beneath that directory.

| Step | Observed outcome |
|---|---|
| Fresh numeric CSV intake | HTTP 201; three predictors, including numeric `line_id` |
| Rules-only audit | Reached NOT_TESTED in 10.58 seconds; zero model calls |
| Generated baseline | Random-row stratified CV; average precision 0.8704, reference prevalence 0.5 |
| List/reopen runs | GET `/api/jobs` returned HTTP 405; only a known job-ID lookup exists |
| Export this result | HTTP 409: “cannot be exported with its current evidence identity” |
| Retain a text group label | Intake rejected it with HTTP 400 and told the author to remove IDs/dates/text |
| Invalid single-class target | Correctly rejected with HTTP 400 |

The baseline's high score is not an estimated inflation effect: I did not execute a matched unseen-line control. The relevant finding is that the generated evaluation protocol does not implement the stated unseen-entity use, while the current intake offers no structured way to retain that distinction. NOT_TESTED correctly avoids scientific clearance.

## Highest user friction

1. **The author cannot express the evaluation contract precisely.** Intake collects target and one text paragraph, then treats every other numeric field as a predictor. Text grouping metadata must be removed. Numeric identifiers remain predictors. The generated random-row protocol is unchanged by a statement about new entities or future observations. Asking an author to remove metadata discards the information needed to choose a defensible split. This is more consequential than adding extra agent personas.
2. **An unresolved result has no continuation.** Questions and scope gaps can be displayed, but the UI has no answer-and-retest path, versioned case lineage or coauthor decision record. A researcher needs to resolve “when is this feature available?” and see which assumptions changed between runs. A chat transcript alone would not supply that evidence.
3. **A completed session is difficult to recover or share.** The server persists jobs but has no list endpoint, and the UI initializes its active job only in memory. Reloading loses the visible run. Most fresh CSV/rules runs end NOT_TESTED; their bundle request fails despite an input manifest existing. The error attributes the problem to identity rather than the absence of a measured control. JSON download remains available in the current tab, but it is not a complete reproducible input bundle.

## Implement now: three bounded improvements

### 1. Add a study brief and explicit feature/metadata roles

Collect a named research question/claim, intended population (same independent records / unseen entities / future observations / unknown), decision time, predictor columns, excluded columns and optional entity/time metadata. Keep declared facts visibly distinct from verified facts. Show a preview of selected predictors and the actual generated evaluation before running.

The smallest safe release can support independent-record baselines and explicit feature exclusions, while returning an actionable unsupported/needs-information state for grouped or future use until those paths are implemented. It must not silently call those protocols validated. Preserve entity/time fields as metadata instead of forcing users to delete them.

Acceptance check: the probe's `line_id` can be declared metadata, never enters `feats`, and the system either runs an explicitly supported unseen-line protocol or stops with a clear limitation before presenting a random-row score as the answer to that question.

This recommendation is an inference from both the probe and scikit-learn's official guidance: evaluation depends on sampling assumptions; grouped observations and time-dependent observations need suitable partitioning. Its leakage guidance also makes prediction-time availability and train-only fitted preprocessing central. [Cross-validation](https://scikit-learn.org/stable/modules/cross_validation.html), [common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html).

### 2. Make the “research room” a persistent decision workspace

Use the existing planner/independent-critic roles as evidence-producing participants. Store structured questions, objections, proposed experiments, author answers and unresolved decisions against a case version. A new answer creates a new immutable case version and linked run; it does not revise an old result. Show what each participant contributed and what execution established. Unknown states should have a visible next action.

Acceptance check: an author can answer a missing-timing question, leave an evidence/rationale note, create a new linked audit, reload the page and still inspect the prior question, answer and original result. Agent agreement must never mark a concern empirically resolved.

### 3. Add run recovery and an honest report for every outcome

List recent local jobs, reopen them by ID/URL, show case title/version/mode/status, and offer a concise shareable assessment report even for NOT_TESTED, NEEDS_INFORMATION, unsupported and failed runs. Label baseline-only artifacts as assessments with no counterfactual; include actual inputs only under an explicit private-data export action. Keep measured controls/raw vectors separate and preserve the existing identity checks.

Acceptance check: the probe's run can be recovered after a reload and exported as an **unmeasured assessment**, with the baseline, claim, open questions, limitations and hashes. A measured bundle remains a distinct artifact. At minimum, replace the misleading identity error with the actual reason a measured-control bundle is unavailable.

The official NeurIPS checklist's emphasis on matching claims to scope, explaining limitations and supplying reproducibility information supports this evidence-first design; it is not proof that users prefer any particular interface. [Paper checklist](https://neurips.cc/public/guides/PaperChecklist).

## Researcher needs after the hackathon

These are hypotheses requiring user validation: a read-only notebook/repository adapter that shows the mapping into the supported contract; links to experiment trackers and data versions rather than duplicated datasets; human coauthor comments and approval history; protocol preregistration and sealed test-set discipline; identity-aware paired/group/time uncertainty; and privacy-preserving local model quality that is measured on available hardware. Literature/gap-finding agents should cite actual sources and remain a separate capability from experimental validation.

Do not broaden the product into a universal autonomous research professor or unbounded multi-agent chat room before these core workflows work. The useful current promise is: help an author identify what assumption is unresolved, run a legitimate supported test, and leave with a recoverable evidence record.

## Implementation follow-through

After the cross-role discussion, this reviewer implemented the client side of the agreed brief/revision/history workflow in `app/static/index.html`, `workspace.js` and `workspace.css`. The room renders actual recorded contributors, open questions and baseline-only evidence; author revisions reuse data as new cases. Active audit identity is independent of the displayed record, import/revision/new-run actions stay locked during that audit, older permalink targets reopen without changing cancellation, and recorded demos make no API requests. Assessment downloads explicitly disclose that their ZIPs include input data/code. Seven minimal-DOM regressions in `tests/test_workspace_js.py` pass; JavaScript parses and the Python test file passes Ruff. These checks are not a browser walkthrough, API integration certification or external-user validation. The original probe remains unchanged; engine/API integration is being verified separately by the coordinator and other roles.
