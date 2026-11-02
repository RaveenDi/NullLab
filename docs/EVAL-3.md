# NullLab EVAL-3: BRIEF-4 spike, gates G0 to G3 (Sun Nov 1, 2026, about 11:40 to 12:30 SLT / 02:10 to 03:00 ET)

All numbers below were measured on this machine. Raw outputs: `logs_spike4/`, `runs_g1/` (not tracked), `runs_spike4/`. (The MOCK plumbing outputs `runs_mock3/` and the spike driver `scripts/legacy/spike4.py` were removed in the repo hygiene pass; they are in git history and `python pipeline.py` regenerates mock runs.) The spike case is **SYNTHETIC**. G4 and G5 were not started.

## G0: harness ($0)
- `eval/build_corpus.py` rebuilt 9 cases byte-identically (0 files changed). No materialisation failures, so nothing was fixed.
- `pipeline.py` MOCK on 9 cases (written to `runs_mock3/`): 6/6 FALSIFIED and 3/3 SURVIVED. This is a plumbing check only (regex falsifier).
- pytest: **30 passed** before the changes (170 s); **41 passed** after them (205 s).
- **Data loss found:** the old tests called `pipeline.run_case`, which writes to `runs/`. The G0 pytest run overwrote all 9 `runs/<case>.json` files with MOCK results; `runs/ablation.json` (LIVE) was not touched. The LIVE EVAL-2 per-case JSONs are therefore gone from disk. Restore them from git if they were committed (I ran no git commands). Fixed: tests now write to a temp directory.
- Docker: `docker info` fails (engine not running). The Docker path stays **UNVERIFIED**.

## G0b: exfiltration and pinning
- The old audit hook only blocked path substrings (`ground_truth`, `/nulllab/eval/`). Judging from the code, any other file, a subprocess, a hard link or ctypes would have got past it. This was not tested against the old hook.
- The new hook (`sandbox/run.py`):
  - It allows `open` only on paths whose realpath lies under the sandbox cwd or the Python install.
  - It blocks process spawning (`subprocess`, `os.system`, `_winapi.CreateProcess`), hard links, symlinks, renames, new ctypes `dlopen`/`dlsym` calls and `shutil.copyfile`.
- New tests: 10 exfiltration attempts plus 1 in the factorial sandbox. **11/11 blocked.** The attempts were: absolute path, 8.3 short path, pathlib, `os.open`, another evaluator file, a file outside the sandbox, `cmd /c type`, `os.system`, a hard link into cwd, and ctypes `CreateFileW`.
- This is still an in-process sandbox, not a container. Code that disables the audit hooks through some native route that is not covered could escape.
- `Dockerfile` and `requirements.txt` pin scikit-learn==1.9.1, pandas==3.1.0 and numpy==2.5.4. These are the versions every measured run used. The brief said 1.3, but pinning an unmeasured version would make container and subprocess results incomparable.

## G1: real Deepchecks and Giskard on the 9 blind inputs (6 leaky, 3 clean)
Both tools installed, each in its own venv:
- **Deepchecks 0.19.1** in `.venv-g1`. It needed sklearn 1.5.2, pandas 2.2.3, numpy 1.26.4, scipy 1.13.1 and category-encoders 2.6.4; the stock install fails on import.
- **Giskard 2.19.2** in `.venv-g1b`. The default `pip install giskard` gives 3.0.1, which is the LLM-agent product and has no tabular scan.

Protocol (blind user): `data.csv` plus the target named in `train.py`, with a random 75/25 split at seed 42.
- Deepchecks ran its `data_integrity` and `train_test_validation` suites, with no model.
- Giskard ran `scan` on a RandomForest trained on the 75% split.

| Tool | Flag rule | Recall (6 leaky) | False alarms (3 clean) |
|---|---|---|---|
| Deepchecks | any failed condition | 4/6 | 3/3 |
| Deepchecks | a leakage-relevant check failed | 4/6 | 2/3 |
| Giskard | any issue | 3/6 | 2/3 |
| Giskard | data-leakage or spurious-correlation issue | 1/6 (leak_proxy) | 0/3 |

- Deepchecks' hits all come from one check, *Feature Label Correlation Change*. It also fires on clean_group_correct, clean_wine_correct and the spike case, so it does not discriminate.
- Neither tool sees code-level leaks such as augment-then-split or full-data target statistics, because they live in `train.py`, not in `data.csv`.
- Neither tool can produce a factorial or an interaction estimate.
- Kill-rule check: neither tool reaches 5/6, and neither ranks the spike interaction. **Not triggered.**

## G2: 2 LIVE muse-spark-1.3 calls on the spike case
Each call ran `bs.py spend check meta` first and was logged with `spend add`. Settings: max_tokens 12000, reasoning_effort low.
- **Extractor:** parseable JSON. Verbatim pointers 2/2: excerpt line 3 and `train.py` line 32. No retry was needed.
- **Falsifier:** parseable JSON with 3 hypotheses, prereg sha `be8e32fe…`. Its JSON schema has no line-pointer field, so "verbatim pointers" applies only to the extractor.
- The falsifier's own patch (fix the history feature only) measured deltas of +4.9 / +5.9 / +6.3 pp.
  - Its primary hypothesis H1 had predicted a "substantial drop toward majority baseline" and was wrong.
  - Its rival H2 had predicted that patient overlap keeps accuracy high, and the data supports it.
