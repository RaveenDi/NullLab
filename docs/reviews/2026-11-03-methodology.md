# Independent methodology review — 3 November 2026

Scope: scientific claims, evaluation design, leakage, statistical inference, and the gap between evaluated runners and the product. Read-only inspection of source, preregistrations and saved results, plus a small offline verdict check. No model calls, experiments, frozen files or recorded results were changed. This is a review, not a new benchmark.

## Assessment

NullLab has a credible narrow core: propose an evaluation control, constrain the edit, execute it, and expose a measured score difference with provenance. The evidence supports engineering feasibility on selected examples. It does not yet establish general research-evaluation competence, autonomous discovery of unknown flaws, a calibrated clean bill of health, or an advantage from multiple collaborating agents.

The best scientific next step is an independent, small, locked evaluation of the actual product path, with a matched reading-only baseline. More repeats of the same known examples would add much less information.

## Findings by priority

### P1 — Saved evidence can be applied to changed inputs

`agent/hybrid.py:143` (`default_measure`) checks generated patch hashes but does not check the dataset hash; its docstring acknowledges this. The same code with changed `data.csv` can reuse old measurements. `agent/hybrid.py:162` (`find_recorded_spark`) selects a successful run by the case directory's basename inside the repo, without matching source, data or claim hashes. It also searches for a successful record rather than explicitly selecting a particular repeat, which makes this demonstration replay inappropriate for estimating operational reliability.

**Impact:** a researcher can change their data and receive a believable number from a different experiment. A provenance label saying "recorded" does not establish that the recording matches the current inputs.

**Repair:** use a manifest covering original code, data, claim, patch, environment and instrument version for every result lookup; refuse a mismatch. Replay should be an explicit mode with an explicit run ID. Preserve old files as historical evidence. The G9 execution cache already has a substantially stronger key; the problem is specifically the product-level stored-result lookup.

### P1 — An unresolved measurement becomes `NOT INFLATED`

`agent/audit.py:61` and `g4.py:163` use majority voting across three seed interval signs. One positive, one negative and one zero sign returns `mixed`. `agent/hybrid.py:270` maps every non-positive category, including `mixed`, to `NOT INFLATED`.

An offline call reproduced:

```text
per-seed signs ['+', '-', '0'] -> mixed -> NOT INFLATED
```

Even a zero sign means failure to establish an effect for these controls, not proof of no leakage. The narrative report is more careful than the top-level verdict. `sandbox/verdict.py` describes a different, older three-seed agreement rule; README references to it do not describe the actual hybrid/factorial verdict path.

**Repair:** distinguish `EVIDENCE_OF_INFLATION`, `NO_EFFECT_DETECTED_FOR_TESTED_CONTROLS`, `INCONCLUSIVE`, `NOT_TESTED`, and `MODEL_NO_FLAW_PROPOSED`. Do not retrospectively change frozen run scoring; implement a new presentation/product contract and label it.

### P1 — The latest evaluation does not evaluate the public hybrid engine

`agent/hybrid.py:179` imports the G5 planner and static fidelity guard. Its production path does not use the G9 typed DSL, behavioural guard, transport and repair instrument. `docs/ARCHITECTURE.md` explicitly documents this separation. The G5 prompt (`agent/factorial_g5.py:14`) asks for TWO suspect steps; it lacks G9's explicit zero-flaw and one-factor choices.

**Impact:** a user cannot assume G9 reliability or guard guarantees apply to `python -m agent.hybrid ... --live`. A clean input may prompt unnecessary changes, the problem G9 was designed partly to address.

**Repair:** expose one versioned, reviewed engine through CLI/UI/CI, or very clearly declare which engine each path uses and evaluate that engine separately. Keep legacy runners for reproducibility.

### P1 — No unseen test currently establishes generalization

