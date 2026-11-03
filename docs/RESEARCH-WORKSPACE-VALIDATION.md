# Researcher workspace validation

The research room produced an internal development review, not interviews with external researchers. Its findings, objections and accepted changes are in [the decision record](reviews/research-room/DECISIONS.md). The [architecture](ARCHITECTURE.md) and [roadmap](RESEARCHER-ROADMAP.md) describe implemented behavior and future evidence gates.

## Integrated changes

- Author-declared decision time, population, predictor availability and column roles; nonnumeric metadata can remain in the CSV without entering the generated features.
- Pre-execution missing-information and unsupported-design gates; represented-entity baselines remain descriptive. Declarations do not establish scientific validity.
- Complete generated-template AST matching, explicit custom-code role warnings, and intake/storage instrument hashes. Editing `feats()` while leaving `PREDICTORS` unchanged is rejected.
- Actual recorded review contributions, actionable reviewer abstentions, per-seed baseline evidence and aggregate data diagnostics.
- New generated-case revisions with exact CSV preservation, parent input hashes and verified linked-audit identity; no upgrade of prior outcomes.
- Saved history, reopen links, active-job separation and strictly descriptive comparison. Request generations keep late responses from mixing conclusion/download identity. Interrupted checkpoints cannot appear as finalized measurements.
- Separate input-bound unmeasured assessment ZIPs and measured control bundles. Both include source/data, exclude unbound adjacent files and require review before sharing.
- Bounded atomic JSON replacement retry for transient Windows sharing locks; permanent failure preserves the last complete checkpoint.

## Checks and retained failures

The first integrated check passed **78 tests**. Independent review then reproduced two client-state issues and identified unactionable reviewer abstentions; these were repaired with regressions. The next run passed **84 tests and failed one** when a concurrent file reader/sync lock prevented Windows checkpoint replacement. The failed job and XML remain in `out/pytest-research-room-final` and `out/research-room-validation-final.xml`. It was not a model failure or a new scientific case score.

After the bounded atomic-write repair, **87 tests passed**. The final integrated suite, including interrupted-result comparison, passed **88 tests in 16.81 seconds**: study/provenance, engine, API, minimal-DOM client state, provider, storage and integrity checks. See `out/research-workspace-release.xml`. The TestClient dependency emitted one deprecation warning; it did not affect the assertions. **12 CI/real guard compatibility checks also passed**. Ruff, JavaScript parsing and freeze verification passed; the freeze checker retained 53 files and 10 logs. No historically frozen source was modified by this workflow addition.

The initial sandboxed run stalled at the local TestClient boundary and was interrupted. The completed integration runs used local Windows socket/process access, without hosted inference. No browser walkthrough was performed. The earlier historical full run remains **474 passed, two failures subsequently repaired, one optional replay skipped**; the entire historical suite was not rerun for this addition.

## Real offline author workflow

An internal synthetic 120-row CSV went through actual API intake, an unresolved audit, clarification into a new case, a real three-seed Random Forest baseline, saved history, reopening, comparison and both assessment exports. It completed in **19.95 seconds with zero model calls**. Outcomes were NEEDS_INFORMATION then NOT_TESTED. Only `sensor_a` and `sensor_b` became predictors; entity/time metadata and the post-test target proxy stayed excluded. Original CSV bytes and earlier case/result hashes were unchanged. Comparison correctly refused direct comparability after the declaration changed.

The baseline average precision was 0.718620 (seed scores 0.740671, 0.729962, 0.685226), on 120 rows per seed. This verifies execution, not scientific clearance, a measured treatment effect, model accuracy on a new benchmark or real-user value. Original acceptance summary and job files remain under `out/research-room-acceptance`; the latest pointer is `out/research-room-acceptance-summary.json`.

## Packaged and installed checks

The refreshed explicit source archive was extracted, built into a wheel and tested independently of the working tree: **81 included product tests passed in 28.89 seconds**. The wheel was installed into a new local target. Eleven core/UI file bytes matched current source, a real 60-row three-seed generated baseline ended NOT_TESTED with zero model calls, an unmeasured assessment exported, and the original measured SECOM evidence still exported with verified identity. The smoke script initially used the wrong path for that historical artifact; correcting the path reused the already completed baseline instead of rerunning it. See `out/source-research-workspace-tests.xml` and `out/installed-research-workspace-smoke.json`.

Local TestClient and package builds required Windows access outside the restrictive sandbox; the first sandbox build hit an atomic metadata-file permission denial. Local tools and no-index/no-dependency builds were used. There was no global package installation. The localhost service was refreshed only after verifying its process identity and absence of active jobs; startup made no model calls.

Fresh model-quality evaluation, matched critic benefit, validated group/time inference, local-model quality and outside-user evidence remain open. The two original synthetic cohorts and SECOM's disputed interpretation are unchanged. Current artifact hashes and publication state belong in out/RELEASE-MANIFEST.json; [release status](RELEASE-STATUS.md) records the remaining gates.