- Tokens: about 2.4k and 2.9k per call. Spark accepted `reasoning_effort` and both calls finished with `stop`.

## G3: compositional spike case `factorial/comp_visit_history` (SYNTHETIC)
- 250 patients and 2,217 visits. The visit label depends on latent patient risk plus 3 lab values.
- **Flaw A:** `patient_event_rate` is a groupby-mean of the label over ALL visits, computed before the split.
- **Flaw B:** a random visit-level split, while the claim is about *new* patients.
- The builder validated the case with evaluator-written reference patches **before** any preregistration:
  - Design v1 (2 to 6 visits per patient) gave I = +7 to +10 pp, and on seed 42 its CI included 0.
  - Design v2 (6 to 12 visits per patient) gave I = +19 to +21 pp.
  - v2 was then frozen, and its agent-view hashes are in `runs_spike4/prereg_log.jsonl`.
  - No prompt was changed at any point.

Preregistration (`runs_spike4/prereg_log.jsonl`, 06:23 UTC = 11:53 SLT), written before any loop run:

| Prereg | Hash | Content |
|---|---|---|
| Scoring rule | `395f9552…` | the culprit and point-miss rules |
| Loop planner (LIVE) | `a9ae2110…` | predicted drops A +6 / B +3 / both +20 pp; ranking AxB > A > B |
| B3 single prompt (LIVE) | `4ad74b98…` | predicted drops A +4 / B +1 / both +32 pp; ranking AxB > A > B; confidence 0.9 |

The loop ran the planner's LIVE-written patches: 4 configs × seeds 42/43/44, n_boot=1000, with an UNPAIRED bootstrap (each config's test set is resampled independently).

| Seed | orig | fix-A | fix-B | fix-both | drop both (95% CI) | I (95% CI) | I, same-n subsample |
|---|---|---|---|---|---|---|---|
| 42 | 0.829 | 0.780 | 0.808 | 0.585 | +24.3 [19.2, 29.6] | **+17.4 [11.0, 24.4]** | +17.8 [10.8, 24.7] |
| 43 | 0.829 | 0.769 | 0.858 | 0.624 | +20.5 [15.4, 25.6] | **+17.4 [10.8, 24.7]** | +17.5 [10.5, 24.1] |
| 44 | 0.843 | 0.780 | 0.858 | 0.603 | +24.0 [19.0, 29.2] | **+19.2 [12.2, 26.1]** | +19.6 [13.3, 25.6] |

Mean components: drop from fix-A +5.7 pp, from fix-B −0.8 pp, interaction +18.0 pp. The ground-truth culprit is therefore **AxB**.

**Acceptance (preregistered rule):**
- I CI excludes 0 on 3/3 seeds: **yes**, both full-n and same-n.
- Fix-both drop of at least 8 pp: **yes, 22.9 pp** on average.
- B3 misranks: **no**. B3 ranked AxB first, which is correct.
- B3 point estimate outside the loop CI: **yes**. 32 pp is above the upper bound on all 3 seeds.
- **Result: SPIKE PASSES. Kill rule not triggered.**

### Honest reading (read this before building G4)
- **The pass is narrow and rests only on magnitude.** Reading alone (B3, one call) got the qualitative story right: the interaction exists, fix-B alone does about nothing, fix-A alone is small, and fixing both is large. B3 missed only on size: 32 pp predicted versus 22.9 pp measured.
- The loop planner's own preregistered guess was +20 pp, which lies inside the CI. So Spark-reading-plus-guessing was close; execution's added value here is the **measured, CI-bounded magnitude**, not the discovery of the interaction.
- The point miss is fragile:
  - With the builder's reference patches, the seed-44 fix-both CI is [24.2, 34.5], which *contains* 32.
  - The miss therefore depends on how the patches implement the fixes. The planner computes in-sample training rates; the reference uses out-of-fold rates.
- n = 1 case and 1 B3 call at temperature 0. Nothing here is a rate.
- The "reading cannot predict the interaction" thesis is **not supported** by this case. "Reading cannot pin the magnitude" is weakly supported.
- For G4, cases need interactions that reading gets *wrong in sign or ranking*, not only in size. Otherwise the ship-pass criterion "B3 misranks or misses magnitude in ≥3/4" will be met only on magnitude.

## Spend
- Spike live calls: 4 (extractor, falsifier, planner, B3), against a cap of 14 (`runs/live_calls_spike4.jsonl`).
- Logged Meta spend went from $10.41 to **$10.67** (+$0.26 at per-call estimates; real per-token price UNVERIFIED). That leaves about $11.7 of the $12 pre-approval and about $19.3 under the $30 cap.
