# NullLab

[![CI](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml/badge.svg)](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml)

**Your question. Your experiment. Your evidence.** NullLab is a local Research Workdesk for investigating the evaluation behind a machine-learning result. Start with your own question and materials, review the study brief and plan, then follow real experiments into input-bound evidence.

The workdesk saves investigations, original uploads, clarification threads, brief revisions, plans and run history. It supports binary numeric Python/sklearn cases and a guided CSV baseline adapter. Muse Spark proposes typed interventions; an optional Muse Wonder critic independently challenges the methodology. Deterministic code checks and measures the experiment. The free rules path handles a deliberately small set of patterns; its study guide provides structured local guidance rather than general model conversation.

Explicit answers can become source-quoted brief suggestions; the author reviews and saves them. Concrete plans expose the target, metric, fixed seeds and required split candidates before execution. Known group/time adapter and numeric-metadata incompatibilities stop before training or model spend. Static applicability is not runtime acceptance, and group/time comparisons retain their descriptive-inference limit. See the [researcher walkthrough repairs](docs/reviews/2026-11-04-researcher-repairs.md) for actual checks and preserved failures.

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
.venv\Scripts\python -m uvicorn app.server:app --host 127.0.0.1 --port 8099
```

The public manufacturing cases are included; regeneration is optional development work, not a setup prerequisite.

Open http://127.0.0.1:8099 and choose **Go to Workdesk**. Enter your question, attach a CSV and optional compatible Python/notes, then review **Study brief → Save brief & prepare plan → Review & run**. The default rules/local-execution mode needs no key. Results show actual progress, uncertainty and objections; reload restores saved work. See the [step-by-step guide](docs/USAGE.md). Keep the service on localhost.

For a complete hands-on check, follow the [38-step product test guide](docs/TESTING-WORKDESK.md) with the bundled [synthetic test materials](test-materials/workdesk/README.md). It covers missing-information gates, CSV and supplied-code runs, history/revisions/exports, optional Meta, errors and mobile behavior.

The landing page explains the method and scope. **[Research Workdesk](http://127.0.0.1:8099/workdesk)** is the actual product. **[Evidence Lab](http://127.0.0.1:8099/evidence)** separates the recorded manufacturing study and saved audits from new work. **[Architecture](http://127.0.0.1:8099/architecture)** is an interactive explanation of Meta reasoning and deterministic execution. Neither explanatory animation represents live model activity.

```powershell
python -m agent.engine examples/secom --out out/my-audit
python -m agent.engine examples/secom --preview
python -m agent.engine examples/secom --live --critic --out out/my-live-audit
```

For a live run, copy `.env.example` to `.env`, provide your own configuration and key, then explicitly use `--live`. The default per-job budget reserves at most $1 and four attempts, with estimated costs; remote cancellation/billing are not guaranteed by a timeout. Provider configuration is repository-owned and uses explicit environment settings. To enable live calls through the local UI, set `NULLLAB_ALLOW_WEB_LIVE=1` in the server environment after reviewing configuration.

Local compatible inference is configured through `MODEL_BASE_URL` and `NULLLAB_MODEL`; loopback servers may omit a key. The transport path is implemented and tested with fake providers. **Muse Glimmer model quality and hardware performance have not been validated here.** Operator-funded public inference and arbitrary hosted Python uploads are not offered by this build.

## Public hosting

The prepared public evidence demo can be hosted as static files on AWS Amplify and connected to a custom domain. Fresh Python audits remain local until the proposed authenticated, isolated service is implemented. See [deployment options and exact steps](docs/DEPLOYMENT.md). The public recording is clearly labelled and makes no model calls.

## Your inputs

In the Workdesk, start with a question and attach your materials. The supported CSV path accepts up to 5 MB, 30–20,000 rows, numeric selected predictors and a binary 0/1 target. Optional UTF-8 text/Markdown notes and compatible Python files are limited to 256 KB each. PDFs, notebooks and arbitrary repositories are not imported automatically. Original bytes and hashes are preserved.

In **Study brief**, supply intended use, decision time, population and predictor availability. Mark entity/time columns as metadata and exclude post-decision inputs. The CSV-only path creates a fixed Random Forest/CV baseline, not a reproduction of existing research code. Supplied Python requires explicit local-execution trust. Missing information and unsupported generated unseen-entity/future designs stop before fitting or model calls. Your answers are declarations, not verified facts. Changed inputs/briefs require a new reviewed plan; earlier evidence remains unchanged.

For trusted existing code, create a case with `train.py` defining `load`, `feats`, and `claimed_eval(df, seed)`, `data.csv`, and `excerpt.md`; optionally add `case.json` with `target`, `intended_use` and preprocessing provenance. `claimed_eval` returns labels and predictions; use module `METRIC = "pr_auc"`, `"roc_auc"` or `"accuracy"`. Custom-code column roles need independent review. See [usage](docs/USAGE.md) and the [researcher roadmap](docs/RESEARCHER-ROADMAP.md).

## Evidence and limitations

Each v2 job has a unique directory, atomic checkpoints, exact input and control hashes, environment/instrument identity, raw vectors, explicit conclusion states, and attempted-call accounting. Mismatched/missing audit identity is refused for export. Prediction vectors are validated before scoring. Legacy research artifacts have their original identities and are not current submission evidence.

The four typed operation families cover fold-local fitting/resampling, removal of label-using evaluation transforms, supported split replacements, and model refitting within folds. Arbitrary feature edits, arbitrary notebooks, full-paper validation and general research-gap discovery are outside this instrument's measured scope. Intervals condition on fixed predictions and are not calibrated for all clustered/temporal designs. No outside researcher has validated this workflow.

The [internal six-case pilot](docs/EVAL-V2-PILOT.md) exposed a contract bug and measured 0/3 flawed-case controls. The original failures are preserved. After repair, reusing the stored plans measured two inflation findings and one inconclusive result without new inference. That rerun is development regression; three model-only no-flaw judgments do not establish clean specificity.

An [eight-case fixed follow-up](docs/EVAL-V2-FOLLOWUP.md) included ambiguous and unsupported inputs. It measured 1/2 supported flawed-case controls, with a disputed result and no positive inflation findings. It exposed transformer tracing and scope-state weaknesses that were subsequently repaired; original scores and post-fix development evidence stay separate.

A [new ten-case internal evaluation and separate six-case confirmation](docs/EVAL-V2-RELEASE.md) retained a critic-contract failure (0/3 flawed controls measured), repaired its prompt, then measured 3/3 controls on new fixed data: one disputed, one no-effect and one descriptive/inconclusive group result. Three clean confirmation cases remained unmeasured model judgments. All outcomes and actual instrument snapshots are public; this is internal control-coverage evidence, not general accuracy.

[Architecture](docs/ARCHITECTURE.md) · [Security and privacy](docs/SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) · [Current evidence](docs/RESULTS-V2.md) · [Implementation status](docs/RELEASE-STATUS.md)

## Verification

Run the full offline suite after the rebuild:

```powershell
python -m pytest -m "not live" -q
python scripts/freeze_check.py verify --allow-missing-data
node --check app/static/workspace.js
node --check app/static/workspace-shell.js
node --check app/static/workdesk.js
node --check app/static/landing.js
node --check app/static/evidence.js
node --check app/static/architecture.js
```

The [documentation index](docs/README.md) lists the active guides. [Historical protocols and run records](docs/HISTORY.md) are retained for reproducibility at their original paths. Deliberate instrument changes are recorded in `docs/FROZEN-CHANGELOG.json`; historical results are not rescored under the new engine. The owner authorized desktop/mobile browser checks for this Workdesk rebuild; earlier reports remain accurate about their own excluded browser scope. The fresh-clone flag permits only known unredistributed historical data to be missing; use strict verification without it when those inputs are present. The first pushed CI run had a historical G9b runner failure caused by a mocked test reading absent gitignored data. That test now uses deliberately nonexistent case paths with an explicit input-view stub, preserving its scheduling/scoring assertions. The CI badge describes the published source, while the latest Workdesk changes are local until separately published. Dated validation scopes are retained in release status.

## Built during the hackathon

The initial code, historical experiments, v2 engine, input/measurement safeguards and author workspace were developed during the Meta Global AI Developer Hackathon (26 October–4 November 2026). Libraries, Meta inference and UCI data are third-party components. Indie Developer track; intended theme: Build for Your World, supporting an author's pre-submission evaluation review. No first-place, world-first, external adoption or measured time-saving claim is made.

MIT for our code. Dataset/service terms remain separate; see [NOTICE](NOTICE). Public repository: [RaveenDi/NullLab](https://github.com/RaveenDi/NullLab).
