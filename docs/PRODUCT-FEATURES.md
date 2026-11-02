# NullLab product features (Mon Nov 2, 2026)

Four features that sit on top of the audit. All run offline by default, make no model call unless you pass `--live`, and spend nothing.
Run every command from the NullLab folder with the repo venv (`.venv\Scripts\python.exe` on Windows, `python` below).
A **case** is a folder with `train.py` (defining `load`, `feats`, `claimed_eval`), `data.csv` and, for reports, `excerpt.md` (the claim text).

Why this shape: EVAL-8 (docs/EVAL-8-RULEBASED.md) found that a free fixed rule library matches or beats the Spark loop on textbook and real cases,
and that the loop wins only on look-ahead features, offsetting errors and label-conditioned imputation. So rules go first and the model is called only when needed.

## 1. Hybrid audit: rules first, Spark only when needed

```
python -m agent.hybrid corpus/leak_prescale --out out/hy --report out/hy.md
python -m agent.hybrid factorial/g4_pump_inspection --live --out out/hy      # real Spark call, explicit flag, spend gate applies
python -m agent.hybrid corpus/leak_prescale --live --referee                  # adds the Wonder veto referee (off by default)
```

Routing, with the tag each step carries in the report:

| situation | what happens | tag |
|---|---|---|
| a rule fires and its fix, measured in the local sandbox, lowers the score (95% interval above 0) | verdict from the rules, $0 | `rules (no model)` |
| a rule fires but the measurement does not confirm it (rules and the cheap consistency check disagree) | the model path is used | `Spark` |
| no rule fires | the model path is used | `Spark` |
| model path needed, offline, no recorded run of the case | verdict `NEEDS_MODEL`, nothing spent. Not a clean bill of health | `rules (no model)` |
| a recorded Spark run of the same case exists in this repo | served from the file, no call | `Spark (recorded run, no new call)` |
| `--referee` and the verdict is INFLATED | one Wonder call may veto it (verdict DISPUTED); it can never create a finding; max 10 calls | `Wonder` |

Every verdict ships a **cost ledger** (calls, estimated tokens and USD per model) and a "who did what" table in the report, followed by the full audit report.
Python API: `agent.hybrid.run_hybrid(case_dir, live=False, referee=False, measure=None, spark_runner=None, ...)` returns a dict; `render_report(res, case_dir)` returns the markdown.
Tests mock the model and the sandbox through `measure=` and `spark_runner=`; `agent.llm.set_replay(traces.jsonl)` also works and books $0.

Honest limits
- The ledger USD is an **estimate** (the per-call figure this repo's spend gate uses, 0.10 per planner call). Real billing and Meta Model API pricing are UNVERIFIED here. Tokens are estimated at 4 characters per token.
- Stored rule measurements (`runs_rulefix/`) are reused only for a case inside this repo whose generated patch hash is identical; the data hash is not stored (UNVERIFIED if `data.csv` changed). Use `--fresh` to re-measure.
- The Wonder referee is untested live. Whether `muse-wonder-1.0` is a useful text referee is UNVERIFIED.
- **What the rules cannot detect** (they recognise a fixed list): evaluating on training rows, scaler/selector/PCA fit on all rows, an id column repeated across the split, an unordered split when a time-named column exists, exact duplicate rows. They match code idioms of this benchmark (top-level `split` function, transformers fit in a top-level function); hashed column names defeat the time rule. Rule author had read the benchmark code, so the free baseline is optimistic.
- **What needs a model**: look-ahead features, offsetting errors, label-conditioned imputation, and anything stated only in prose. No rule fired is not evidence of no leakage.

## 2. CI check

```
python -m agent.ci_check path/to/repo --threshold 0.05 --summary "$GITHUB_STEP_SUMMARY"
```

Audits every case folder under the path. Exit **1** when a case is INFLATED with the 95% interval above 0 and the mean inflation is over the threshold
(0.05 = 5 percentage points for accuracy, 0.05 absolute units for PR-AUC); exit **2** when nothing was audited or a measurement failed; exit **0** otherwise.
The message names the case, claimed and controlled scores, the inflation, the threshold and what found it. A markdown job summary is written to `--summary`.

`.github/workflows/nulllab-audit.yml` runs it on pull requests and pushes. Default is **rules only: $0, no model, no secrets, no network** (the workflow references no secret).
Set `AUDIT_PATH` or use the manual-run inputs to point it at your own case folders.

Honest limits
- Cases where no rule fired are reported `NOT CHECKED`, exit 0: the build is not told the pipeline is clean.
- It executes `train.py` of every case in a restricted subprocess (the runner is the sandbox; `NULLLAB_NO_DOCKER=1`). Do not point it at code you do not trust.
- Spark mode (`--spark --live`) is optional and **not enabled in the workflow**. It needs `MODEL_API_KEY` as a repository secret and goes through `agent/llm.py`'s spend gate, which expects the owner's battle-station tooling: UNVERIFIED on a stock GitHub runner.
- The workflow has not been run on GitHub (UNVERIFIED); the CLI path is tested locally.

## 3. Reproducibility bundle

```
python -m agent.bundle corpus/leak_prescale --run runs_rulefix/leak_prescale.json --out out/bundle.zip [--no-data]
cd out && unzip bundle.zip -d b && cd b && python rerun.py && md5sum -c MANIFEST.md5
```

One zip: preregistration hash and input hashes, the executed patches and a unified `.patch`, traces (run record, plan, event log, raw planner reply when stored; never keys),
the audit report, a standalone `rerun.py` (needs only python, pandas, numpy, scikit-learn), `MANIFEST.md5` (md5sum compatible) and a README with the limits. The zip is deterministic.
Secrets: text files are scanned for `MODEL_API_KEY`, `sk-`/Bearer/AWS/GitHub-token shapes and your environment's key value; hits are replaced with `[REDACTED]` and counted in the README; the build is refused if anything key-looking remains.

Honest limits
- `rerun.py` recomputes **point estimates** for seeds 42/43/44 and compares them to the stored values (checked on `leak_prescale`: all three seeds match). It does not recompute bootstrap intervals (use `python -m agent.audit ... --remeasure` in the repo).
- It is the case folder's code, not the authors' original pipeline. Library-version drift can change scores. `rerun.py` runs code on your machine: read it first.
- The md5 manifest detects accidental change, not tampering. The scan finds key-looking strings, it cannot prove absence.

## 4. Patch export

```
python -m agent.patch_export corpus/leak_prescale --run runs_rulefix/leak_prescale.json --out fix.patch --base-out train.normalized.py
```

Writes the stored fix as a unified diff. The header (ignored by `patch`/`git apply`) carries case, fix, provenance (`rules (no model)` or `Spark: <mode>`), metric,
claimed and controlled score, inflation, seeds, n per seed, the per-seed 95% intervals, and the hash of the base it applies to.
`--config fix_A|fix_B|fix_both` selects the factor. Refuses with exit 2 when the fix changed nothing.

Honest limits
- The diff is taken on the `ast.unparse`-normalised `train.py`, the form the sandbox executed. It applies to `train.normalized.py` (written by `--base-out`), **not** to a hand-formatted original; comments and layout are not preserved.
- Rule R2 patches include the helper code the rule baseline adds (visible in the diff); read it before using the patch.
- It is a proposed control that changes the score as shown, not a proof the authors' pipeline is wrong, and not a fix for leakage types outside the two factors tested.

## Tests

`python -m pytest tests/test_hybrid.py tests/test_ci.py tests/test_bundle.py -q` (offline; fixture numbers are hand-made, none is a measurement).
