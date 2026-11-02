# NullLab

**Reading an AI's answer is cheap. Measuring it is the work.**

Re-runs an ML claim's suspect step and measures how inflated it was.

`tests: 387 collected (77 passed at G6, docs/EVAL-6.md)` | `CI: agent.ci_check, exit 0/1/2 (workflow in .github/workflows, not yet run on GitHub: UNVERIFIED)` | `offline by default` | `rules-only path: $0, no key`

## Try it (offline, no key, $0)

```
python -m venv .venv
.venv\Scripts\activate  # Windows (bash/macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
python -m agent.hybrid corpus/leak_prescale --out out/hy --report out/hy.md
```

Real output, recorded 2026-11-02 10:10 UTC (15:40 SLT / 05:10 ET) from exactly that command; only the temp path in the first line was shortened to `<tmp>`. Source: `report/assets/recorded/hybrid_rules.json`.

```
leak_prescale: INFLATED [rules (no model)] model calls 0 est $0.00; record dir <tmp>/hy3; report <tmp>/hy3.md

Verdict: INFLATED | produced by: rules (no model)
Route: rules fired and the measurement confirms (consistency check passed)
Claimed 0.8178 vs controlled 0.6444 (accuracy); inflation +17.333 pp; sign + (per seed ['+', '0', '+']);
95% interval per seed (unpaired bootstrap): 42: [2.667, 30.667], 43: [-1.333, 25.333], 44: [10.633, 37.333].
```

(The second block is the head of `out/hy.md`; `leak_prescale` is a case we built, SYNTHETIC. The process exits 0.) Gate a pull request on it, rules only, five lines:

```yaml
- uses: actions/checkout@v4
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }   # the version this repo was developed on
- run: pip install -r requirements.txt && python -m agent.ci_check . --threshold 0.05 --summary $GITHUB_STEP_SUMMARY
```
`agent.ci_check` exits 0 (no case above the threshold), 1 (a case is INFLATED beyond it, 95% interval above 0), 2 (nothing audited or a measurement failed). A case where no rule fired is reported `NO_RULE_FIRED`, not as a pass. Full workflow: `.github/workflows/nulllab-audit.yml`.

## What it found on a famous published result (source hidden)

A famous published ML result reported a score that did not survive a re-check: the model was scored on rows it had trained on. We disguised its source (columns renamed, domain reworded, features rescaled; same rows) and asked NullLab to re-run it. Two preregistered runs, reported side by side at equal weight and never merged:

| Run | Direction found (leaky) | False alarms (clean twin) | Inflation within 0.15 of the published +0.36 | Harness INCONCLUSIVE | Result |
|---|---|---|---|---|---|
| **G7** (preregistered) | **3/5** | **0/5** | **3/5** | **2/10** | bar (4/5 direction) **FAILED**; source `runs_g7/score.json` |
| **G8** (new labelled run, scored as frozen) | **4/5** | **0/5** | **4/5** | **1/10** (target 0, **not met**) | clauses (a) to (c) **met**; harness target **missed**; source `runs_g8/score.json`, [docs/EVAL-9-G8-RESULT.md](docs/EVAL-9-G8-RESULT.md) |

G8 leaky repeats that executed measured +0.340, +0.339, +0.341, +0.328 (published +0.36; a Python port of the original measures +0.299); the one that did not is a read timeout after about 500 s, counted as not met and not re-rolled. G7 measured +0.308 in each executed repeat. All five G8 clean repeats: no effect, interval spans 0 (-0.005, -0.005, -0.004, -0.015, -0.005). Reading only (one prompt, no execution) got the G7 leaky case right 4/5 and false-alarmed 5/5 on the clean twin; it was not run on G8. Caveats that matter: the guard rejected a random-split first plan in the executed repeats, so the time split comes from the guard plus the model; the fixed rules were never run on this disguised case; the disguise passed a 2-call probe, which is not proof of no memory; n = 5 per arm, counts not rates. Everything has n and a file on the demo page (`python -m report.render`, then open `report/index.html`).

