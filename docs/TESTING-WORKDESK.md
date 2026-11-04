# Test NullLab as a researcher — manual product checklist

Start at http://127.0.0.1:8099 . Keep the service running. Use the test materials under `test-materials/workdesk` in this repository. Expected behavior below is an engineering checklist, not a scientific reliability score. Start with the no-key path; Meta is a separate optional test. Keep each outcome, including failures.

## 1. Check the public explanation

1. Open `/`. You should see Hero, Method, Scope & Evidence and a compact footer.
2. The background should continue moving behind the hero. Click **Pause motion**, then **Play motion**. Navigation/text must remain usable.
3. Click **Explore the architecture** in Method. Follow **01 → 02 → 03 → 04 → 05 → 06 → 07 → 08 downward**. Each explanation opens below its selected step. **Next step ↓** and **↑ Previous step** move one step; Up/Down keys do the same when a step has focus. No stage should be to the right/left of another.
4. Click **Pause motion**. This only pauses the explanatory diagram. It does not start/pause an audit or use credits.
5. Open **Evidence Lab**. The constructed SECOM record must say RECORDED. Select **Clean twin**: it must say NOT TESTED/no measured control, without claiming clean clearance. This page creates no fresh experiment.
6. Choose **Go to Workdesk**. You should see your saved project list and question-first start form, not an automatically loaded manufacturing result. Use **New investigation** if an older project is open.

## 2. Start your own CSV study

7. Enter this question:

   > Does my validation procedure support predicting an event for new independent components using measurements available before the outcome?

8. Click **Attach materials**. Select `baseline.csv` and `notes.md` from `test-materials/workdesk`, then **Start investigation**. These are synthetic files for learning the workflow.
9. Open **Materials**. Confirm 60 rows, two columns (`sensor`, `event`), target candidate `event`, and both attachments. **Inspect material** must show file content/hash without executing Python.
10. In **Research**, ask:

    > What information is missing before we can evaluate this study?

    Leave **Assistant settings** on Local study guide. You should receive labelled deterministic guidance, not a fabricated experiment result. No classifier/model call should run yet.

    You can also supply explicit author facts in the thread, for example:

    ```text
    Target: event
    Population: independent_records
    Decision time: Before inspection
    All selected predictors are available at prediction time.
    ```

    Open **Review suggested brief details**. Each suggestion should show its source quote. **Use in draft** copies one field; **Copy suggestions to draft** copies the available proposals. Neither action saves a reviewed brief, trusts Python or starts a run. Confirm the draft yourself and use **Save brief & prepare plan**. For the missing-information test below, leave those fields explicitly unresolved instead.

## 3. Check the missing-information gate

11. Open **Study brief**. Select target `event`, pipeline **Create a baseline from my CSV**, and enter the decision below. Initially leave population **Not decided yet**, prediction time empty and availability **Not confirmed**.

    > Screen new independent components for an event, using the sensor measured before inspection.

12. Choose **Save brief & prepare plan**. Expect concrete questions/Needs information and a disabled **Review & run** button. No training or model call should occur. A text message alone must not silently accept the missing facts.

## 4. Review and run a real baseline

13. Complete the brief with these author declarations for this synthetic exercise:

| Field | Value |
|---|---|
| Outcome / target column | event |
| Which pipeline | Create a baseline from my CSV |
| Decision or research claim | Screen new independent components for an event, using the sensor measured before inspection. |
| Where must the result apply? | New independent records |
| When is the prediction made? | Before inspection, using the sensor already available for each component |
| Are predictors available? | I confirm they are available |
| Column roles → one row | One independent hypothetical component |
| Entity/group, time, exclusions | Leave blank for this two-column synthetic file |

14. **Save brief & prepare plan**. Inspect the new revision and concrete six-step plan. It should name the target, metric, supplied/generated pipeline, seeds 42/43/44 and any required split candidates. Read its static compatibility note and limitations; a candidate is not yet runtime-approved or measured. This independent generated study should become Ready to review.
15. Click **Review & run**. Check the revision/source summary. Keep **Rules & local execution · no key**, then click **Start this investigation run** once.
16. Open **Results**. Actual intake/baseline/hypothesis/guard/measurement events should update. While running, the headline must say in progress rather than presenting NOT TESTED as a final conclusion. The pending explanation and last recorded activity describe known progress, rather than inventing completed stages. If the small run finishes quickly, inspect its saved events; do not rerun just to catch an animation.
17. This generated model normally ends **NOT TESTED**: it ran a three-seed baseline but found no supported counterfactual to measure. That is a valid limited outcome. Inspect the starting score, limitations and zero provider attempts. It is not a clean bill of health and not a promised accuracy target.
18. Download **Assessment ZIP** (the unmeasured assessment) and **Result JSON**. The ZIP should include assessment.md, result/dependencies and exact input files, with explicit no-counterfactual wording. A measured Evidence ZIP must not be offered for a baseline-only result.

