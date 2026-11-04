# Researcher workflow roadmap

The question/upload-first Research Workdesk is implemented locally. It surrounds the existing v2 measurement engine with persistent investigations, materials, reviewed brief revisions, plans and linked jobs. The [implementation record](plans/RESEARCH-WORKDESK.md) and [architecture](ARCHITECTURE.md) describe the supported slice; broader design goals remain explicit below. The [current validation record](reviews/2026-11-04-workdesk-validation.md) reports browser/package/final-review checks; source publication and external-user evidence remain separate.

The immediate user is an author/student asking whether a binary tabular pipeline evaluation supports a concrete intended use, what remains unresolved, and what to do next. This focus comes from owner-led use, code/API probes and AI review, not recruited researcher interviews or validated demand. Interface completeness is not a scientific accuracy or impact claim.

## Implemented: work on the author's own investigation

| Researcher need | Current behavior | Important boundary |
|---|---|---|
| “Where do I start?” | `/workdesk` starts from a question and optional attachments; saved projects can be reopened. Examples are secondary and copy inputs explicitly. | A question/page load does not create a score, job or model call. |
| “Which material did you inspect?” | Immutable UUID/hash-bound CSV, Python and text/Markdown attachments, deterministic CSV profiles and AST-only adapter checks. | No notebook/PDF/repository retrieval. Latest CSV/Python are selected for a brief; arbitrary old-version selection is not implemented. |
| “Are you evaluating the intended task?” | Author-reviewed target, prediction time, population, unit, availability and column-role declarations; missing/unsupported gates. | Declarations are not independently established facts. CSV-only mode is a generated Random Forest baseline, not paper/model reproduction. |
| “Can you use my pipeline?” | Compatible `load`/`feats`/`claimed_eval` Python can be compiled as an explicit supplied-pipeline case after code acknowledgement. | Trusted local execution only; AST compatibility does not establish safety, scientific validity or enforced custom feature roles. |
| “What happens next?” | Local guide or optional bounded Meta guidance; a visible six-step plan is prepared from a saved brief. | Guidance is unmeasured and cannot accept facts, bypass a gate or trigger a run. |
| “Did the run use the reviewed inputs?” | Dispatch requires the current plan ID and matching compiled input hashes; material/brief/plan mutations are blocked during its active audit. | Chat does not change a frozen run; changed materials require a new brief and plan. |
| “What actually happened?” | Actual job events, provisional baseline, attempted-call ledger, final measurements/objections and matching exports. | Running/mismatched checkpoints are not final verdicts. A model-only no-flaw judgment is not empirical clearance. |
| “Can I continue and share this?” | Brief/plan/run history, project/run/view links, follow-up, verified measured/assessment ZIPs and a separate investigation-summary JSON. | Follow-up context uses the latest linked run and says so even when an older result is selected. Summary JSON is not a measured bundle; ZIPs include source/data. |
| “Where is the product evidence?” | `/evidence` separates recorded examples/saved jobs from own-data work; `/architecture` explains the actual model/guard responsibilities. | Animation is explanatory, not live agent conversation. |

Supported user uploads are UTF-8 `.csv` up to 5,000,000 bytes and `.py`/`.txt`/`.md` up to 256,000 bytes; at most 20 materials/project and 200 projects. CSVs need 30–20,000 rows, 2–1,000 columns and a nonmissing 0/1 target with at least five records/class. Generated predictors must be numeric and finite apart from the template's recorded missing-value replacement. The bundled public SECOM input import has a separate local-case size allowance, not a general user-upload extension.

Optional guidance has a persistent four-attempt/$0.25 reserved envelope per investigation. Each hosted audit has a separate four-attempt/$1 reserved envelope. Neither is a global/account cap or billed-cost guarantee. Outbound guidance acknowledgement is hash-bound to the authorized materials/brief/thread/latest run context; no raw CSV rows are sampled, but prompts/code/notes may contain private content.

## Finish the current release honestly

