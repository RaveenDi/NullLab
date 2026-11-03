# NullLab implementation checklist

Owner authorization, 3 November 2026: address the full independent audit, including code, documents, user experience, minor and major issues; remove the civil-war submission example; target evidence consistent with 8/10 in every rubric category. Track: Indie Developer. No external researcher available. This document records the ordered work; unchecked items are not completed functionality.

The owner requested architecture-audit completion before implementation. Updated instruction: **do not perform a browser walkthrough; defer the full offline test suite until after the rebuild**. Focused safe architecture probes and targeted checks are distinct from that deferred suite. Existing authorization covers the proposed local work, so no repeated approval is needed for ordinary fixes.

**Revised execution order (supersedes the original phase sequence below):**

1. Close architecture review and record reproducible findings (original review plus completion addendum).
2. Capture a recoverable baseline; retire the civil-war submission evidence (T01–T04).
3. Establish evidence identity, honest verdicts, export integrity and result schema validation (T10–T14, T53–T54).
4. Prove the replacement manufacturing case (T05–T09) using validated measurements.
5. Unify the engine and isolate per-run provider/job state (T15–T18, T55–T56).
6. Fix portable configuration, model accounting, replay and recovery (T19–T22, T57).
7. Harden execution/privacy (T23–T27); complete the scientific instrument (T28–T32).
8. Build guided intake, UI and exports/CI (T33–T38), then bounded collaboration (T39–T41) and no-key modes (T42–T44).
9. After the rebuild, perform fresh-install/internal workflow verification and the full offline suite (T45–T46). Browser walkthrough is excluded by owner instruction.
10. Finalize documentation and submission evidence (T47–T52); documentation for each changed contract is updated during implementation too.

**Progress:** Architecture review closed. V2 core, author UI/data adapter, portable provider, typed controls, evidence/export integrity and local execution safeguards are implemented and verified. Current UI/submission evidence is manufacturing only. The explicit v2 source archive excludes historical case/data/results; original history remains locally traceable. A localhost server is running on port 8099. Recovery snapshot remains under ignored `out/audit-baseline/`.

The full offline run finished with 474 passed, two legacy-expectation failures and one optional historical replay skipped; both failures were corrected and their targeted reruns passed. Latest current-engine/API checks: 29 passed. Ruff and freeze verification pass. This is combined full-run plus repair-rerun evidence, not a claim of a subsequent single all-green full run. Browser walkthrough is excluded.

A real public-data Meta audit used three attempts, reserved estimate $0.662912. Spark proposed the control; Wonder disputed the interpretation. Current evidence retains that dispute. The owner subsequently authorized further Meta spending: a six-case pilot used 15 attempts and $2.070315 reserved estimate, with all original outcomes retained. A contract bug blocked all three flawed-case controls; post-fix reuse of the stored plans measured two inflation findings and one inconclusive result, explicitly development evidence. The eight-case follow-up also completed: 15 attempts, $2.44894425 reserved, one of two supported flawed controls measured and disputed. Its additional defects and separate development repairs are documented below. A synthetic CSV task walkthrough using the installed package completed in 7.59 s with no model calls; this is internal validation, not user-time-saved evidence.

Unchecked tasks remain open. Two fixed internal cohorts are now reported with original failures and separate post-fix regressions; they do not validate generalization of the subsequently repaired instrument. Generalized group/time uncertainty, a fully matched comparison, measured critic benefit, actual Glimmer performance, broader hosted inference, final video, logged-in rule checks and publication are not complete. The prepared source ZIP, read-only demo ZIP, wheel, evidence ZIP and submission drafts make the next release decisions concrete.

**Additional architecture findings incorporated:**