## 5. Test persistence, follow-up and revision

19. Reload the page. The project, attachments, brief, run and outcome should reopen. Use **Projects** on a phone or the desktop project rail to switch away and back.
20. Ask: **What can I conclude, and what remains untested?** The guide should describe the saved latest outcome with its scope; it must not invent a controlled improvement.
21. Attach `notes-revised.md`. Expect Review changes and an invalidated plan. Earlier result/exports must remain attached to their original revision. Review and save the brief again before any new run. Do not change the true intended population merely to pass a gate.
22. To check the generated-design boundary, choose **Future records** with the generated baseline and save. Expect a missing-time question plus the generated future-design scope gap, with no runnable plan. Restore **New independent records** only for this independent synthetic exercise, then save a new plan. No old result should be rewritten.
23. Optionally run the newly reviewed revision once. Switch between run buttons in Results and verify each shows its own revision/export. Follow-up guidance uses the latest run; selecting an older run must show that context boundary.

## 6. Test an uploaded existing pipeline and a measured control

24. Choose **New investigation**. Enter:

    > Does whole-dataset feature screening affect validation accuracy in this supplied pipeline on independent recordings?

25. Attach both `supplied-pipeline/data.csv` and `supplied-pipeline/train.py` from the test kit. Choose **Start investigation**.
26. In Materials, expect 176 rows and 81 columns. Inspect the Python. It defines load, feats and claimed_eval and screens features using all labels before validation.
27. Review this brief:

| Field | Value |
|---|---|
| Target | event |
| Pipeline | Use my supplied Python pipeline |
| Claim | Predict quality events for independent recordings from measurements available before inspection. Examine whether label-based screening before validation changes accuracy. |
| Population | New independent records |
| Prediction time | Before inspection, using measurements already available for each recording |
| Availability | I confirm they are available |
| One row | One independent synthetic recording |
| Code acknowledgement | Check only after reading and trusting the supplied local Python |

28. **Save brief & prepare plan → Review & run → Rules & local execution → Start** once. This runs the supplied code, not the generated Random Forest.
29. Expect a typed fold-local feature-screening control, guard results, three-seed measurement and per-seed uncertainty. In the retained acceptance run this known fixture measured **0.610 → 0.559 accuracy, INCONCLUSIVE**. Preserve your actual outcome; scores are not a pass target, and a library/runtime difference should be recorded rather than rerolled.
30. Expand **Recorded reviews & limitations** and **Tested control & input identity**. An unmeasured outcome should instead use a proposed/control-status label. Local rules may contain no model critique; the UI must not invent one. If recorded model reviewers disagree, inspect both reasons rather than treating them as consensus.
31. Download **Evidence ZIP**. Inspect exact uploaded data/code, tested control/patch, predictions, environment and result. Reopen it through Evidence Lab → **Return to the evidence**. Its headline, numbers and job ID must match. Unrelated manufacturing facts should not appear above this saved own-data result.

## 7. Optional acknowledged Meta paths

32. In a supported saved investigation, open **Assistant settings → Ask Meta to help frame this question**. Read the outbound scope and acknowledge it only if appropriate. Send a question. Pending feedback should remain visible until the request returns. The response should be labelled model guidance with material filenames for validated references, not measured evidence. Source quotes can populate a reviewable draft; they must not silently overwrite a saved declaration. Already confirmed brief fields should be supplied as resolved context rather than repeatedly requested. Its allowance is four attempts/$0.25 reserved per investigation; actual billing can differ. Changing materials/thread/brief/run context must require renewed acknowledgement.
33. For a new explicitly reviewed plan, choose **Meta planner + optional independent critic** in Review & run. Keep **Ask an independent methodology critic** checked if testing Wonder. Read/acknowledge what leaves the machine, then start once. The selected run should show requested Meta/independent review even while its local baseline is executing and zero provider attempts have been recorded. Per audit default: four attempts/$1 reserved estimate. Inspect actual model/attempt records and retain no-flaw, disputed, failed or unmeasured outcomes as they occur. No specific verdict is guaranteed.
34. If the Meta option is disabled, the server/provider configuration is not enabled for that session. The no-key product should still work. These guide steps do not prove local open-weight reasoning quality.

