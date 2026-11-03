# Independent architecture review — 3 November 2026

**Closed by follow-up review:** [Architecture audit completion](2026-11-03-architecture-completion.md) verifies the remaining dimensions and records additional reproducible findings. Browser walkthrough is excluded by owner instruction; the full offline suite is deferred until after the rebuild. This is completed architectural assessment, not release certification.

Scope: source inspection, offline probes and local verification. No live model calls, no application changes, no frozen evidence edits. This review distinguishes the research runners from the user-facing product. References are repository-relative, with line numbers from this checkout.

## Main assessment

NullLab has substantive experiment-control engineering. It is currently a specialized local ML-evaluation audit harness with a replay UI, not a general multi-agent research platform. The principal execution gap is that the polished evidence and strongest research runner do not form the path a new user actually executes.

## Highest-priority findings

1. **The product uses an older, weaker execution path than the strongest results.** `agent/hybrid.py:185-208` imports the G5 planner and static fidelity guard. The planner writes replacement Python functions (`agent/factorial_g5.py:15-18`), rather than using G9's four-operation edit DSL and behavioral guard. The hybrid also lacks the G9 transport installation, smoke preflight and separate repair budgets. `docs/ARCHITECTURE.md` acknowledges this, but a judge seeing the overall technical-depth story can easily assume the shipped audit has those guarantees. Integrate a new product runner around the validated G9 components, preserving historical frozen files, or explicitly show separate research/product capability tables.

2. **Live use is tied to the owner's workstation.** `agent/llm.py:16-17,38-50` expects `C:\dev\bs\.env` or an environment key and a sibling `battle-station/bs.py`. A stock clone cannot use the model merely by following `.env.example`. The spend gate should remain fail-closed, but needs a portable, repository-owned provider/budget configuration. Historical call counts also govern new product calls (`agent/llm.py:137-175`); this checkout counted 157 against the default 190 cap. This is a research-run budget, not a usable per-user quota.

3. **Configured alternative endpoints are ignored.** `.env.example` and `docs/ARCHITECTURE.md:206,242` advertise `MODEL_BASE_URL`. `agent/llm.py:14,194` uses a hardcoded endpoint; `agent/transport.py:96` also uses `llm.BASE_URL`. Offline source verification found no `MODEL_BASE_URL` reference in the adapter. A local OpenAI-compatible model server cannot be selected as documented. Role routing has a related product mismatch: G5 plan/retry calls omit `role`, so `NULLLAB_MODEL_PLANNER` is not selected on this path (`agent/factorial_g5.py:60-78`; hybrid proxy passes through the omitted role).

4. **A stored verdict can be reused for changed inputs.** `agent/hybrid.py:162-175` selects a successful recorded Spark result solely by case basename under the repository; there is no input/code/excerpt hash match. An offline probe in a disposable temporary fake repository replaced both `train.py` and `data.csv`, and the old result was still selected. Rule cache validation only checks generated patch hashes, not data (`agent/hybrid.py:143-155`). `--fresh` controls only rule measurements; it does not disable recorded Spark lookup. Every reusable result needs a complete content manifest, and replay should be an explicit mode. This directly threatens the product's central evidence-integrity promise.

5. **The subprocess boundary is insufficient for public uploads, with a concrete write-policy weakness.** `sandbox/run.py:56-70` allow-lists the working directory and Python prefixes for every `open` event without inspecting open mode/flags. The policy therefore permits writes to allowed Python-prefix paths when OS permissions permit; this is not just the documented ability to read installed packages. No write into a real Python installation was attempted. Together with the acknowledged native-code bypasses, this rules out safely hosting arbitrary uploaded code under this boundary. `sandbox/executor.py:76-96` always uses subprocess for factorial runs. Existing Docker support only covers the older single-experiment path and is unverified. Keep the current product local/trusted-code or validate isolated workers before accepting untrusted code.