- [x] T53. Validate worker results before scoring: schema, exact one-dimensional equal vector lengths, finite values, legal metrics/classes, seed/config completeness and row identity where required. Reject malformed output rather than relying on NumPy broadcasting.
- [x] T54. Require original run manifests at export; distinguish audited input bytes from exported/redacted bytes, and label changed inputs as a mismatch rather than inventing audit-time provenance.
- [x] T55. Replace process-global provider/ledger monkeypatching with explicit per-job dependencies; verify overlapping jobs cannot double-book, miss, or cross-route calls.
- [x] T56. Allocate unique run/job paths and atomic checkpoint writes; avoid shared `r1.json`/`hybrid.json` overwrites. Keep one mutable data frame from silently contaminating other experimental configurations.
- [x] T57. Fix installed-transport replay recursion, and verify model-role selection and replay exhaustion semantics through the supported adapter.

**Recommended development model:** GPT-6.1 Sol with Extra High (`xhigh`) reasoning for the core repair, methodology and final review; High for routine UI/docs work. This is a recommendation, not a claim that this chat's model setting has changed. Work through one stage at a time; use a narrowly scoped independent reviewer where it adds meaningful verification. Do not launch a broad parallel editing fleet.

**Application models:** keep Meta Muse Spark as the principal planner. Evaluate Wonder as an independent methodology critic. Add a real configurable open-weight path for Muse Glimmer, measured separately. Do not replace the submitted application's Meta reasoning with the development assistant. Verify provider availability, current options and the authorized spending ceiling before paid test runs.

**Replacement demonstration selected for feasibility testing:** semiconductor manufacturing quality evaluation on the UCI SECOM dataset. The official source describes 1,567 examples, 591 features, missing values, pass/fail labels and timestamps, under CC BY 4.0: https://archive.ics.uci.edu/dataset/179/secom . Build an explicitly labelled benchmark pipeline on these real records with a leaky variant and a valid clean twin. This is not an allegation against the dataset authors or an existing publication. No numerical effect is promised before measurement. SECOM becomes development/demo evidence once used to build the product; independent tests must use different case families.

The intended demonstration: a quality-prediction evaluation looks convincing; NullLab traces test-label influence through preprocessing/feature selection or resampling, validates a minimal control, executes it, quantifies the change, and avoids accusing the clean twin. Show imbalance-aware metrics and a trivial baseline; high accuracy alone is not impressive on this dataset. Pass/fail screening is the initial task. Do not claim future defect forecasting unless a defensible prediction-time contract and temporal evaluation are implemented.

## Ordered work

### 1. Establish a recoverable baseline and retire the old example

- [x] T01. Record current working-tree changes, source revision, frozen manifests and test commands. Preserve the previous suite's unknown status; defer its full rerun/failure resolution until after the rebuild, per owner instruction.
- [ ] T02. Preserve an immutable historical snapshot, then retire civil-war cases, primary-result claims, UI references and case-specific dependencies from the active submission. Do not relabel those results as a new domain or erase their provenance.
- [x] T03. Remove topic/author scrubbing used to conceal the retired domain. Rebuild the current evidence manifest and separate historical experiments from the supported product.
- [x] T04. Refresh current project instructions, decision log and documentation index; remove obsolete finalist/path claims and correct SLT/ET conversions. Record confirmed Indie track and owner authorization.

Gate: no active demo or score claim relies on the retired evidence; historical records remain distinguishable and intact.

### 2. Prove the replacement example before designing around it

- [x] T05. Obtain SECOM from its authoritative source, record attribution/license, checksum and dataset schema, and validate missingness/labels/timestamps.
- [x] T06. Define the user, target, information available at prediction time, evaluation population, metric, baseline and admissible controls before testing outcomes.
- [x] T07. Create a modest deterministic leaky/clean pair using supported mechanisms; independently verify the intended flaw and clean control. Label planted flaws explicitly.
- [x] T08. Measure baseline reproduction, controlled effects, uncertainty and runtime. Show a simple majority-class baseline and imbalance-aware performance. Log failed or weak attempts; never cherry-pick repetitions to manufacture a dramatic result.
- [x] T09. Accept the example only if the result is understandable, useful, scientifically defensible and practical for a demo. If it fails, record why and select a new legitimate example under a new protocol rather than escalating leakage until a preferred number appears.

