# NullLab docs

Documents marked **FROZEN** are hash-pinned by a preregistration. Do not edit them; see [FROZEN-FILES.md](FROZEN-FILES.md). Run `python scripts/freeze_check.py verify` before and after any change.

## Product docs
| Doc | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | How the loop, sandbox, guard and report fit together |
| [DEPLOYMENT.md](DEPLOYMENT.md) | Deployment options, rules and the pre-deploy checklist |
| [SECURITY.md](SECURITY.md) | Threat model and what the sandbox does and does not stop |
| [USAGE.md](USAGE.md) | Audit, CI check, bundle and patch export: commands and the case-folder layout |
| [AUDIT-REPORT.md](AUDIT-REPORT.md) | The reviewer report produced by `python -m agent.audit` |

## Evidence
Each EVAL doc states its protocol, the raw files it rests on and what was and was not shown. Docs 9 to 13 are **FROZEN**.

| Doc | One line |
|---|---|
| [EVAL-2.md](EVAL-2.md), [EVAL-2-RESULTS.md](EVAL-2-RESULTS.md) | Nine-case live evaluation: protocol and results |
| [EVAL-3.md](EVAL-3.md) | Spike gates G0 to G3: sandbox hardening, synthetic factorial case, baseline tools |
| [EVAL-4.md](EVAL-4.md) | G4: cases where reading alone should get it wrong |
| [EVAL-5.md](EVAL-5.md) | G5: patch-fidelity guard and three repeats |
| [EVAL-6.md](EVAL-6.md) | G6: a real published correction and a textbook case |
| [EVAL-7.md](EVAL-7.md) | Disguised civil-war case, split-use rule, traces, muse-wonder probe |
| [EVAL-8-RULEBASED.md](EVAL-8-RULEBASED.md) | A no-LLM, rule-based baseline against the loop |
| [EVAL-9-G8-PREREG.md](EVAL-9-G8-PREREG.md), [EVAL-9-G8-RESULT.md](EVAL-9-G8-RESULT.md) | **FROZEN.** G8 hardened loop on the disguised pair: preregistration and result |
| [EVAL-10-CASES.md](EVAL-10-CASES.md) | **FROZEN.** Second real case (EHG): sources and licences |
| [EVAL-11-EHG-PREREG.md](EVAL-11-EHG-PREREG.md) | **FROZEN.** EHG preregistration |
| [EVAL-12-G9-DSL.md](EVAL-12-G9-DSL.md), [EVAL-12-G9-INSTRUMENT.md](EVAL-12-G9-INSTRUMENT.md) | **FROZEN.** Typed edit DSL, behavioural guard and instrument robustness |
| [EVAL-13-G9-PREREG.md](EVAL-13-G9-PREREG.md) | **FROZEN.** G9 preregistration |
| [EVAL-14-GUARD-SPEED.md](EVAL-14-GUARD-SPEED.md) | G9 behavioural guard speed fix |
| [EVAL-15-G9B-PREREG.md](EVAL-15-G9B-PREREG.md) | G9b: continuation of the G9 units that never produced an outcome |
| [KILL-LOG.md](KILL-LOG.md) | Claims and ideas that were killed, and the evidence |

### Frozen-file policy
Files that a preregistration hashed must stay byte-identical and keep their path. The manifest is [FROZEN-HASHES.json](FROZEN-HASHES.json), the checker is `scripts/freeze_check.py`, deliberate changes are logged in [FROZEN-CHANGELOG.json](FROZEN-CHANGELOG.json), and the rules are in [FROZEN-FILES.md](FROZEN-FILES.md).

## Repository layout
| Path | What it is |
|---|---|
| `agent/` | Product core: claim extraction, falsifier, loop runners, fidelity and behavioural guards, audit, bundle, CI check, patch export, model transport |
| `sandbox/` | Restricted executor and the runners that measure edits on a case |
| `baselines/` | Comparison methods: single-prompt reading, checklist, rule-based fixer |
| `eval/` | Evaluation builders, truth files, scoring and regression scripts (evaluator side only) |
| `report/`, `app/` | Demo UI: static report pages and SPA, and the FastAPI server that serves them |
| `scripts/` | Freeze checker, guard benchmark, baseline-tool probes |
| `tests/` | Offline test suite (also pins the frozen behaviour) |
| `corpus/`, `factorial/`, `real/` | Cases: synthetic corpus, synthetic factorial cases, real and disguised published cases |
| `runs_*/` | Preregistered evidence, one folder per generation: `runs_spike4` (EVAL-3), `runs_live` (EVAL-2/4 rerun), `runs_g4` to `runs_g7` (EVAL-4 to 7), `runs_rulefix` (EVAL-8), `runs_g8` and `runs_g8_cases` (EVAL-9, 10), `runs_ehg` (EVAL-11), `runs_g9_offline`, `runs_g9` and `runs_g9b` (EVAL-12 to 15). Contains prereg logs and call logs; never edited |
| `logs_spike4/`, `runs/` | Raw logs behind EVAL-3 and the live call logs (`runs/live_calls_*.jsonl`) |
| `pipeline.py`, `nulllab_cli.py`, `g4.py`, `g5.py`, `g6.py` | Entry points and early-generation modules; `g4.py` to `g6.py` are frozen and imported by frozen code, so they stay at the root |

A restructure of the root into a proper package layout is planned after the demo; frozen paths stay put until the manifest is re-issued.
