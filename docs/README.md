# NullLab docs index

Documents marked **FROZEN** are hash-pinned by a preregistration. Do not edit them; see [FROZEN-FILES.md](FROZEN-FILES.md).

## Method
| Doc | What it is |
|---|---|
| [IDEA.md](IDEA.md) | The idea and why it was chosen |
| [PLAN.md](PLAN.md) | Original planning-room plan |
| [BRIEF-4-factorial.md](BRIEF-4-factorial.md) | Decision: compositional factorial falsification |
| [EVAL-12-G9-DSL.md](EVAL-12-G9-DSL.md) | **FROZEN.** Typed edit DSL and behavioural guard |
| [EVAL-12-G9-INSTRUMENT.md](EVAL-12-G9-INSTRUMENT.md) | **FROZEN.** The G9 instrument: robustness |
| [KILL-LOG.md](KILL-LOG.md) | Ideas and claims that were killed, and why |

## Evals (chronological)
| Doc | What it is |
|---|---|
| [EVAL-2.md](EVAL-2.md), [EVAL-2-RESULTS.md](EVAL-2-RESULTS.md) | 9-case live evaluation |
| [EVAL-3.md](EVAL-3.md) to [EVAL-8-RULEBASED.md](EVAL-8-RULEBASED.md) | Spike gates, hard cases, fidelity guard, real cases, disguised case, rule-based baseline |
| [EVAL-9-G8-PREREG.md](EVAL-9-G8-PREREG.md), [EVAL-9-G8-RESULT.md](EVAL-9-G8-RESULT.md) | **FROZEN.** G8 preregistration and result |
| [EVAL-10-CASES.md](EVAL-10-CASES.md) | **FROZEN.** Second real case (EHG), sources and licences |
| [EVAL-11-EHG-PREREG.md](EVAL-11-EHG-PREREG.md) | **FROZEN.** EHG preregistration |
| [EVAL-13-G9-PREREG.md](EVAL-13-G9-PREREG.md) | **FROZEN.** G9 preregistration |
| [LIVE-RESULT-2026-11-01.md](LIVE-RESULT-2026-11-01.md) | First live run |
| [RESULTS-CARD.md](RESULTS-CARD.md) | One-page results card |
| [AUDIT-REPORT.md](AUDIT-REPORT.md) | Reviewer report produced by `python -m agent.audit` |

## Product and demo
| Doc | What it is |
|---|---|
| [PRODUCT-FEATURES.md](PRODUCT-FEATURES.md) | Audit, CI check, bundle, patch export |
| [DEMO-GUIDE.md](DEMO-GUIDE.md), [DEMO-SCRIPT.md](DEMO-SCRIPT.md), [VIDEO-STORYBOARD.md](VIDEO-STORYBOARD.md) | The 3-minute demo |
| [UX-BRIEF.md](UX-BRIEF.md), [UX-BRIEF-2.md](UX-BRIEF-2.md) | UI briefs |

## Ops
| Doc | What it is |
|---|---|
| [FROZEN-FILES.md](FROZEN-FILES.md), [FROZEN-HASHES.json](FROZEN-HASHES.json), [FROZEN-CHANGELOG.json](FROZEN-CHANGELOG.json) | The freeze manifest and how to record a deliberate change |
| [STATUS.md](STATUS.md), [PROGRESS.md](PROGRESS.md) | Build status logs |
| [BUILDER-BRIEF.md](BUILDER-BRIEF.md), [MUSE-BRIEF-2.md](MUSE-BRIEF-2.md), [MUSE-BRIEF-3.md](MUSE-BRIEF-3.md) | Internal builder briefs (gitignored in the original repo) |

Run `python scripts/freeze_check.py` before and after any change.