Gate: a measured, explainable manufacturing example and a clean twin; no fabricated effect sizes or implied real deployment benefit.

### 3. Fix evidence identity and verdict semantics

- [x] T10. Bind all cached/replayed results to source, dataset, excerpt/claim, intended-use contract, patch, model/prompt, seeds, dependencies and instrument version.
- [x] T11. Make replay explicit with a run ID; invalidate mismatches; make fresh mode bypass all result reuse, including recorded-model selection.
- [x] T12. Replace ambiguous conclusions with evidence of inflation, no effect detected for tested controls, inconclusive, not tested, unsupported and model-only assessment as appropriate.
- [x] T13. Prevent mixed seed results, referee disputes and model no-flaw proposals from becoming verified-clean outcomes. Carry the distinction through CLI, UI, exports and CI.
- [x] T14. Add meaningful regression tests for changed-input reuse, stale provenance, uncertainty/dispute handling, failure propagation and zero-tested coverage.

Gate: the product cannot present old numbers as new evidence or present missing evidence as scientific clearance.

### 4. Ship one supported engine

- [x] T15. Create one versioned product runner around the typed edit contract, behavioural checks, preflight, executor, transport and bounded repairs; preserve legacy runners separately.
- [x] T16. Support zero/one/multiple legitimate interventions without forcing two flaws. Publish a capability matrix; unsupported edits must stop explicitly.
- [x] T17. Route CLI, API/UI jobs, CI, reports, bundles and patch exports through that runner and one result schema.
- [x] T18. Make baseline reproduction a required prerequisite for attributing a measured change; retain original-to-adapted code mapping.

Gate: evidence about the current engine describes the actual path users run.

### 5. Remove workstation dependencies and correct model accounting

- [x] T19. Replace private battle-station dependence with repository-owned configuration and bounded budgets; use supported environment/.env handling without private paths.
- [x] T20. Implement configurable base URL, model per role, authentication behavior and provider capabilities; do not silently ignore configuration.
- [x] T21. Separate historical research-run caps from current job/user budgets. Record attempted, successful, failed and billing-unknown calls; retain provider usage when available and clearly label estimates.
- [ ] T22. Add timeouts, bounded retry/backoff, cancellation, progress and resumable job records where needed. Verify credential redaction and no secret inheritance.

Gate: a fresh clone can use its documented provider without the owner's machine or sibling repository.

### 6. Harden execution and privacy

- [x] T23. Restrict file writes to the disposable workspace; distinguish read-only dependencies from writable paths; review all worker entry points and relevant filesystem operations.
- [ ] T24. Enforce resource limits and cleanup consistently; make security-critical configuration fail closed. Test the security contract with safe temporary fixtures.
- [x] T25. Implement and verify isolated factorial workers before offering arbitrary hosted code execution. If verification is incomplete, keep execution local/trusted and hosted examples curated; expose that boundary in the product.
- [x] T26. Add an outbound-data manifest/preview, including sampled rows, source and excerpts. Default confidential inputs away from Contributor mode; document provider training/retention distinctions accurately.
- [ ] T27. For any hosted execution, add required authentication/access controls, quotas, input limits, job isolation and error handling; inspect dependency/license and secret exposure risks.

Gate: deployment capabilities match a tested security boundary, and users can understand what leaves their machine.

### 7. Improve the scientific instrument

- [x] T28. State the estimand and control assumptions; distinguish protocol changes from pure causal claims about leakage.
- [ ] T29. Preserve row IDs/group/time metadata and use paired or structure-aware uncertainty where justified. Validate interval behavior on controlled cases; avoid claiming unsupported coverage.
- [ ] T30. Make reading-only and execution comparisons match model, input, methodology instructions, allowed answers and practical budget. Separate initial judgment from the effect of execution.
- [ ] T31. Freeze the new engine and prepare a small fresh evaluation spanning flawed, clean-but-suspicious, ambiguous and unsupported cases, with truth hidden from product agents.
- [x] T32. Report case-family denominators, coverage, abstentions, false findings, invalid controls, latency and cost; keep every scheduled outcome. Separate development, demo and test evidence. The original pilot and post-fix regression have separate machine scores and reports; wider evaluation remains T31.

