# NullLab

**Put the evaluation behind a machine-learning score to the test.** NullLab helps an ML author reproduce a supported pipeline, challenge one evaluation assumption, run a constrained control, and export input-bound evidence.

The current author workspace runs real local experiments. It supports binary numeric Python/sklearn cases and a guided CSV baseline adapter. Muse Spark proposes typed interventions; an optional Muse Wonder critic independently challenges the methodology. Deterministic code checks and measures the experiment. The free rules path handles a deliberately small set of patterns.

NullLab does not train or fine-tune a language model. It runs the supplied classifier's training/evaluation code, then reruns that code under a checked evaluation control. The Meta agents investigate the evaluation method; the executed classifier supplies the predictions being measured.

## Manufacturing demonstration

Our constructed benchmark uses real [UCI SECOM semiconductor records](https://archive.ics.uci.edu/dataset/179/secom), licensed CC BY 4.0. The archive contains 1,567 records, 590 sensor columns and 104 defects. We introduce the faulty resampling placement ourselves; this is not an accusation against UCI or a published study.

On three fixed seeds, a planned control changed average precision from **0.983 to 0.139** by generating synthetic records inside training folds and scoring original held-out records. The conditional intervals were positive on all three seeds. The scored population and prevalence also change: the difference describes the corrected protocol, not a pure causal quantity of leakage. The initial feature-screening variant measured only +0.036 with intervals crossing zero; that weaker attempt is retained in the development log.

A real Spark planner independently proposed the resampling control. The Wonder critic **disputed the interpretation**, pointing out missing preprocessing and prevalence context. That disagreement is retained beside the measured result. A rules-only clean-twin run proposed no control and is labelled **NOT TESTED**, rather than clean. These are a small development demonstration, not a held-out benchmark or adoption study.

## Run locally

Python 3.12. From this folder:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python scripts/build_manufacturing.py --download
.venv\Scripts\python -m uvicorn app.server:app --host 127.0.0.1 --port 8099
```

Open http://127.0.0.1:8099 . Prepare a study brief and CSV baseline, inspect recorded review contributions, answer questions through a new case version, reopen saved audits and compare their metadata. Download a measured control bundle or an explicitly unmeasured assessment ZIP. No key is needed for the rules/local-execution path. Keep the service on localhost.

```powershell
python -m agent.engine examples/secom --out out/my-audit
python -m agent.engine examples/secom --preview
python -m agent.engine examples/secom --live --critic --out out/my-live-audit
```

For a live run, copy `.env.example` to `.env`, provide your own configuration and key, then explicitly use `--live`. The default per-job budget reserves at most $1 and four attempts, with estimated costs; remote cancellation/billing are not guaranteed by a timeout. The application has no private battle-station dependency. To enable live calls through the local UI, set `NULLLAB_ALLOW_WEB_LIVE=1` in the server environment after reviewing configuration.

Local compatible inference is configured through `MODEL_BASE_URL` and `NULLLAB_MODEL`; loopback servers may omit a key. The transport path is implemented and tested with fake providers. **Muse Glimmer model quality and hardware performance have not been validated here.** Operator-funded public inference and arbitrary hosted Python uploads are not offered by this build.

## Your inputs

In the UI, open **Prepare data or revise a study brief**. Supply a binary 0/1 target, intended use, decision time, population and predictor availability. Mark entity/time columns as metadata and exclude post-decision inputs. Selected predictors must be numeric; metadata may be text. This creates a fixed Random Forest/CV baseline, not a reproduction of existing research code. Missing information and unsupported unseen-entity/future designs stop before fitting or model calls. Your answers are declarations, not verified facts. Clarifications create a new case; earlier evidence remains unchanged.

For trusted existing code, create a case with `train.py` defining `load`, `feats`, and `claimed_eval(df, seed)`, `data.csv`, and `excerpt.md`; optionally add `case.json` with `target`, `intended_use` and preprocessing provenance. `claimed_eval` returns labels and predictions; use module `METRIC = "pr_auc"`, `"roc_auc"` or `"accuracy"`. Custom-code column roles need independent review. See [usage](docs/USAGE.md) and the [researcher roadmap](docs/RESEARCHER-ROADMAP.md).

## Evidence and limitations

Each v2 job has a unique directory, atomic checkpoints, exact input and control hashes, environment/instrument identity, raw vectors, explicit conclusion states, and attempted-call accounting. Mismatched/missing audit identity is refused for export. Prediction vectors are validated before scoring. Legacy research artifacts have their original identities and are not current submission evidence.

The four typed operation families cover fold-local fitting/resampling, removal of label-using evaluation transforms, supported split replacements, and model refitting within folds. Arbitrary feature edits, arbitrary notebooks, full-paper validation and general research-gap discovery are outside this instrument's measured scope. Intervals condition on fixed predictions and are not calibrated for all clustered/temporal designs. No outside researcher has validated this workflow.

The [internal six-case pilot](docs/EVAL-V2-PILOT.md) exposed a contract bug and measured 0/3 flawed-case controls. The original failures are preserved. After repair, reusing the stored plans measured two inflation findings and one inconclusive result without new inference. That rerun is development regression; three model-only no-flaw judgments do not establish clean specificity.

An [eight-case fixed follow-up](docs/EVAL-V2-FOLLOWUP.md) included ambiguous and unsupported inputs. It measured 1/2 supported flawed-case controls, with a disputed result and no positive inflation findings. It exposed transformer tracing and scope-state weaknesses that were subsequently repaired; original scores and post-fix development evidence stay separate.

[Architecture](docs/ARCHITECTURE.md) · [Security and privacy](docs/SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) · [Current evidence](docs/RESULTS-V2.md) · [Implementation status](docs/RELEASE-STATUS.md)

## Verification

Run the full offline suite after the rebuild:

```powershell
python -m pytest -m "not live" -q
python scripts/freeze_check.py verify
node --check app/static/workspace.js
```

The old protocol files and run histories are retained for reproducibility. Deliberate instrument changes are recorded in `docs/FROZEN-CHANGELOG.json`; historical results are not rescored under the new engine. Browser walkthrough is excluded by the owner's instruction. Current test outcomes are recorded in the release status, not inferred from this command list.

## Built during the hackathon

The initial code, historical experiments, v2 engine, input/measurement safeguards and author workspace were developed during the Meta Global AI Developer Hackathon (26 October–4 November 2026). Libraries, Meta inference and UCI data are third-party components. Indie Developer track; intended theme: Build for Your World, supporting an author's pre-submission evaluation review. No first-place, world-first, external adoption or measured time-saving claim is made.

MIT for our code. Dataset/service terms remain separate; see [NOTICE](NOTICE). Public repository: [RaveenDi/NullLab](https://github.com/RaveenDi/NullLab).
