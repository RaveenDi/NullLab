# Researcher workflow roadmap

The immediate user is an author who wants to know whether a reported binary pipeline evaluation supports a concrete deployment or research claim, what remains unresolved, and what to do next. This focus comes from internal code/API probes and AI review, not validated demand. A strong hackathon demonstration should show that decision being handled honestly; adding agent personas alone does not establish quality or impact.

## Now: complete and demonstrate one investigation

| Priority | Researcher need | Implemented direction | Completion evidence needed |
|---|---|---|---|
| 1 | “Are we evaluating the task I actually intend?” | Compact author brief, predictor exclusions and metadata roles, visible generated protocol, pre-execution missing-information/unsupported gates. | Supported/unknown/unseen/future regression checks; generated source cannot bypass its role contract. An author declaration remains labelled as such. |
| 2 | “What should I do with this objection?” | Recorded review room, open questions, new generated-case revision with parent linkage and a fresh audit. | End-to-end revision/re-audit test; previous case/result bytes remain unchanged; unresolved facts gate again. |
| 3 | “Can my coauthor recover and inspect this?” | Saved history, permalink reopen, descriptive comparison and a distinct assessment ZIP for unmeasured outcomes. | Recovery/active-job tests, verified snapshot identity, no fabricated control or causal ranking, clear private-input export disclosure. |
| 4 | “Can I trust the demonstration?” | Preserve SECOM's planted-flaw provenance, population caveat and Wonder's dispute; retain both fixed cohorts and their failures. | Current packaged-source tests and reproducible artifacts. No reroll of a failure into a claimed fresh success. |

These are workflow and integrity deliverables, not measured user impact. The current CSV adapter remains a generated baseline, not an automatic reproduction of a paper or arbitrary notebook.

## Next: validate value before adding scope

1. **Observe real author tasks.** Ask a few consenting researchers or students to bring a small permissible binary pipeline and a concrete claim. Record where they misunderstand declarations, abstentions, baseline scores and exports. Measure task completion and errors before proposing time-saving claims. No researcher is currently recruited; this is an open gate.
2. **Freeze new evaluation cases and the instrument.** Add genuinely new supported, clean, incomplete and unsupported cases with truth defined before results are inspected. Retain every outcome and distinguish protocol coverage, execution success, statistical behavior and model judgments. Use a matched one-planner baseline before claiming critic benefit.
3. **Bind clarification rationale more precisely.** Add stable question IDs and answer/source references where they help coauthors distinguish a factual correction from an unsupported assertion. Parent input hashes and a verified linked-audit identity are recorded already; sources supporting the author's answers remain a separate need. This should complement exact job snapshots, not turn chat memory into evidence.
4. **Make baseline semantics machine-readable.** Distinguish a generated baseline, external-reference reproduction and no-skill reference. A numeric baseline or `reproduced` field must not imply that a publication's result has been reproduced when no external reference exists.
5. **Add read-only import adapters.** Start with notebook/repository or experiment-tracker metadata and show the mapping to the existing supported contract. Keep an explicit author review step. Do not accept arbitrary remote code into a public executor as a convenience feature.

## Later: separate capability validation

| Candidate | User decision it could support | Prerequisite before shipping a claim |
|---|---|---|
| Row-aware paired inference and group/time evaluation | Whether a result generalizes across records, entities or periods | Stable prediction-row/group/time identities from the real executor; declared target population; validated resampling and interval coverage; no removal of current inconclusive safeguards as a shortcut. |
| Claim/evidence issue ledger | Which conclusion is supported, disputed or awaiting evidence | Every change cites an input, artifact or author source; model opinion cannot resolve an empirical issue without a test. |
| Local open-weight reasoning | A private, no-user-key research workflow | Actual supported runtime/hardware, bounded latency/cost measurements and new-case model-quality evaluation. Compatible transport alone is insufficient. |
| Literature and dataset specialists | Whether a claimed gap or data source is credible | Source retrieval, precise citations, license/privacy checks and a separate evaluation of retrieval/interpretation. This is not validated by binary pipeline controls. |
| Collaborative or hosted workspace | Reliable multi-person access to permissible studies | Access control, quotas, isolation, data lifecycle, authenticated provenance and a verified deployment boundary. The current loopback service is not a public execution platform. |

The design follows the general research requirements of separating training/evaluation information, stating scope and preserving reproducibility metadata. These support the architecture; they do not establish preference for this interface. See scikit-learn's [common pitfalls](https://scikit-learn.org/stable/common_pitfalls.html) and [cross-validation guidance](https://scikit-learn.org/stable/modules/cross_validation.html), and the NeurIPS [paper checklist](https://neurips.cc/public/guides/PaperChecklist).

New ideas should earn priority by resolving an observed researcher decision, fitting the supported evidence contract, and having a bounded acceptance test. Keep external impact, general accuracy and competition scores unclaimed until evidence supports them.