`docs/EVAL-12-G9-DSL.md:36` explains that the operations were selected with all the relevant cases already in view; `docs/EVAL-13-G9-PREREG.md:12` says EHG is not held out. Preregistration protects against changing a particular run after viewing its outputs; it does not erase previous adaptation to those datasets and failure modes.

Parsing `runs_g9b/score.json` found two underlying dataset families, each with a leaky/clean variant. The repeated plans produce identical measurements on fixed seeds. Those repeats measure response/process stability on those cases, not independent confirmation across research problems. Disguising names and rescaling data does not create a new dataset.

**Repair:** after freezing the product, have a person who did not tune the instrument select or adapt a small new collection. Include legitimate clean pipelines that look suspicious, unsupported formats, known flaws, and matched clean twins. Keep the truth and adjudication out of planner/reviewer contexts. Report dataset-level denominators and abstentions separately. Label this a pilot, not a population rate.

### P1 — G9's clean-case advantage cannot be attributed to execution

All **8 of 8** clean G9/G9b units are labelled `no flaw reported (model verdict, nothing run)` in `runs_g9b/score.json`. Source confirms the shortcut: `agent/contract_g9.py:158` accepts a valid `no_flaw` without compiling or running, and `agent/factorial_g9.py:380` returns immediately. Recording zero false alarms is legitimate; saying sandbox measurement prevented these particular false alarms is not supported.

This qualification is specific to G9: inspection of `runs_g7/r1.json` through `r5.json` and `runs_g8/r1.json` through `r5.json` confirms **all five clean units in each run contain executed statistics**, with status `ok` and calculated sign `0`. Those runs support a measured absence of inflation for the tested controls; they still do not prove the entire pipeline is leakage-free.

The comparator is also not a clean execution ablation. `agent/factorial_g7.py:47` asks the reading baseline for accuracy drops in percentage points, including on the PR-AUC/ROC-AUC cases. The G9 planner receives a longer contract, explicit clean-answer instruction and a prescribed temporal-control rule (`agent/contract_g9.py:46`). Different instructions, answer formats and repair budgets can explain differences.

**Repair:** compare the same model, inputs, methodology contract, permissible answers and budget with execution off/on. Record the model's initial judgment before execution and any final change. Compare rules, matched reader, one planner plus execution, and only then a proposed reviewer collaboration. The existing B3 results remain historical evidence, not a matched causal attribution.

### P2 — Statistical intervals have a narrower meaning than a researcher may infer

`sandbox/factorial_stats.py:43` and `:78` independently resample individual rows of already-computed prediction vectors. No model is refitted during bootstrap, and the worker output (`sandbox/run_factorial.py:38`) carries only labels/predictions, not row identities, groups or times. Three seed results are separately computed and majority-voted (`g4.py:163`); this is not a single calibrated 95% confidence procedure.

**Inference from the implementation:** these are conditional row-resampling intervals. They do not account for all training, tuning, temporal or cluster dependence. Independently resampling configurations also discards pairing where evaluation rows overlap. This can matter particularly because group and temporal leakage are core supported cases. The implementation gives no evidence that its interval procedure has the claimed coverage under those structures.

The headline temporal comparison additionally changes the evaluation population: apparent performance over the original rows versus future-period holdout performance. The EHG comparison removes synthetic evaluation rows. These are meaningful protocol corrections, but the numerical difference should be described as **the change under the specified control**, not a universally isolated causal amount of leakage. Equal sample sizes alone would not eliminate a population/composition difference.

**Repair:** label existing intervals precisely. In a new version preserve row IDs and grouping/time metadata, choose paired resampling where outcomes align and an appropriate group/time-aware procedure where they do not, and validate on controlled simulations. Record the estimand, eligible evaluation population and threshold before experiments. Do not silently re-score historical results.

### P2 — DSL robustness comes with an important coverage tradeoff

The DSL supports four operation families. It cannot express feature edits, duplicate handling and some split/structural rewrites (`docs/EVAL-12-G9-DSL.md:29`). Of 82 historical plans, the replay reports **7 full**, **46 partial**, and **29 no coverage** (`:133`). Zero crashes is valuable but does not imply that those plans can be faithfully handled.

