# Author workflow

Start the localhost workspace using the README. Select a manufacturing example, or open **Prepare data or revise a study brief** to create a CSV case. Describe the decision, when it happens, which population the predictions must apply to, and whether the selected predictors are available then. Entity/time fields are metadata; exclude post-decision columns. These declarations are not independently verified facts. Review the claim and execution mode before running.

Unknown decision time, population or availability asks concrete questions before any fitting/model dispatch. A complete unseen-entity or future-record request is unsupported by the generated random-row adapter. Represented-entity baselines remain descriptive. Do not change the declared population merely to pass a gate: supply a separately validated pipeline when the real question needs group/time evaluation.

The review room shows actual deterministic checks and recorded model contributions. It does not simulate conversation or vote on scientific truth. Baseline-only outcomes show seed scores without implying a controlled effect. Saved audits can be reopened after reload, including by `?job=UUID`. Viewing an older result does not change the active audit being polled or cancelled.

Use **Answer questions** or revise the selected generated case's brief, then **Save a new case version**. The same CSV bytes are reused; parent input hashes, a linked audit manifest when available, reason and timestamp are recorded. Run the new case to evaluate it. Prior inputs and results remain unchanged. Custom Python is not silently regenerated. Comparison verifies saved identities and lists metadata differences; it does not compute a causal ranking or a new statistical test.

For an existing trusted Python pipeline, the case folder contains `train.py`, `data.csv`, `excerpt.md`, optionally `case.json`/`contract.json`. A supplied `expected_score` and `score_tolerance` in case.json are checked before planning; mismatch stops attribution. Without a numerical reference, the baseline is an execution of supplied code, not verification of a published number. Required functions are `load(path)`, `feats(df)`, and `claimed_eval(df, seed)` returning one-dimensional equal-length true labels and predictions. AUC metrics require both classes as 0/1. The current instrument accepts at least 20 rows with five per class and a CSV up to 50 MB. Arbitrary project/notebook conversion is not automatic.

```powershell
python -m agent.engine CASE --out out/audit
python -m agent.engine CASE --preview
python -m agent.engine CASE --live --critic --out out/live-audit
python -m agent.intake DATA.csv --target defect --intended-use "Screen independent parts" --decision-time "Before final acceptance" --population independent_records --availability confirmed --entity-column part_id --exclude post_test_status --out examples/my-case
python -m agent.ci_check examples/secom --threshold 0.05
```

The CSV adapter accepts 30–20,000 rows, numeric selected predictors, a binary 0/1 target and a 5 MB file. Text metadata is allowed. At least five records per class and one predictor are required. It creates a new fixed Random Forest baseline with constant zero replacement of missing predictors, not a reproduction of a user's original model. Review whether zero is appropriate. Omitting the brief fields saves an unresolved case that will ask questions. The example CLI metadata/exclusion names must exist in your CSV. Generated-source AST matching enforces the complete template; edited code must use an explicit custom adapter with unverified roles.

No matching rule -> NOT TESTED. A model that proposes no flaw -> MODEL NO FLAW, without empirical clearance. Missing predictor timing or intended population can produce NEEDS INFORMATION with concrete questions. A known concern outside the edit list produces UNSUPPORTED with scope gaps. A consistent positive tested effect -> INFLATED. Mixed or failed measurements -> INCONCLUSIVE. Reviewer objection -> DISPUTED; unresolved objections survive an early no-flaw answer. A consistent score increase is CONTROL SCORE HIGHER, not no effect. No-effect results apply only to the tested controls.

Every job writes `result.json` and immutable input snapshots. `agent.engine.export_bundle(path_to_result)` creates a ZIP for measured v2 results, verifying input/control identity and refusing credential-like text. The ZIP includes inputs, controls, patch, dependency versions and result. Inspect executable code before reproducing. The patch replaces the original file with the normalized compiled control; it is not a formatting-preserving small edit. The result records conditional intervals, not universal statistical coverage.

`agent.engine.export_assessment(path_to_result)` creates a separate assessment ZIP for terminal unmeasured outcomes with verified snapshots, including gated and baseline-only runs. It includes a readable assessment, exact inputs, result and dependency versions. It states that no counterfactual was measured. Both ZIP types contain data and executable source; review before sharing. Extra untracked files beside the snapshot are excluded. A failed run without an input identity cannot export an assessment.

CI returns 1 for a measured effect above threshold, 2 for failure or unchecked/disputed coverage, and 0 for completed checks below threshold. `--allow-unchecked` selects report-only coverage behavior. Legacy `agent.audit` is a historical report reader; historical results without an audit-time manifest cannot be exported as new evidence.
