# NullLab reviewer report: `python -m agent.audit` (Mon Nov 2, 2026, SLT with ET alongside)

One command turns finished run files into one self-contained page a reviewer can read, check and paste from.
It makes **no API call and no network request**. Code: `agent/audit.py` (also `python nulllab_cli.py audit ...`). Tests: `tests/test_audit.py`.

```
python -m agent.audit <case_dir_or_run_dir> --report out.html|out.md [--case NAME] [--repeat K] [--run FILE] [--remeasure]
```

- `<case_dir>` (has `train.py`, `excerpt.md`): the run is looked up in `runs_*/`. Loop runs are preferred over rule-baseline records, newer run dirs over older ones, repeat r1 first. `--run FILE` and `--repeat K` pin it.
- `<run_dir>` (for example `runs_g6`): needs `--case` when the dir holds several cases. The tool says so and stops otherwise.
- Supported inputs: loop runs (`rK.json` with a `loop` section; g5, g6, g7) and rule-baseline records (`runs_rulefix/<case>.json`). A case with no finished run, or a missing `excerpt.md`, stops with a plain message.
- Output is HTML or Markdown by file extension. The same files give the same bytes (no clock, no randomness; tested). Input files are never modified (tested).
- `--remeasure` is the only step that executes anything: it re-runs the **stored** patches in the local sandbox (still no API) and appends how far the new drop is from the stored one. The one-line rerun command printed in the report uses it. On a scratch case it reproduced the stored drop exactly (tested).

## What the page contains

| # | Section | Source | Notes |
|---|---|---|---|
| header | provenance badge | `eval/g6_truth.json` / `g7_truth.json` (host-side metadata), the path (`factorial/`, `corpus/`), the run dir name | **SYNTHETIC / REAL-PINNED / TEXTBOOK / MOCK**. A run dir named `*mock*` or a plan whose mode says MOCK gets MOCK |
| 1 | Claim as stated, with source | `excerpt.md` (file path and sha256 prefix); for real cases the paper and the published correction from the truth file | the Results text is quoted verbatim |
| 2 | Claimed vs controlled score | `stats` in the run file | per seed 42/43/44: claimed, controlled, drop, **95% interval (unpaired bootstrap)**, n claimed and n controlled; mean; A alone, B alone, interaction. "Counts, not rates" is printed |
| 3 | Exact patch diff, "only step X changed" | the stored `sources` against the claim's `train.py` (both through `ast.unparse`) | the steps named come from the stored fidelity line; the A-only and B-only diffs are in collapsed blocks |
| 4 | Fidelity check | the stored line plus an **offline re-audit** of the stored plan (`fidelity.build_configs`, `check_static`, and `check_justification` if `data.csv` is present) | also checks that the stored sources are identical to the ones rebuilt from the plan, so a tampered source is flagged (tested) |
| 5 | Preregistration hash and timestamp | `prereg_log.jsonl` next to the run (the planner record of that repeat, the retry record if any, the scoring rule) or `PREREG.sha256` for rule records | if there is no record the page says so in orange |
| 6 | One-line rerun command | built from the paths | offline, no API |
| 7 | What we could not test | generated | see below |
| 8 | Leakage type | patch plus the planner's description of each suspect step | Kapoor and Narayanan taxonomy, arXiv:2207.07048 |
| 9 | Suggested note to the authors | template, filled from the numbers | written as a reviewer comment, hedged, and honest about the sign (see below) |
| 10 | Copy as reviewer note | same facts | plain text, 140 to 155 words on the samples (test bound 110 to 190); a Copy button (inline script, no external call) |

### What we could not test (generated, not hand-written per case)
- The original pipeline, raw data and software versions were not re-run (with the port notes for real cases).
- Only two evaluation steps (A and B) varied per run. Model, metric and features are held fixed.
- The interval covers test-row sampling over 3 seeds only.
- A forecasting claim whose control is not time-ordered (flagged when the excerpt says forecast/future and the mapped type is not temporal).
- The case's own "not reproduced" flaw from the truth file (for example the civil-war imputation correction).
- Contamination, when `probe.json` in the run dir says the source was recognised.
- Synthetic origin; MOCK origin ("do not cite as evidence"); a scored sample under 100 rows.
- For a rule-baseline record: that it is a fixed library without a model.