**G9 (a third, separately labelled run; typed edit language, speed-fixed guard; shown beside G7 and G8, never merged).** The EHG disguised pair (a second real dataset: oversampling before cross-validation; 5 repeats) and a regression check on the headline pair (3 repeats), 16 units in all: 8 from G9, which was stopped when the guard analysis proved too slow on the large case, and 8 from G9b, run after the guard was sped up with identical decisions ([EVAL-14](docs/EVAL-14-GUARD-SPEED.md), [EVAL-15](docs/EVAL-15-G9B-PREREG.md)). The stalled units had no observed outcome, so G9b is a continuation, not a re-roll; each unit is labelled by guard version in `runs_g9b/score.json`.

| G9 + G9b union (counts) | Direction found (leaky) | False alarms (clean twin) | Inflation within 0.15 | Reading only (leaky found / clean false alarms) |
|---|---|---|---|---|
| EHG disguised pair, 5 repeats | **5/5** | **0/5** | **5/5**, +0.424 every repeat (offline reference +0.43) | 5/5 / 0/5 (matched the loop) |
| Headline pair regression, 3 repeats | **3/3** | **0/3** | **3/3**, +0.332 each (published +0.36) | 1/3 / 3/3 |

Preregistered clauses (EVAL-13), scored on the union: EHG PASS, regression PASS, harness target met (0 of 16 INCONCLUSIVE; G9b used one guard repair and one bad-JSON repair). Estimated G9b spend about USD 1.6 (estimate, not billing). Caveats: (1) the 5 repeats gave identical numbers (same plan and seeds), so n = 5 is nominal for stability, not 5 independent confirmations; (2) EHG is not held out for the typed edit language, which was informed by failures we had already seen; (3) the contract states the temporal-split rule up front, so the headline pair no longer tests whether the model finds that split itself; (4) 8 of 16 units ran under the pre-fix guard and 8 under the fixed one; (5) the fixed-rules baseline fires nothing on EHG (0.000), and rules vs loop overall stays MIXED. Source: `runs_g9b/score.json`.

One-page card: [docs/RESULTS-CARD.md](docs/RESULTS-CARD.md). Synthetic hard cases (**11/12** signs right, reading only wrong **9/12**, fixed rules with no model **6/12**; SYNTHETIC, n = 12): [docs/EVAL-8-RULEBASED.md](docs/EVAL-8-RULEBASED.md).

## Where Meta's models sit

```
 claim + train.py + data (agent view only; the evaluator's truth files are never visible)
        |
        v
 [ Muse Spark ]  names 2 suspect steps, predicts the drop, writes structured edits   <- model
        |           (muse-wonder-1.0 can be swapped in: NULLLAB_MODEL; 8/8 schema-valid plans on a small synthetic probe)
        v
 [ guard ]       plain code: edit stays in its step, no feature/model/metric change,
        |         a forecast needs a time split (SPLIT-USE-REQUIRED); reject -> one retry   <- no model
        v
 [ sandbox ]     original, fix A, fix B, both x seeds 42/43/44, network off, unpaired bootstrap   <- no model
        v
 FALSIFIED / SURVIVED / INCONCLUSIVE  +  reviewer report (python -m agent.audit)
```
Spark also plays the single-prompt "reading only" baseline (B3). Muse Wonder and `muse-spark-1.3-contributor` appear only where stated in [docs/EVAL-7.md](docs/EVAL-7.md): the headline G7 runs used the contributor build; the Wonder swap was one small probe and no headline number uses it. Rules first, Spark where rules fail: a fixed five-rule library (no model, $0) is tried first; it measured 0 on the freight and pump hard cases where the loop got the sign 3/3 on both ([EVAL-8](docs/EVAL-8-RULEBASED.md); preregistered verdict MIXED).

## Replay in 3 commands (offline, no API key, $0)

