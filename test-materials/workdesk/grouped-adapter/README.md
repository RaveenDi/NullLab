# Known synthetic grouped-adapter recovery

This is a development fixture derived from the retained 4 November repeated-rig session. It is **not a new scientific cohort, outside-researcher validation, or a replacement for the original UNSUPPORTED audit**.

**Current runtime limitation:** the one retained deterministic guard check rejected this fixture because its string `device_id` values could not be converted to the frozen guard's numeric metadata representation. Baseline vector equality and AST applicability passed, but runtime support did not. Do not spend credits on this revision expecting a grouped measurement. Any explicit one-to-one numeric metadata encoding must be reviewed and retained as a separate input revision, with its mapping and another engineering check.

For a new investigation, attach **data.csv, train.py and notes.md**. Read and trust the Python before local execution. Do not upload original_pipeline.py alongside train.py: it is a reference for the original unsupported function shape. The Workdesk uses the latest attached Python file.

Use target `event`, intended population **Unseen entities**, entity column `device_id`, and prediction time **Before inspection**. The four numeric predictors are simulated pre-inspection measurements; `device_id` is metadata. Confirm these declarations only for this synthetic example.

The adapter extracts the unchanged random-row CV body into `cv_eval(X, y, seed, groups)`. `claimed_eval(df, seed)` explicitly supplies `df['device_id'].to_numpy()`. It preserves the original feature list, Decision Tree, hyperparameters, three stratified random-row folds, metric and seed. The typed candidate can replace the helper's splitter with grouped validation. No original material or outcome was modified.

Baseline vector equality is checked on seeds 42, 43 and 44 by `tests/test_workdesk_protocol.py`. Fixture preparation itself performs no grouped measurement. Compiler applicability is an early mechanical check; runtime provenance, fidelity, data sufficiency and scientific interpretation remain separate gates. A local rules run may abstain because local planning does not propose group controls. Acknowledged Meta planning may propose a control or abstain; neither a particular verdict nor a score is promised.

`PROVENANCE.json` records exact input/source hashes and the baseline-equivalence check status. Keep all new outcomes and record a separate investigation/revision. Do not rerun the original audit until a preferred conclusion appears.