Gate: current claims are supported by a fresh pilot of the shipping engine, with limitations stated and no retrospective rescoring of old experiments.

### 8. Build the actual author workflow and redesign the UI

- [x] T33. Add guided intake for one supported local/sklearn pipeline: code, data, claim, target, intended use, split and groups/time fields. Explain incompatible inputs before execution.
- [x] T34. Build the complete journey: intake -> baseline reproduction -> hypothesis/control -> checks -> execution -> evidence -> usable export.
- [x] T35. Replace the replay-led landing experience with a clear author task and manufacturing example. Show live, rules-only, recorded, model-only, failed and unsupported states distinctly.
- [x] T36. Add useful progress/cancellation, accessible responsive layouts, readable metrics, evidence/source links, disagreements and concise limitations. Remove exaggerated FALSIFIED language.
- [x] T37. Make the patch's application target explicit and preserve source mapping; distinguish JSON evidence from a rerunnable ZIP. Verify exports from a clean environment.
- [x] T38. Make CI communicate audited/total coverage and configurable strict failure on unchecked/disputed cases; verify the default workflow checks meaningful inputs.

Gate: a new supported case can traverse the real product, and the output can be inspected and applied without undocumented intervention.

### 9. Add bounded collaboration that earns its complexity

- [x] T39. Add an independently prompted methodology critic with access to relevant original evidence, initially separated from the planner's conclusions. Define roles, permissions and a shared structured evidence record.
- [x] T40. Permit a bounded challenge/revision round; resolve disputes through tests or an unresolved status. Deterministic code computes statistics; agent consensus is not validation.
- [ ] T41. Run a matched ablation against the one-planner engine. Retain or prominently claim collaborative benefit only if it improves valid findings or reduces harmful errors at a reasonable measured cost.

Gate: collaboration has observable value, and the UI shows useful challenges rather than simulated agent chatter.

### 10. Deliver honest no-key access

- [x] T42. Preserve the functional rules-only path with accurate coverage and unknown states.
- [ ] T43. Implement the local OpenAI-compatible provider route and test Muse Glimmer on available suitable hardware or an institution/provider endpoint. Measure memory, latency, schema/control fidelity and task outcomes.
- [ ] T44. Provide operator-funded no-user-key access for bounded public examples if funded and securely deployable. Keep optional BYOK separate. Do not market untested local reasoning as shipped.

Gate: each offered mode actually works and clearly identifies who supplies compute, what it can evaluate and its data boundary. An unvalidated mode remains disabled/documented as pending.

### 11. Verify the whole product and update all documentation

- [x] T45. Perform a fresh-install walkthrough and professor-style adversarial review on a new supported case. Measure setup friction, completion and export usability; label this internal AI evaluation.
- [x] T46. After the full rebuild, resolve baseline/new failures and run the full offline test suite plus appropriate integration, security, frontend and smoke checks. Do not perform a browser walkthrough (owner instruction). Verify supported platforms instead of implying untested cross-platform support.
- [x] T47. Rewrite README, architecture, setup, configuration, usage, privacy/security, deployment, result cards, limitations, licenses and contribution guidance against verified behavior; audit links and examples.
- [x] T48. Maintain a compact evidence/decision ledger and reconcile all public numbers, screenshots, UI text and submission claims with current artifacts.

Gate: tests and documentation agree with the exact build being demonstrated; remaining limitations are visible rather than hidden in old notes.

### 12. Demonstration, release and scoring review

- [ ] T49. Produce a three-minute storyboard showing the input, suspected flaw, Meta-driven control, real execution, measured effect, clean twin and export. Record actual behavior, clearly label time compression/replay, and avoid unsupported customer/impact claims.
- [ ] T50. Prepare public demo/repository instructions, submission answers, architecture visual, attribution, build-during-event boundary and verification checklist. Confirm current logged-in rules and final links.
- [x] T51. Reassess each rubric category against evidence, not feature count. Run a concise independent challenge review and fix the highest remaining blocker before cosmetic additions.
- [ ] T52. Complete the authorized release workflow with a recoverable version, verified links and monitoring plan. Publishing/submission actions should be concrete and reviewable; do not infer authorization to send messages or accept legal terms from a code-fix request.