```
.venv\Scripts\python -m report.render                                   # rebuild the demo page from the run files
.venv\Scripts\python -m uvicorn app.server:app --port 8099              # open http://127.0.0.1:8099 (or open report\index.html from disk)
.venv\Scripts\python -m agent.hybrid corpus/leak_prescale --out out/hy --report out/hy.md   # a reviewer report on a synthetic case
```
Setup first: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`. Replaying the recorded model replies through the whole loop (`python -m agent.factorial_g7 --replay runs_g7/traces.jsonl --out <new dir> run`, sandbox runs, several minutes) exists but was not re-run when this README was written (UNVERIFIED). Live model runs are CLI-only and spend-gated; the page makes no model call.

## Honest limits
- **The G7 preregistered acceptance failed** (direction 3/5, needed 4). Two repeats ended INCONCLUSIVE: a sandbox crash on the single allowed retry, and an unparseable retry reply. Counted as wrong, as preregistered. G8 is a new labelled run, not a re-score of G7: its clauses (a) to (c) were met (4/5, 0/5, 4/5) and its harness target was not (1/10 INCONCLUSIVE, a read timeout).
- **Reading beats running on detection of the leaky case here** (4/5 vs 3/5). NullLab's advantages are specificity (0/5 vs 5/5 false alarms on the clean twin) and that it measures instead of guessing.
- **Measured values are short of the published +0.36**: G7 +0.308, G8 +0.328 to +0.341. A Python port of the original pipeline measures +0.299 on the same rows.
- **The disguise is not proof of no memory.** It passed a 2-call probe (the first disguise was recognised by name; the final one was not). The textbook and the undisguised real case are recognised by the model, so they cannot separate running from remembering.
- **Hard-case and factorial results are SYNTHETIC cases we built.** Counts, not rates. n is in every cell. Not a population estimate.
- **Rules vs loop is MIXED**, not a pass: the loop has more hard-case signs right (11/12 vs 6/12) and more clean false alarms (1/12 vs 0/12). The rule author had read every `train.py`.
- The guard checks edits stay in their step and, since G7, that a forecast gets a time split; it cannot check direction or whether a fix is the right one.
- The sandbox is a restricted subprocess (network cut, timeout, evaluator paths blocked), not a locked container; the `Dockerfile` path is untested.
- **G9 caveats:** identical repeats (n = 5 is nominal), EHG not held out for the typed edit language, temporal-split rule stated up front, 8 of 16 units under the pre-fix guard. See the G9 paragraph above.
- Estimated Meta credits G4 to G8: about $15.35 over 200 live calls; G9b adds about $1.6 (per-call estimates, not billing; G0 to G3 and G9 are not in the G4 to G8 sum). Test suite: 387 tests collected on Nov 2 (collection only; the full suite was not re-run for this edit, the report tests pass; 77 passed at G6).

## What is in the repo
- `agent/` loop, guard, auditor; `baselines/` single-prompt, checklist and rule baselines; `sandbox/` executor; `eval/` builders and host-only truth; `real/` real, disguised and textbook cases (raw data pinned by checksum, see `real/README.md`); `report/` the demo page (plain HTML/CSS/JS, no external requests); `runs_*/` every run file behind every number; `docs/` EVAL-2 to EVAL-8, audit report, results card, demo script, video storyboard.
- Corpus rebuild: `python eval/build_corpus.py`; all cases in mock mode: `python pipeline.py` (MOCK outputs are labelled and never headline numbers). Live: `python pipeline.py --live` refuses to call the model unless `bs.py spend check` approves. Keep the key in `.env` or `C:\dev\bs\.env`; never commit it.
- Earlier phases: [EVAL-4](docs/EVAL-4.md) (2x2 factorial, G4), [EVAL-5](docs/EVAL-5.md) (guarded edits with repeats, G5: acceptance PASSED, one clean false alarm remained), [EVAL-6](docs/EVAL-6.md) (real and textbook cases, G6: acceptance FAILED on size, 1 of 3).

## Scope and tooling
Everything in this repository was written during the Meta Global AI Developer Hackathon (Oct 26 to Nov 4, 2026), with coding agents including Meta's Muse Code. Third-party libraries: scikit-learn, pandas, numpy, FastAPI, uvicorn, pytest. Public data used for the real cases is not ours; it is pinned and cited above.

## Licence
MIT, see [LICENSE](LICENSE). The licence covers this repository's code and docs. Third-party data keeps its own terms: the EHG features come from PhysioNet TPEHGDB (Open Data Commons Attribution License 1.0), and the raw civil-war data is not redistributed here.
