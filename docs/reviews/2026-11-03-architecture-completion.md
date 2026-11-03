# Architecture audit completion — 3 November 2026

**Status: architecture audit completed successfully within the revised scope.** This closes the interrupted architecture review; it does not certify that the product is correct or production-ready. The original eight findings in [the architecture review](2026-11-03-architecture.md) remain actionable. This pass reviewed concurrency, model-provider boundaries, budget accounting, result validation, job lifecycle and exports, and added reproducible bounded probes.

Per the owner's current instruction, **no browser walkthrough was attempted** and **no full offline test suite was run**. Full-suite completion is deferred until after the rebuild. There were no paid calls, network requests, real dataset execution, application-source edits or changes to frozen artifacts in this completion pass. Prior incomplete suite output must not be treated as a pass; a pytest lastfailed cache also cannot establish that a full run completed successfully.

## Additional findings

**A09 — Process-wide provider replacement is unsafe for overlapping jobs (P1, reproduced).** `agent/hybrid.py:91–114` temporarily assigns `llm.live_complete` globally. Two overlapping `recording_llm` scopes can wrap one another. A bounded sequential interleaving reproducing overlapping lifetimes counted one fake call in both ledgers, then left the second scope's next call unaccounted after the first scope exited, and restored a stale proxy after both scopes exited. No real model was invoked. `agent/transport.py:299–309` similarly rebinds process-wide functions, and `agent/llm.py:106` holds replay state globally. The current browser does not expose concurrent live audits, so this is a concrete blocker to the planned multi-user/multi-agent integration, not a claim that the present replay page leaks between real users. Inject a provider and ledger per job; scope replay state and cancellation to the job; avoid global monkeypatching in the shipping path.

**A10 — Export provenance can assert that present-day inputs produced historical scores (P1, reproduced).** `agent/audit.py:111–167` chooses a stored result without checking its original input identity. `agent/bundle.py:186–197` copies current case files and hashes them, labelling the hashes “inputs as audited,” while `expected.json` carries the selected old result (`:205–208`). A probe copied the bundled `leak_prescale` fixture into a temporary folder, changed the CSV bytes, and built a ZIP against its original stored run. Export succeeded and described the changed dataset's hash as audited. The benign whitespace edit demonstrates absent byte-identity enforcement, not a claim that this particular edit changes model performance. `agent/patch_export.py:42–75` similarly combines a diff against current normalized source with old numerical claims. Bind exports to the immutable audited snapshot; reject mismatches rather than merely calculating fresh hashes. Record redaction separately because `bundle.py:218–228` can change bytes after original input hashes have been calculated.

**A11 — Host-side statistical calculation lacks an explicit prediction-vector contract (P1, reproduced).** `sandbox/factorial_stats.py:12–13` calculates equality with NumPy arrays without checking matching one-dimensional shapes. A two-label vector and one prediction are silently broadcast; the bounded probe reports accuracy 0.5 and n=2 instead of rejecting malformed output. `sandbox/run_factorial.py:35–43` serializes returned labels/predictions but does not independently establish their identity. Calculating statistics outside the sandbox is useful, but it cannot make unvalidated vectors trustworthy. Validate schema, shape, nonempty sample counts, finite values, allowed metrics/classes, seed completeness and row identities before statistical computation; where feasible obtain evaluation targets from trusted instrument-controlled data rather than treating arbitrary returned labels as ground truth. The probe establishes a host consumer flaw; it is not a claim that the G9 guard necessarily permits this malformed vector on every supported case.

**A12 — Installed transport breaks replay by recursing through its own rebound entry point (P1, coordinator reproduction).** `agent/transport.py:199–200` calls `llm.live_complete_ex` when replay is active. `transport.install()` at `:299–303` has rebound that symbol to the same function. The coordinating reviewer safely reproduced plain replay returning correctly, followed by `RecursionError` after transport installation, and restored transport/replay state afterward. This needs a dedicated replay implementation/provider rather than recursion through a mutable global adapter. This finding is attributed to the coordinator's runtime check; the completion agent independently verified the source path.

