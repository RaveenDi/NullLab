# Independent v2 release review — 3 November 2026

**Status: bounded review and independent closure verification complete; all four findings below are closed in the reviewed source. This is not release approval.** Reviewed current `agent/engine.py`, `agent/provider.py`, `agent/evidence.py`, `agent/intake.py`, `app/server.py`, and `app/static` source. Read the implementation checklist and current regression tests. No browser walkthrough, live APIs, paid calls, full suite, commits, publishing, or product-source edits were performed by this reviewer.

Two small offline probes used synthetic data, mocked worker predictions and an in-memory fake provider. Their disposable artifacts are under ignored `out/release-review-safe/`. Existing suite results and release/evaluation limitations remain as recorded in the implementation checklist; this review does not reclassify historical evidence or establish critic benefit, Glimmer quality or fresh evaluation performance.

## Original findings (preserved; closure evidence below)

### 1. [P1, closed] Export verifies one copy of the controls and archives another

`agent/engine.py:432` calls `evidence.verify(..., r)`, which hashes top-level `r["sources"]` (`agent/evidence.py:103`). The ZIP is then populated from `r["record"]["sources"]` at `agent/engine.py:441–442`. After JSON serialization these are independent copies. A stale or edited nested control can therefore pass the manifest check and be exported as an audited control despite having different bytes.

**Confirmed offline:** created a valid manifest for top-level `# audited control`, put `# DIFFERENT unaudited control` in the nested record, and called `export_bundle`. Manifest verification succeeded and `controls/fix_both.py` contained the unaudited source. No executable candidate code was run.

**Fix:** export only the exact source mapping that was verified, or require both source mappings and manifests to agree before creating the ZIP. Validate the archived patch against the verified original/controlled sources as well. Add a regression that independently changes the nested control and expects rejection.

### 2. [P2, closed] Cancellation during a model request still launches additional requests

Cancellation is checked only by `event()` (`agent/engine.py:213–219`). Between the Baseline and Hypothesis events, the initial critic and up to two planner attempts execute without another cancellation check (`agent/engine.py:286–305`). Cancelling while the initial critic is running therefore still launches a new planner request once the critic returns. Cancelling during an invalid first planner answer can similarly launch the repair attempt. Provider retries are also unaware of cancellation.

**Confirmed offline:** a fake initial critic set the cancellation flag before returning. The fake provider still received roles `["critic", "planner"]`; only then did the engine return `cancelled`. There were no network calls or costs.

**Fix:** check cancellation immediately before each new provider attempt and after each response, including retry/repair boundaries. An already-running remote request can remain billing-unknown; cancellation must prevent subsequent requests from being started.

### 3. [P2, closed] Significant score increases are described as no detected effect

`_summary()` distinguishes consistent negative intervals using sign `"-"`, but the verdict expression at `agent/engine.py:370–374` maps that sign to `NO_EFFECT_DETECTED`. For example, all seeds with an original-minus-control interval `[-0.20, -0.10]` establish a measured increase under the control, yet the UI labels it “No effect detected for this control” (`app/static/workspace.js:8`). This contradicts the measured direction and interval.

**Fix:** represent a consistent increase explicitly, or use a narrowly worded “no evidence of inflation” result that retains the detected opposite effect. Reserve “no effect detected” for intervals that include zero. Keep CLI, UI, copy-note and CI semantics aligned. This finding is established by source inspection; no empirical SECOM outcome is being reinterpreted.

### 4. [P2, closed] Opening recorded evidence loses the active job used by polling and cancellation

The recording handlers set the shared `job` variable to `null` (`app/static/workspace.js:80–81`) without stopping the active poll timer or preserving a separate active job ID. The next poll requests `/api/jobs/null` (`:59`), enters the error handler, and re-enables Run (`:65`) although the original audit continues. Cancel also now targets `/api/jobs/null` (`:77`). A user inspecting the recording during a live audit loses control of that audit and can start another one accidentally.

**Fix:** preserve active-job identity separately from the result being displayed, and keep polling/cancellation attached to that identity while a recording is open. Alternatively disable switching to recordings until the active audit reaches a terminal state. Verify this with a small JavaScript state test; a browser walkthrough is not necessary.

## Independent closure verification

The reviewer inspected the coordinator's repairs and ran `python -m pytest tests/test_engine_v2.py tests/test_provider_v2.py tests/test_workspace_js.py -q --basetemp <unique workspace out directory>`: **19 passed in 4.69 s**. The initial invocation using the sandbox's default temporary directory encountered filesystem permission failures on atomic replacement; the workspace-local rerun passed. This is a focused regression run, not a new full-suite result.

- **Finding 1 closed:** `agent/engine.py:451–457` verifies both manifests and requires both source mappings and manifests to agree. `:462–471` reconstructs and verifies the patch; `:472` allocates a unique ZIP path. The export regression accepts a valid bundle and rejects independently changed nested sources and patch bytes.
- **Finding 2 closed:** `agent/engine.py:213–226` checks cancellation before/after each model call and converts cancellation-related provider failures to terminal cancellation. `agent/provider.py:284–287` checks before every retry dispatch. The focused critic-cancellation regression dispatches only the initial critic. An additional independent mock transport set cancellation while returning HTTP 429: only one transport dispatch and one reserved attempt occurred; no retry was sent.
- **Finding 3 closed:** `agent/engine.py:383–392` maps consistent negative intervals to `CONTROL_SCORE_HIGHER`. `app/static/workspace.js:8` uses “The tested control increased the score,” including copied notes through the shared label mapping. `agent/ci_check.py:61–62` recognizes the verdict as no measured inflation. The negative-effect regression and an independent direct CI interpretation check passed.
- **Finding 4 closed:** recording handlers at `app/static/workspace.js:80–81` retain the shared active job ID; transient polling errors at `:65` retry without re-enabling Run. The minimal-DOM regression opens a recording during an active job, then verifies polling and cancellation retain that job ID and never request `/null`.

No new actionable regression was found in these bounded changes. The exact reviewed SHA-256 hashes are:

| Source | SHA-256 |
| --- | --- |
| `agent/engine.py` | `3e1c9879d1bbb0107d63bdad7d10258cb659dfbc7c7c25da554d2aa0ef0ecc7a` |
| `agent/provider.py` | `5f39e3a73a8d62191c2d1b334e3f041219b5604a295beac7e6cb0c70e2bbc733` |
| `agent/evidence.py` | `de3295450339c4c92d6ef57f617feb5f918bf6af7714d3d3cd936e66c5d79ffa` |
| `app/static/workspace.js` | `a5a25bb923318286eade5b7b19707573decdf5e0a6bef68a9420c6090a6bd05a` |
| `agent/ci_check.py` | `7fbeb13c4f5987ffc96f1e9f366361c3aa50e5a3dad779dad039b934d48169cf` |

## Scope observations

The reviewed path correctly labels model-only no-flaw outcomes, unsupported plans and final critic disputes separately, restricts the HTTP workspace to local peers/hosts, acknowledges outbound code/claim metadata, and keeps unvalidated local-model and external-evaluation work pending. Closure of the four bounded findings does not complete the checklist's remaining release or evaluation items.