This matters because the earlier rules-versus-loop edge was concentrated in hard feature/interaction cases, while the latest typed boundary excludes feature edits. The wider planner's capability and the typed planner's reliability must not be combined into one untested capability claim.

**Repair:** show a capability matrix and an explicit unsupported outcome. Measure joint success: valid input accepted, hypothesis expressible, correct control executed, conclusion correct. Avoid reporting compile success alone as end-to-end coverage.

### P2 — No evidence yet supports a multi-agent benefit

The main loop is a planner plus deterministic machinery, with repairs. The optional Wonder referee (`agent/hybrid.py:240`) can veto a finding but is not an independently evaluated collaborating research team. Its failure or unparseable reply leaves the original finding in place and records that failure, so "reviewed" must mean an actual successful review, not just that the flag was requested.

A room full of agents can amplify shared assumptions. Agent consensus is not independent empirical confirmation, especially when agents see the same prompts and one another's answers.

**Repair:** if adding collaboration, start with one independent methodology critic whose remit is narrow: challenge whether the proposed control matches the intended use and available-at-prediction-time information. Have planner and critic first work independently; resolve disagreements using executable checks or a user-visible unresolved status. Test whether this prevents erroneous controls at comparable cost. Add other roles only where a measured failure justifies them.

## What the project is actually doing

There are three distinct systems to keep separate in the pitch and interface:

1. **The user's predictive model:** classical classifiers in the present cases. NullLab executes the original and modified evaluation pipelines, which can train/refit these models.
2. **The Meta reasoning model:** used for inference to propose/review evaluation controls. The inspected project does not train or fine-tune that model.
3. **NullLab's own benchmark:** used to evaluate whether NullLab proposes legitimate controls and reports appropriately. This benchmark needs its own development/test separation, independent of the train/test split inside each audited pipeline.

Leakage in the first system happens when information unavailable at intended prediction time influences fitting, preprocessing, feature selection, tuning or evaluation. The remedy depends on the task: fit preprocessing within training folds; tune on validation/inner CV; preserve a final untouched test; keep related groups together when deployment is to new groups; use appropriate time ordering for forecasting. There is no universal percentage split that makes all tasks valid. These practices are described by the primary [scikit-learn leakage guidance](https://scikit-learn.org/stable/common_pitfalls.html#data-leakage) and [cross-validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html).

Leakage in NullLab's own evaluation can arise from repeatedly modifying prompts, rules and DSL operations after seeing benchmark failures. The repository is unusually candid about this, which is a strength; the remedy is fresh independent evaluation, not removing the caveats.

## What is genuinely strong

- Raw results and explicit failure records make the work inspectable. G7's failed acceptance bar remains visible.
- Clean twins, a deterministic baseline and a reading-only baseline address useful questions, even though attribution still needs stronger matching.
- Constrained edits and a behavioural guard are substantive engineering, beyond answer generation.
- The system measures a proposed intervention and exports evidence and patches; this is a useful research workflow when the scope is understood.
- The repository already discloses contamination, development-set exposure, weak independence and unverified paths. Preserve that honesty while reducing the conceptual burden on users.

## Recommended sequence

1. Correct result identity and verdict semantics, and choose the actual engine to ship.
2. Give one real researcher one supported input and observe completion of the audit, including whether the proposed control answers their question.
3. Freeze that engine and evaluate a small fresh case set with matched baseline, abstention accounting, and clean controls.
4. Add a narrow independent critic only if it addresses a demonstrated failure and wins a small ablation.
5. Use an evidence-backed case in the demo: initial claim, specific disputed assumption, executed control, measured change, limitations, and usable output.

These recommendations preserve the narrow credible contribution. A general literature-review/dataset-discovery/research-team expansion would require new sources, permissions, adapters and evaluation; the current results do not validate that broader product.
