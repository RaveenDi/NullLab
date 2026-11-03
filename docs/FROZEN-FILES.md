# Frozen files

The G8, EHG and G9 preregistrations hash their inputs. Those files must stay byte-identical (after CRLF -> LF normalisation) and keep the same repo-relative path, or the recorded hashes no longer describe what ran.

- Manifest: [FROZEN-HASHES.json](FROZEN-HASHES.json) (53 files plus 10 prereg logs).
- Checker: `python scripts/freeze_check.py verify` (also `write`, `list`).
- Test: `tests/test_frozen_hashes.py` runs the same checks, including the hashes written inside `runs_ehg/` and `runs_g9/prereg_log.jsonl` and the combined G8 digest.

## What is frozen

| Group | Files |
|---|---|
| Runner and pipeline code | `agent/{factorial_g9,factorial_ehg,factorial_g8,factorial_g7,factorial_g5,factorial_g6,factorial,transport,smoke,cached_exec,edit_dsl,guard_g9,contract_g9,llm,fidelity}.py`, `g4.py`, `sandbox/{executor,run,run_factorial,factorial_stats}.py`, `baselines/rulefix.py` |
| Truth and builders | `eval/{build_g8_cases,build_g7,run_rulefix,regress}.py`, `eval/g8_truth.json`, `eval/g7_truth.json` |
| Agent views | `real/{ehg_disguised,ehg_disguised_clean,civilwar_disguised,civilwar_disguised_clean}/{train.py,data.csv,excerpt.md}` |
| Preregistration docs | `docs/EVAL-9` to `EVAL-13` (G8, cases, EHG, G9 DSL, G9 instrument, G9 prereg) |
| Tests pinning frozen behaviour | `tests/test_{g7,g8,g8_cases,g9_runner,ehg_runner,guard_g9,dsl}.py` |
| Prereg logs | every `runs_*/prereg_log.jsonl` |

Prompts, contract text, op specs and the rules payload live inside the frozen modules, so they are covered by the file hashes.

## Rules

1. Do not edit, move or rename a frozen file. Refactors keep old paths importable or leave the file alone.
2. Prereg logs are append-only. A completed log is pinned in full. `runs_g9` is a live run, so only its freeze records (up to `g9_prereg_doc`) are pinned; later lines are free to grow. The checker compares the pinned prefix.
3. Where a log lists several records of one kind (a re-freeze), the last one binds. For example `runs_ehg` has two `ehg_source_hashes` records; the first is superseded.
4. `*.csv` under the frozen case folders is gitignored in this repo, so these files are protected by the manifest only until someone force-adds them.

## Recording a deliberate change

Example: a post-tag security fix to `sandbox/run.py` (the network block runs after `import train`) will change its hash. Do not regenerate the manifest to hide it. Append an entry to [FROZEN-CHANGELOG.json](FROZEN-CHANGELOG.json):

```json
{"path": "sandbox/run.py", "old_sha256": "<hash in FROZEN-HASHES.json>", "new_sha256": "<new LF sha256>",
 "reason": "block network before importing train.py", "date": "YYYY-MM-DD"}
```

Optional field `old_sha256_crlf` (sha256 of the OLD content with CRLF line endings): add it when the file is one of the G8 digest inputs (`G8_FILES` in `scripts/freeze_check.py`), because the runs_g8 combined digest was computed over the old bytes in either line-ending form. `sandbox/run_factorial.py` and `sandbox/executor.py` carry it.

The sandbox security fix of 2026-11-02 is recorded this way for `sandbox/{run,run_factorial,executor}.py`, `agent/{cached_exec,smoke,guard_g9}.py` (see [SECURITY.md](SECURITY.md)). The G9, G9b and EHG runners' `verify` stage compares code hashes with their freeze logs and will refuse to start a new run on this code; those runs are finished, their results stay tied to the old hashes.

The test accepts a difference only when both the old and the new hash match an entry exactly, and it also accepts it against the hashes quoted in the prereg logs. Any further edit changes `new_sha256` and fails again. Results produced before the change stay tied to the old hash; say so in the result doc.

The curated source archive omits full historical datasets and some runners. Full historical freeze verification requires the complete Git repository and applicable inputs. Retained hash metadata does not substitute for absent data.