### Leakage-type mapping
Types: L1.1 No test set, L1.2 Pre-processing on train+test, L1.3 Feature selection on train+test, L1.4 Duplicates, L2 Illegitimate features, L3.1 Temporal leakage, L3.2 Non-independence, L3.3 Sampling bias.
- **Loop runs.** One type per factor (A, B): the one with most keyword hits in the planner's description of that suspect step, plus a hint from a declared `feature` kind (L2). Entries are ranked by the factor's measured drop, so the primary type belongs to the factor that carries the effect. A tie goes to the lower taxonomy number.
- **Rule records.** The rule that fired maps directly: R1 to L1.1, R2 to L1.2 or L1.3 (selector or not), R3 to L3.2, R4 to L3.1, R5 to L1.4.
- The report says the mapping is by keyword rules and should be checked by hand. L3.3 (sampling bias) cannot be found from a patch and is never assigned by the tool.

### The note is not always a leak note
- **Sign +:** says "may be inflated", names the changed steps, the claimed and controlled values, the seeds, n, the per-seed intervals, the pattern and what to report instead, and the caveat.
- **Sign 0:** says "No evidence of inflation", that this is not proof, and asks for nothing (tested).
- **Sign − or mixed:** says the change does not support an inflation reading.

## Samples (generated from existing run files, no API) in `runs_rulefix/audit_samples/`
| File | Case | Provenance | Source run | Result shown |
|---|---|---|---|---|
| `civilwar_apparent.html` | civilwar_apparent | REAL-PINNED | `runs_g6/r1.json` | PR-AUC 0.384 claimed → 0.154 controlled (+0.231); interval excludes 0 on 2 of 3 seeds; L1.1 No test set |
| `esl_selection.html` | esl_selection | TEXTBOOK | `runs_g6/r1.json` | accuracy 99.3% → 46.7% (+52.7 pp); L1.3 primary |
| `g4_assay_replicates.html` / `.md` | g4_assay_replicates | SYNTHETIC | `runs_g5/r1.json` | accuracy 92.2% → 62.3% (+29.9 pp); L3.2 primary |
| `g4_assay_replicates_rulefix.md` | same case | SYNTHETIC | `runs_rulefix/g4_assay_replicates.json` | rule baseline: 92.2% → 81.4% (+10.8 pp); only `split_idx` changed |
| `civilwar_apparent_rulefix.html` | civilwar_apparent | REAL-PINNED | `runs_rulefix/civilwar_apparent.json` | rule baseline: +0.296 PR-AUC on 1785 rows |

Re-audit of the loop samples: accept, stored sources identical to the rebuilt ones. Regenerate with:
```
python -m agent.audit real/civilwar_apparent --report out.html
python -m agent.audit factorial/g4_assay_replicates --run runs_rulefix/g4_assay_replicates.json --report out.md
```

## Styling
Light, white-and-orange, using the tokens of `report/index.html`: warm off-white `#F2EFEA`, ink `#111111`, orange `#E8501F`, white cards, system font stack. No external request (tested: no `src`/`href`/`url()`/`@import`/`http`). Checked in the preview pane at a 269 px viewport: no horizontal page overflow (tables scroll inside their card; long URLs and hashes wrap).

## Tests (`tests/test_audit.py`, 14, all offline)
Every required element is present; deterministic bytes; no external requests; note length and no markup; Markdown output; a null finding is not written as a leak; re-audit matches and catches a tampered source; inputs untouched; a run dir with several cases needs `--case`; taxonomy mapping for loop and rule records; provenance badges including MOCK; a rule-baseline record on a scratch case with `--remeasure` reproducing the stored drop; and the two real g6 samples (skipped if `runs_g6/r1.json` is absent).

## Limits and UNVERIFIED
- **UNVERIFIED:** the taxonomy labels are used as given in the task brief for arXiv:2207.07048; the paper was not re-fetched in this session.
- **UNVERIFIED:** the Copy button was not exercised in a real browser (the page text and layout were read in the preview pane; the clipboard call has a `execCommand` fallback).
- `n_boot = 1000` is printed as "set in the g5/g6 drivers, not stored in the run file". Rule records do store it.
- The patch diff of a loop run is the planner's rewrite of whole functions, so it can be larger than the idea ("only step X changed" is a statement about steps, not lines).
- The keyword mapping can mislabel an unusual description. For the assay sample it ranks L3.2 above L2, and both are shown.
- Only loop (`rK.json`) and rule records are supported. Spike and legacy G4 `loop.json` files with whole-file patches are not.
