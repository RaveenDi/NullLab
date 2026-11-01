# NullLab

**Every AI can give you an answer. What if yours could discover why that answer is wrong?**

NullLab is an adversarial experiment engine for machine-learning claims. Given a claim ("our classifier achieves 96% and generalizes") plus the training script, it names the assumption the claim depends on, preregisters three competing hypotheses, writes and executes a controlled re-evaluation in a sandbox, and returns SURVIVED, FALSIFIED or INCONCLUSIVE with paired confidence intervals over three seeds. If a claim holds up, it says so. Built for the Meta Global AI Developer Hackathon (Push the Frontier).

## Status: honest summary
- **Offline MVP works** (sandbox runner, case corpus with ground truth kept out of the agent's view, baselines, verdict logic, report pages, FastAPI app). Run `python -m pytest -q`.
- **First live run with `muse-spark-1.3` (3 cases x 3 seeds):** hero case FALSIFIED, planted synthetic leak FALSIFIED, clean control SURVIVED, all correct. Verbatim code-line citations did not pass yet; the corpus is small and the flaws are in pipelines written for the project; baselines are our own reimplementations. Details in `docs/LIVE-RESULT-2026-11-01.md`.
- Mock mode is a scripted stand-in and is never reported as a model result.
- The sandbox is a restricted subprocess, not Docker; a Dockerfile (`--network=none`) is included but untested.

## Run it
```
python -m venv .venv && .venv\Scriptsctivate
pip install -r requirements.txt
python -m pytest -q
python pipeline.py            # mock mode (no network)
python pipeline.py --live     # live muse-spark-1.3 (needs .env with a Meta key)
```
Copy `.env.example` to `.env` and add a Meta Model API key for live mode. Live calls are budget-checked by the project tooling.

## Scope and tooling
Everything in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026), mainly Oct 31 to Nov 1, with coding agents including Meta's Muse Code. Meta models: `muse-spark-1.3` (claim extraction, hypothesis generation, experiment code). Libraries: scikit-learn, pandas, numpy, FastAPI, uvicorn, pytest.

## License
Not yet chosen by the owner.