## 8. Error handling, cancellation and mobile

35. In a separate test investigation, attach `unsupported.json`: expect a useful unsupported-file error and no execution/model call. Attach `invalid-target.csv`, then attempt a generated brief with target event: expect a binary 0/1 validation error, no runnable plan, no silent yes/no recoding.
36. For any supported run that is still active, click **Cancel active run** once. Cancellation is cooperative between stages; it may not beat a fast completion and does not prove remote provider cancellation. The displayed status/export must reflect the actual outcome. Do not launch repeated jobs just to force a cancelled state.
37. Open the local app in a narrow desktop window (or phone emulation), around 390px and 320px wide. **Projects** should open/close; Research, Study brief, Results and Materials must remain reachable. Inspect a material dialog and close it with Escape/the close button. Long content scrolls inside its view without horizontal page clipping. A physical phone cannot access the computer's 127.0.0.1; this local-only server is not a public mobile deployment.
38. Open Architecture at the same width: steps must stay 01–08 vertically, explanations underneath, arrows downward. Test Next/Previous and pause. The desktop/mobile controls should preserve the same selected step.

## 9. Check required group/time controls before spending credits

For a repeated-entity study, declare **Previously unseen entities** and the true entity column. Review the static compatibility card before **Review & run**. An adapter exposing `load`, `feats` and `claimed_eval` is only structurally compatible; that does not prove its required intervention is expressible.

In particular, a splitter constructed inside `claimed_eval(df, seed)` cannot receive a group vector merely by naming a column. The current CV template needs an explicitly bound helper such as `cv_eval(X, y, seed, groups)`, called from `claimed_eval` with the declared `df[entity_column].to_numpy()`. Adding `groups=None` without that binding is insufficient. An impossible required operation must produce a blocked plan and actionable explanation, with no new baseline, job or audit-provider call. Missing source functions, invalid target/data or stale source/material identities should also fail before dispatch.

This is static source/operation/data validation, not execution of arbitrary uploaded Python. Even an applicable AST candidate must later pass runtime provenance, model fidelity and data-sufficiency checks. The current group trace path expects numeric group metadata; string IDs can fail its numeric conversion. Keep group identifiers out of predictors. Any reviewed one-to-one numeric encoding must preserve original IDs/mapping and become a new input revision; do not silently recode data or relabel an earlier failed result.

The retained first repeated-rig audit (`b55538e3…` / `3bd55513…`) remains **UNSUPPORTED** with a 0.974 starting accuracy and no grouped comparison. Its separate static follow-up and later adapter engineering checks do not change that audit or rescore a cohort. A ready plan promises neither runtime acceptance nor a scientific conclusion. Group/time comparisons remain descriptive; row-bootstrap intervals do not establish uncertainty for new entities or future periods.

The explicit [numeric-metadata recovery kit](../test-materials/workdesk/grouped-adapter/numeric-metadata/README.md) is a known synthetic engineering revision. Its one retained Meta audit `745ca3a6…` measured **0.974 → 0.290 accuracy, INCONCLUSIVE** on three seeds. Use its saved project `715f8e22-536d-4e4a-9f3c-ee13795a72c1` to inspect the actual evidence without another paid run. The source kit preserves original identities/mapping and exact baseline-equivalence checks. It is not a fresh scientific cohort or a performance target for future runs.

On desktop, selecting **Results**, **Study brief** or **Materials** should now expand that task across the main work area. **Research** retains the conversation and context columns. Tab switches must preserve unsaved form values. A completed run for the current brief shows **Evidence saved** or **Assessment saved**; a new brief still needs its own plan and run. For the grouped result, the descriptive-inference explanation must be visible beside the numbers even if a model critic accepted the interpretation. Ask “What can I conclude from the saved run?” in the default no-key guide: it should report the actual verdict and the repeated-entity uncertainty limit.

## Record what you found

For each issue, note: step number, project/run ID, files used, expected versus actual behavior, exact message, screenshot and whether local rules or Meta was selected. Preserve the result and ZIP. Never report NOT TESTED as a product crash or clean scientific clearance; distinguish a supported scope limit, missing information, failed execution and a measured conclusion.

The test kit and this guide cover the current supported product. General papers/notebooks/literature discovery, arbitrary hostile hosted code and validated outside-researcher impact remain outside this release. No new scientific evaluation or paid inference was performed merely to prepare these steps.
