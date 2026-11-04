# NullLab

[![CI](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml/badge.svg)](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml)

**Your question. Your experiment. Your evidence.** NullLab is a local Research Workdesk for investigating the evaluation behind a machine-learning result. Start with your own question and materials, review the study brief and plan, then follow real experiments into input-bound evidence.

The workdesk saves investigations, original uploads, clarification threads, brief revisions, plans and run history. It supports binary numeric Python/sklearn cases and a guided CSV baseline adapter. Muse Spark proposes typed interventions; an optional Muse Wonder critic independently challenges the methodology. Deterministic code checks and measures the experiment. The free rules path handles a deliberately small set of patterns; its study guide provides structured local guidance rather than general model conversation.

Explicit answers can become source-quoted brief suggestions; the author reviews and saves them. Concrete plans expose the target, metric, fixed seeds and required split candidates before execution. Known group/time adapter and numeric-metadata incompatibilities stop before training or model spend. Static applicability is not runtime acceptance, and group/time comparisons retain their descriptive-inference limit.

NullLab does not train or fine-tune a language model. It runs the supplied classifier's training/evaluation code, then reruns that code under a checked evaluation control. The Meta agents investigate the evaluation method; the executed classifier supplies the predictions being measured.

## Manufacturing demonstration

The bundled example uses real [UCI SECOM semiconductor records](https://archive.ics.uci.edu/dataset/179/secom) (CC BY 4.0; 1,567 records, 590 sensor columns, 104 defects). We introduce the faulty resampling placement ourselves; this is not an accusation against UCI or a published study.

On three fixed seeds, a planned control changed average precision from **0.983 to 0.139** by generating synthetic records inside training folds and scoring original held-out records. The conditional intervals were positive on all three seeds. The scored population and prevalence also change, so the difference describes the corrected protocol rather than a pure causal quantity of leakage.

A Spark planner proposed the resampling control and the Wonder critic **disputed the interpretation**, pointing out missing preprocessing and prevalence context; both are shown beside the measured result. A rules-only run on the clean twin proposes no control and is labelled **NOT TESTED**, not clean. This is a small demonstration, not a benchmark.

## Run locally

Python 3.12.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt     # Windows: .venv\Scripts\python
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8099
```

Open http://127.0.0.1:8099 and choose **Go to Workdesk**. Enter your question, attach a CSV and optional compatible Python/notes, then review **Study brief → Save brief & prepare plan → Review & run**. The default rules/local-execution mode needs no key. See the [usage guide](docs/USAGE.md); [test-materials/workdesk](test-materials/workdesk/README.md) holds synthetic files to try. Keep the service on localhost.

Pages: the landing page explains the method; **Workdesk** is the product; **Evidence Lab** shows the recorded manufacturing study and saved audits; **Architecture** is an interactive explanation (not live model activity).

CLI:

```bash
python -m agent.engine examples/secom --out out/my-audit
python -m agent.engine examples/secom --preview
python -m agent.engine examples/secom --live --critic --out out/my-live-audit
```

## Model configuration (bring your own key)

No credentials are included in this repository. To use live model calls:

1. Copy `.env.example` to `.env` (gitignored).
2. Set `MODEL_API_KEY` to your own key. Adjust `MODEL_BASE_URL`, `NULLLAB_MODEL` and `NULLLAB_MODEL_CRITIC` if you use a different endpoint or model.
3. Pass `--live` on the CLI, or start the server with `NULLLAB_ALLOW_WEB_LIVE=1` to allow live calls from the web UI.

Any OpenAI-compatible endpoint works, including a local server (for example `MODEL_BASE_URL=http://127.0.0.1:8080/v1`, where the key may be blank). Environment variables take precedence over `.env`. The default per-job budget reserves at most $1 and four attempts; a timeout does not guarantee remote cancellation or exact billing. Local-model quality has not been validated here.

## Your inputs

In the Workdesk, start with a question and attach your materials. The supported CSV path accepts up to 5 MB, 30–20,000 rows, numeric selected predictors and a binary 0/1 target. Optional UTF-8 text/Markdown notes and compatible Python files are limited to 256 KB each. PDFs, notebooks and arbitrary repositories are not imported automatically. Original bytes and hashes are preserved.

In **Study brief**, supply intended use, decision time, population and predictor availability. Mark entity/time columns as metadata and exclude post-decision inputs. The CSV-only path creates a fixed Random Forest/CV baseline, not a reproduction of existing research code. Supplied Python requires explicit local-execution trust. Missing information and unsupported generated unseen-entity/future designs stop before fitting or model calls. Your answers are declarations, not verified facts. Changed inputs/briefs require a new reviewed plan; earlier evidence remains unchanged.

For trusted existing code, create a case with `train.py` defining `load`, `feats`, and `claimed_eval(df, seed)`, `data.csv`, and `excerpt.md`; optionally add `case.json` with `target`, `intended_use` and preprocessing provenance. `claimed_eval` returns labels and predictions; use module `METRIC = "pr_auc"`, `"roc_auc"` or `"accuracy"`. Custom-code column roles need independent review. See [usage](docs/USAGE.md).

## Scope and limitations

The four typed operation families cover fold-local fitting/resampling, removal of label-using evaluation transforms, supported split replacements, and model refitting within folds. Arbitrary feature edits, arbitrary notebooks, full-paper validation and general research-gap discovery are outside this instrument's scope. Intervals condition on fixed predictions and are not calibrated for all clustered or temporal designs. Findings are evidence about the supplied evaluation code, not scientific clearance, and no outside researcher has validated the workflow.

Every job keeps its input and control hashes, environment identity, raw vectors and an explicit conclusion state; exports refuse missing or mismatched identity. See [Architecture](docs/ARCHITECTURE.md), [Security and privacy](docs/SECURITY.md) and [Deployment](docs/DEPLOYMENT.md).

## Tests

```bash
python -m pytest -m "not live" -q
```

## License and attribution

MIT for our code (see [LICENSE](LICENSE)). Libraries, model inference and the UCI data are third-party; their terms are in [NOTICE](NOTICE).