1. **Maintain current-source acceptance and publish deliberately.** The [Workdesk validation](reviews/2026-11-04-workdesk-validation.md) records completed internal/browser/package checks; the new source remains local. Future changes must recheck the own-data generated and supplied-code paths, material identity, stale-plan rejection, consent changes, active-run mutation locks, restart/history, selected/active run distinction and both export paths. Include desktop/mobile/keyboard behavior under the owner's current browser-check request. Packaging, manifests, documentation and source publication must describe these exact bytes; prior release checks do not automatically cover the rebuild.
2. **Keep historical evidence unchanged.** Preserve the planted SECOM flaw, changed-population caveat and Wonder dispute. Preserve original synthetic cohort failures and separate later confirmation/development repairs. A new intake/UI acceptance test is not a rerun of a scientific cohort or a new reliability score.
3. **Record the revised product demonstration.** Show a real question/upload, author decisions, reviewed plan, real progress and evidence. Recorded manufacturing evidence may illustrate the bounded method if labelled; it cannot substitute for proof that fresh inputs work. Deployment remains optional for the captured submission form; video recording/upload and final rules/submission checks are separate gates.

## Next: validate value before broadening scope

1. **Observe outside author tasks.** Recruit consenting researchers/students with permissible small binary studies. Record task completion, misunderstandings of declarations/abstentions, model-only judgments and exports. No outside researcher is currently recruited; time-saving and adoption claims remain unsupported.
2. **Freeze new evaluation cases and instrument bytes.** Define new supported, clean, incomplete and unsupported truths before inspecting outputs; retain every outcome. Separate protocol coverage, execution success, statistical behavior and model judgments. Use a matched one-planner baseline before claiming independent-critic benefit.
3. **Strengthen clarification provenance.** Add stable issue/question IDs, answer-to-source references and editable field-level proposal diffs. Current material references and author-reviewed revision hashes are useful, but do not establish sentence-level evidence for every assertion. A model cannot resolve an empirical concern through chat alone.
4. **Improve material/version selection and issue continuity.** Let authors deliberately select among older CSV/Python attachments, manage retained projects/materials safely, and compare issues across revisions. Preserve exact job snapshots and avoid treating changed populations/protocols as controlled score improvements.
5. **Make baseline semantics machine-readable.** Distinguish generated baseline, supplied-protocol execution, external-reference reproduction and no-skill reference. Neither a numeric baseline nor a `reproduced` flag should imply a paper result was reproduced without a supplied/verified external reference.
6. **Add read-only import adapters.** Start with notebook/repository or experiment-tracker metadata mapped to the supported contract, with author review. No arbitrary remote code should enter a public executor for convenience.

## Later: separate capability validation

| Candidate | User decision | Prerequisite before a claim |
|---|---|---|
| Row-aware paired inference and group/time evaluation | Whether a result generalizes across records, entities or periods | Stable prediction-row/group/time identity, declared population, validated resampling/interval coverage. Retain current inconclusive safeguards until validated. |
| Claim/evidence issue ledger | Which conclusion is supported, disputed or awaiting evidence | Every resolution cites an input/artifact/author source; opinion cannot substitute for the appropriate empirical test. |
| Local open-weight reasoning | Private research assistance without user-supplied hosted keys | Supported runtime/hardware and bounded latency/cost/new-case quality evaluation. Compatible endpoint transport alone is insufficient. |
| Literature/dataset specialists | Whether a claimed gap/source is credible | Retrieval, precise citations, licensing/privacy and separate interpretation/retrieval evaluation. Binary pipeline controls do not validate it. |
| Collaborative/hosted service | Reliable multi-person work on permissible studies | Authentication, isolation, quotas, lifecycle, provenance and verified deployment. The loopback workdesk is not a public execution service. |
| Aggregate experiment budgeting | Bound spending across multiple jobs/projects | Durable shared reservations/recovery and concurrency tests. Current per-guidance/per-job ledgers do not enforce a global billing ceiling. |

The general research principles remain train/evaluation separation, explicit scope and reproducible metadata. See scikit-learn's [common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) and [cross-validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html), and the NeurIPS [paper checklist](https://neurips.cc/public/guides/PaperChecklist). These principles do not validate interface preference.

Prioritize observed researcher decisions that fit the evidence contract and have bounded acceptance tests. External impact, broad accuracy and competition scores remain unclaimed.