6. **Failed calls vanish from the product cost ledger.** `agent/hybrid.py:106-107` adds a ledger entry only after a successful response. A simulated timeout, without network, produced ledger calls=0 and estimated USD=0. The lower-level adapter does log attempts, but the product summary contradicts it. Record attempted calls before dispatch and distinguish completed/failed/unknown-billed outcomes; use provider usage where available instead of character-count token estimates.

7. **CI can return green without auditing a case.** `agent/ci_check.py:60-88` maps `NEEDS_MODEL` to `NO_RULE_FIRED` and returns exit 0 when all cases are unchecked/unresolved. An offline run on `corpus/leak_group` printed NOT CHECKED and returned 0. The textual caveat is honest, but a green required check will be interpreted as clearance. Add a configurable strict coverage policy and report audited/total counts directly in the check status. This is a product-policy gap, not a hidden claim that the current code proved the case clean.

8. **Privacy wording understates model inputs.** `agent/factorial.py:44-49` sends the excerpt, full training script and the first five CSV data rows. The dataset is not uploaded wholesale, but raw row samples do leave the machine during live use. Show an outbound-data preview and let users redact/approve it. Disguising feature names is not sufficient privacy protection for private rows.

## What is genuinely implemented

- A deterministic rules-first audit and local sandbox measurement route that needs no model key.
- Structured model proposals, rejection/retry and measurement-based verdicts.
- A stronger research-only typed-edit and behavioral-check pipeline.
- Stored traces, source/freeze checks, reviewer reports, reproducibility bundles and patch exports.
- A local FastAPI presentation server. It serves repository cases and mock reruns; `app/server.py:98-105` calls the older mock pipeline. It has no intake route for a user's repository, notebook or data upload, no authentication and no user/job persistence.
- An optional one-call veto referee. This is not a collaborative room of autonomous literature/dataset/code/statistics agents. Most named stages are deterministic code; the reading-only role is an experimental baseline, not a collaborating agent.

## No-key and local-model feasibility

The current $0 experience is rules, replay and mocked plumbing; it does not provide fresh general reasoning. Three distinct future options should be communicated separately: developer-funded hosted inference with quotas (no user key, operator pays); local open-weight inference (no provider key, user supplies hardware/compute); and optional bring-your-own-provider for advanced users. Model quality, memory, latency and context limits require measurements on the actual chosen model and machine. A smaller model is not automatically equivalent to the current planner.

The existing provider boundary makes local support plausible, but it needs the endpoint fix, local/no-auth credential behavior, portable budgets, capability-aware payload options (the current request forces reasoning_effort and at least 12,000 output tokens), and the same held-out evaluation as the hosted model. Do not claim local support based on configuration fields alone.

## Focused architectural direction

Before adding many roles, make one real user's claim → code/data contract → independent proposed control → reproducible measurement → actionable report work through one supported entry point. The present case contract requires hand-shaped `train.py`, `load`, `feats`, `claimed_eval`, `data.csv` and an excerpt. A notebook/repository adapter with an explicit intended-use statement is more valuable immediately than another agent label.

If adding multi-agent work, keep it bounded: an auditor proposes a suspected flaw and minimal control; an independently prompted challenger attacks the control's validity and can abstain; a deterministic executor measures accepted controls. Exchange evidence objects (claim, source, tested change, result, uncertainty), not conversation summaries. Do not equate agent agreement with correctness. Measure improved valid findings, reduced false alarms, latency and cost against the existing single-planner baseline.

## Verification

- `python scripts/freeze_check.py verify`: **passed, 53 files and 10 logs**.
- Offline disposable probes: stale recorded-result selection confirmed; failed-call ledger omission confirmed; unchecked CI case returned 0.
- `python -m ruff check .`: **not run successfully; Ruff is not installed in the existing `.venv`**. No dependency installation was performed.
- The earlier main offline pytest run did not have a collected final result before the agent's usage-limit interruption; at least one failure was observed then. Its final status remains unknown. Per the owner's subsequent instruction, the full offline suite will run after the rebuild. No clean-suite claim is made.

No model-quality, latency, billing, fresh-install, Docker, Linux, hosted-service or live-referee validation was performed in this review.
