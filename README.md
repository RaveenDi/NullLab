# NullLab

[![CI](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml/badge.svg)](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml)

**Check the evaluation behind a machine-learning result before you trust it.**

A reported score can be inflated by how the evaluation was done: preprocessing fitted on test rows, synthetic records generated before cross-validation, leaked groups or time. NullLab is a local Research Workdesk that reruns your classifier's own code under a checked evaluation control and reports how much the metric changes.

## How it works

1. **Ask.** Enter your question and attach a CSV, optionally your `train.py` and notes.
2. **Review the brief and plan.** You confirm the target, intended use, population, decision time and column roles. The plan shows the metric, seeds and split candidates before anything runs.
3. **Propose.** Muse Spark proposes a typed intervention (fold-local fitting or resampling, removal of a label-using transform, a split replacement, or in-fold refitting). An optional Muse Wonder critic challenges the methodology independently.
4. **Verify and measure.** Deterministic code checks the proposed change, runs it in a restricted sandbox on fixed seeds, and measures the difference with intervals.
5. **Keep the evidence.** Every result is bound to hashes of the exact inputs and controls, and can be exported.

NullLab does not train or fine-tune a language model. The models only investigate the evaluation method; the classifier you supply produces the predictions that are measured. The default rules mode needs no key and makes no model calls.

## Demonstration

The bundled example uses real [UCI SECOM semiconductor records](https://archive.ics.uci.edu/dataset/179/secom) (CC BY 4.0; 1,567 records, 590 sensor columns, 104 defects). We introduce the faulty resampling placement ourselves; this is not an accusation against UCI or a published study.

On three fixed seeds, a planned control changed average precision from **0.983 to 0.139** by generating synthetic records inside training folds and scoring original held-out records. The conditional intervals were positive on all three seeds. The scored population and prevalence also change, so the difference describes the corrected protocol rather than a pure causal quantity of leakage.

The Spark planner proposed the control and the Wonder critic **disputed the interpretation**, noting missing preprocessing and prevalence context; both are shown beside the measured result. A rules-only run on the clean twin proposes no control and is labelled **NOT TESTED**, not clean. This is a small demonstration, not a benchmark.

## Quick start

Python 3.12.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt     # Windows: .venv\Scripts\python
.venv/bin/python -m uvicorn app.server:app --host 127.0.0.1 --port 8099
```

Open http://127.0.0.1:8099 and choose **Go to Workdesk**. [test-materials/workdesk](test-materials/workdesk/README.md) holds synthetic files to try, and the [usage guide](docs/USAGE.md) walks through the workflow. Keep the service on localhost.

| Page | Purpose |
|---|---|
| Landing | Explains the method and scope |
| Workdesk | The product: investigations, briefs, plans, runs |
| Evidence Lab | Recorded manufacturing study and saved audits (read-only) |
| Architecture | Interactive explanation of the models and deterministic checks (not live model activity) |

Command line:

```bash
python -m agent.engine examples/secom --out out/my-audit
python -m agent.engine examples/secom --preview
python -m agent.engine examples/secom --live --critic --out out/my-live-audit
```

## Model configuration (bring your own key)

No credentials are included in this repository.

1. Copy `.env.example` to `.env` (gitignored).
2. Set `MODEL_API_KEY` to your own key. Change `MODEL_BASE_URL`, `NULLLAB_MODEL` and `NULLLAB_MODEL_CRITIC` to use another endpoint or model.
3. Pass `--live` on the command line, or start the server with `NULLLAB_ALLOW_WEB_LIVE=1` to allow live calls from the web UI.

Any OpenAI-compatible endpoint works, including a local server (`MODEL_BASE_URL=http://127.0.0.1:8080/v1`, key may be blank). Environment variables take precedence over `.env`. The default per-job budget reserves at most $1 and four attempts; a timeout does not guarantee remote cancellation or exact billing.

## Inputs

- **CSV path:** up to 5 MB, 30–20,000 rows, numeric predictors, binary 0/1 target. It creates a fixed Random Forest/CV baseline, not a reproduction of your research code.
- **Your own code:** a case folder with `train.py` defining `load`, `feats` and `claimed_eval(df, seed)` (returning labels and predictions, with module `METRIC` of `"pr_auc"`, `"roc_auc"` or `"accuracy"`), plus `data.csv` and `excerpt.md`; optionally `case.json`. Running it requires explicit local-execution trust, so read the code first.
- Notes: UTF-8 text or Markdown up to 256 KB. PDFs, notebooks and repositories are not imported.
- Missing information, or designs the generated adapter cannot answer (unseen entities, future periods), stop before fitting or any model call.

## Project layout

| Path | Contents |
|---|---|
| `agent/` | Engine, study and intake logic, evidence handling, model provider, behavioural guard |
| `app/` | FastAPI server, Workdesk API and the web UI |
| `sandbox/` | Restricted execution of case code |
| `baselines/` | Rule-based baselines |
| `examples/` | Bundled SECOM cases |
| `docs/` | Usage, architecture, security, deployment |
| `tests/` | Offline test suite |

## Limitations

The four operation families do not cover arbitrary feature edits, notebooks, full-paper validation or research-gap discovery. Intervals condition on fixed predictions and are not calibrated for every clustered or temporal design. A finding is evidence about the supplied evaluation code, not scientific clearance, and no outside researcher has validated the workflow. See [Architecture](docs/ARCHITECTURE.md), [Security](docs/SECURITY.md) and [Deployment](docs/DEPLOYMENT.md).

## Tests

```bash
python -m pytest -m "not live" -q
```

## License

MIT for our code ([LICENSE](LICENSE)). Libraries, model inference and the UCI data are third-party; their terms are in [NOTICE](NOTICE).
