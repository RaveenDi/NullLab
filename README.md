# NullLab

**Every AI can give you an answer. What if yours could discover why that answer is wrong?**

NullLab is an adversarial experiment engine for machine-learning claims. Given a claim ("our classifier
achieves 96% and generalizes") plus the training script, it names the assumption the claim depends on,
preregisters three competing hypotheses, writes and executes a controlled re-evaluation in a sandbox, and
returns SURVIVED, FALSIFIED or INCONCLUSIVE with per-seed (unpaired) bootstrap confidence intervals over three seeds. If a claim
holds up, it says so. Built for the Meta Global AI Developer Hackathon (Push the Frontier).

## Latest result: G6, a real published correction ([docs/EVAL-6.md](docs/EVAL-6.md))

| Case | Provenance | Published correction | NullLab loop (3 live repeats) | B3 reading only |
|---|---|---|---|---|
| Civil-war onset, Muchlinski et al. 2016; flaw documented by Neunhoeffer & Sternberg 2019 (Political Analysis) | **REAL-PINNED** (Dataverse doi:10.7910/DVN/KRKWK8, md5-pinned) | PR-AUC 0.43 → 0.07 (+0.36) | sign + 3/3; +0.23 / +0.20 / +0.20; within ±0.15 in **1/3** | right 3/3 |
| Screening before CV, ESL §7.10.2 | **TEXTBOOK** | accuracy 0.97 → 0.50 (+0.47) | +0.53 / +0.55 / +0.43, 3/3 | right 3/3 |
| Correct variants of both | same | none | **0/6** false alarms (2 INCONCLUSIVE) | 3/6 false alarms |

Preregistered G6 acceptance: **FAIL** (real-case magnitude 1/3). Memorisation probe: Spark recognises both sources.
Spend +$2.84. `python g6.py ref|replay|rule|probe|run <r>|score`; cases in `real/`, host-only truth in `eval/g6_truth.json`,
rebuild data with `python eval/build_g6.py <SambnisImp.csv>`. Full suite: 77 passed.

## Setup (5 commands)

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python eval/build_corpus.py     # (re)builds corpus/ (9 cases) + eval/ground_truth.json (evaluator only)
python pipeline.py              # all cases, MOCK mode -> runs/<case>.json
python -m pytest -q             # suite (needs the corpus materialized first)
```

Then either open `report/index.html` directly, or serve it:

```
python -m report.render         # writes report/index.html + report/<case>.html
python -m uvicorn app.server:app --port 8099   # http://127.0.0.1:8099/
```

Live (real model) runs are CLI-only and spend-gated:

```
python pipeline.py --live       # muse-spark-1.3 as extractor + falsifier (Meta key required, $30 cap)
python -m eval.score --live     # adds the B3 single-prompt baseline (one call per case, no execution)
```

Copy `.env.example` to `.env` for local runs, or keep the key at `C:\dev\bs\.env` (never print or commit it).
`pipeline.py --live` refuses to call the model unless `bs.py spend check` approves, and stops after the
per-phase live-call cap (70 for G4). LIVE outputs go to `runs_live/`, MOCK outputs to `runs/`.
 Falsifier calls use `max_tokens >= 12000` with `reasoning_effort: "low"` — smaller budgets returned
empty model output.

## What is real vs mock

- **MOCK mode is a scripted regex stand-in.** It exercises the plumbing (preregistration, sandbox, verdict,
  report) and is labelled `MOCK (stub, not a model result)` in every run JSON and report page. It is never
  evidence the model can do the task.
- **LIVE mode calls `muse-spark-1.3`** for claim extraction (with verbatim line citations) and falsifier
  patches (executed in the sandbox). First live run (3 cases × 3 seeds): 3/3 verdicts correct; code-line
  citations failed verbatim (grounding 0.5) — see `docs/LIVE-RESULT-2026-11-01.md`.
- **Baselines B0/B1 are our reimplementations** (a 4-check data checklist; a fixed GroupKFold on a guessed
  group column), not the real Deepchecks/Giskard suites — labelled as such. B3 (single-prompt judgement,
  no execution) runs only with `--live`. `runs/ablation.json` records whether the real suites are installed.

## Honest limitations

- Corpus flaws are planted by the project (the hero pipeline was written for this repo; it is not an
  independent published paper), so recall measures "finds our planted leaks", not wild ones.
- Sandbox is a restricted subprocess (network cut, timeout, evaluator paths blocked), **not** the planned
  locked-down container; the `Dockerfile` (`--network=none`) path is implemented but untested.
- `requirements.txt`/`Dockerfile` pin scikit-learn 1.9.1, pandas 3.1.0, numpy 2.5.4 (the versions all runs used). Excerpt claim percentages are nominal — the
  measured claimed-protocol numbers are in `runs/*.json`.
- EVAL-2 (9 cases) live results are in `runs_live/` (rerun Nov 1): loop 5/6 recall, 1/3 false alarms; B3 single prompt 6/6, 0/3.
  Live Spark is not reproducible run to run (the first EVAL-2 run had 0/3 loop false alarms).

## 2x2 factorial falsification (G4, SYNTHETIC cases, `g4.py`, `docs/EVAL-4.md`)

What the data supports (n = 4 new + 4 clean cases, all built by us; counts, not rates):
- On a cancellation case, single-prompt reading (B3) and Spark's own planner both predicted the claim was inflated;
  executing the planner's patches showed it is understated (fix-both -5.5pp, truth -10.4pp). On a benign case, B3
  said "leak"; execution measured ~0.
- The loop's fix-both sign was right on 4/4 new cases; B3 was wrong on 3/4 (sign, verdict or culprit).
- **But** the loop false-alarmed on 1/4 clean cases (its "fix" removed a legitimate feature), and the preregistered
  G4 acceptance therefore FAILED. We do not claim that reading cannot predict these effects, or that the loop is
  reliable on clean code.

## Guarded factorial with repeats (G5, same SYNTHETIC cases, `g5.py`, `docs/EVAL-5.md`)

The planner now writes **structured edits** to named functions of `train.py`, and code applies them. A deterministic
**patch-fidelity guard** (`agent/fidelity.py`) rejects any edit that changes the model, the features, the split or the
sample size outside the declared step. A rejected edit gets one retry; if it still fails, the result is INCONCLUSIVE.
The guard and the acceptance rule were preregistered (hashed) before any G5 live call. There were 3 independent live
repeats.

What the data supports (8 cases × 3 repeats; counts, not rates):
- **Preregistered acceptance PASSED.** Every clause held:
  - loop clean false alarms: 1/12;
  - loop sign right on hard runs: 11/12 (the miss is 1 INCONCLUSIVE);
  - B3 (reading only) wrong on hard runs: 9/12;
  - every executed patch passed the fidelity audit.
- Replayed offline, the guard rejects G4's failing clean_group_correct patch. Live, clean_group_correct never
  false-alarmed in 3/3 repeats.
- On the cancellation case, B3 said "inflated" in 3/3 repeats. The guarded loop measured "understated" in 3/3.
- On the benign case, B3 said "leak" in 3/3 repeats. The loop measured ~0 in 2/3, and 1 was INCONCLUSIVE.
- **Remaining failure.** One clean false alarm (clean_wine_correct, r2): a declared, guard-compliant edit dropped a
  *named* legitimate column and used an ordered split on class-sorted rows. The guard does not judge whether a
  declared fix is *justified*, only that it stays inside its step. B3 also false-alarmed on clean runs, 7/12.

## Scope and tooling

Everything in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 to Nov 4,
2026), mainly Oct 31 to Nov 1, with coding agents including Meta's Muse Code. Meta models: `muse-spark-1.3` (claim extraction, hypothesis generation,
experiment code). Libraries: scikit-learn, pandas, numpy, FastAPI, uvicorn, pytest.

## License

Not yet chosen by the owner.