**A13 — Current job/artifact lifecycle cannot safely become a hosted auditing service unchanged (P1, source inspection).** `app/server.py:18–23` has a shared rendered index and rewrites report files, and `:95–100` executes a mock case inline. There are no durable job IDs, per-job workspaces, cancellation endpoints, ownership checks or queue lifecycle. `agent/hybrid.py:385–390` writes predictable `r1.json`/`hybrid.json` paths rather than immutable uniquely identified artifacts. File writes are not atomic; a shared caller-supplied output directory can overwrite/interleave job results. The current local trusted use is narrower and should remain labelled accordingly. Before exposing real input, define states such as queued/running/completed/inconclusive/failed/cancelled, store job-local evidence atomically, and retain all attempts without accidentally selecting the first successful historical result.

**A14 — Timeout and spend controls have limits that matter for the new architecture (P2, source inspection).** `agent/transport.py:156–177` bounds caller waiting by a daemon thread and closes a response best-effort; it does not establish that remote inference was cancelled. Retrying can coexist with an abandoned request. `:201–219` gates/counts the logical call once, and retries recheck spend at `:274–278`, while retry attempts have a separate transport log. `_LOCK` is thread-local-to-process protection, not a transaction shared by multiple service processes, and the spend check is not a reservation for all in-flight jobs. Document attempted versus logical calls and unknown billing; use durable budget reservation for concurrent service jobs. Do not equate the deadline with provider cancellation or a strict billing cap. No live cost overrun was attempted or demonstrated.

## Export and reproduction boundaries verified

The ZIP's `rerun.py` (`agent/bundle.py:104–128`) imports and executes case/patch code directly on the recipient's machine; it does not use NullLab's restricted worker. The existing bundle README warns the user to inspect it, so this is a disclosed product boundary, not an undisclosed security exploit. The rebuilt exporter should make the execution boundary explicit at the download/run action, provide exact dependencies/environment details, verify input hashes before execution, and distinguish a score replay from full interval/statistical reproduction. Hashing is accidental-change detection, not proof of origin when the author controls both data and manifest.

## Repeatable probe evidence

Run only the bounded audit script, not pytest:

```powershell
.\.venv\Scripts\python.exe docs\reviews\architecture_completion_probes.py
```

Observed exit code: **0**, about 3.3 seconds. Results:

- Overlapping provider scopes: one call counted in both ledgers = true; second call unrecorded = true; stale proxy restored = true.
- Changed-input export: bundle accepted = true; current hash described as audited = true.
- Invalid vector shape: accepted = true; reported n = 2 and accuracy = 0.5 for all four configurations.

The script uses a fake response provider and a disposable temporary export directory; it never executes the case code or calls an inference endpoint. All mutated module state is restored before exit. The script lives among review artifacts, not the production test suite. The coordinator separately reverified the freeze manifest: **53 files and 10 logs passed**.

The coordinator subsequently reran the saved script with replay-recursion and mixed-verdict probes added and persisted the machine-readable evidence in [architecture-probe-results.json](2026-11-03-architecture-probe-results.json). The implementation checklist now includes T53–T57 for result validation, export provenance, state isolation, job/artifact isolation and replay repair. These additional checks do not change the deferred full-suite status.

## Revised architectural order

1. Retire the disallowed/ambiguous hero and establish a legitimate example, preserving provenance.
2. Define the versioned input/result/job contracts and immutable evidence identity, including exports and explicit replay.
3. Fix verdict semantics and malformed-result rejection before attaching UI or extra agents.
4. Create one supported runner with injected providers, scoped replay/ledgers, portable configuration and bounded budgets; fix transport replay recursion.
5. Harden isolated execution, result validation and the privacy boundary.
6. Add guided input, job lifecycle and UI/API/CI integrations over that runner.
7. Add independently evaluated collaboration and optional open-weight access.
8. Complete fresh scientific evaluation, then the deferred full offline suite and release verification after the rebuild. Browser walkthrough remains excluded by owner instruction.

All architecture review dimensions assigned to this completion pass are now closed with findings or explicit verification limits. Remaining live-provider, billing, hardware, cross-platform, container and full-suite checks are **implementation/release validation work**, not silently claimed audit successes. There is no pending completion-agent task or active test process started by this pass.