## Evidence target for 8/10 in each category

| Area | Evidence we should be able to show |
|---|---|
| Impact | One clear author problem, a usable new-input workflow, a meaningful manufacturing demonstration and honest limits on adoption evidence |
| Meta tooling | Spark makes legitimate testable decisions; critic/open-weight capability has measured purpose where shipped; model roles and traces are visible |
| Technical depth | One portable engine, correct evidence identity/verdicts, tested execution boundary, matched fresh pilot, trustworthy cost/provenance and usable exports |
| Demo | Clear input-to-evidence story, visually readable measured change, clean twin, working interaction, and verified publicly accessible deliverables |

These are evidence targets, not guarantees about judges. Missing external user validation remains a limitation even if every engineering task is complete. If time is constrained, finish the trust, real-workflow and demonstration gates before broadening domains or adding more agent roles. The score target does not authorize changing scientific acceptance criteria to obtain flattering outcomes.


## Final bounded review and release status

The independent v2 reviewer completed successfully. Its four findings (nested export controls, cancellation boundaries, negative-effect labels and active-job UI identity) were fixed and independently reverified. The review records current source hashes. Focused repair suite: 19 passed, plus an independent cancellation-before-retry probe. The current UI also has a Node DOM-mock regression; this is not a browser walkthrough.

Current artifacts: `out/nulllab-public-demo.zip` (view-only public recordings), `out/nulllab-v2-source.zip` (explicit source/data allow-list; historical evidence excluded), `out/dist/nulllab-0.2.0-py3-none-any.whl`, and submission drafts. No Git commit/push, deployment, video publication or submission was performed.

Eight-per-category remains a target, not an achieved score. Impact lacks external-user evidence; Meta tooling lacks matched critic/local-model evaluation; technical depth lacks verified general group/time inference and hosted isolation; Demo lacks a recorded public video and deployed public URL. Implemented scope is usable and internally verified, with these release/research gates still open. Do not mark every checklist item complete merely because the core works.

The eight-case fixed follow-up and coordinator's subsequent repairs are recorded in [EVAL-V2-FOLLOWUP](../EVAL-V2-FOLLOWUP.md). The case-preparation agent hit its usage limit after writing the frozen cases/source snapshot; the coordinator validated the artifacts and completed execution/adjudication. New explicit missing-information/unsupported outcomes, retained initial objections and safe scaler tracing passed 37 focused checks; CI/JS passed 11. See [remaining priorities](../FINAL-PRIORITIES.md) before adding features or making release claims.

The final source subset also built a wheel and passed all 32 included product tests after extraction. The no-skill ROC-AUC reference is correctly 0.5 rather than majority-class accuracy. Installed final-wheel bytes match current core code, and its intake/abstention/export smoke checks pass. Historical full-run and focused repair results remain separately described; no claim that the entire historical suite was rerun all-green is made.

## Researcher workflow follow-through — 4 November 2026

The owner's requested discussion room reviewed actual code/API behavior and implemented study declarations/roles, pre-training gates, a recorded evidence room, clarification into new input-bound versions, saved audit recovery, descriptive comparison and separate unmeasured assessments. Coordinator integration closes the partial agents' work. Full-template matching, malformed-review abstentions, response races, interrupted-checkpoint display/comparison and a transient Windows sharing failure were repaired with retained evidence. Latest checks: 88 integrated; 12 CI/guard compatibility; 81 from extracted source. Installed-wheel baseline and both export paths pass. See [research-room decisions](research-room/DECISIONS.md), [validation](../RESEARCH-WORKSPACE-VALIDATION.md) and [roadmap](../RESEARCHER-ROADMAP.md). These do not close external-user, fresh-quality, public video or publication/submission gates.
