# CI, fresh internal evaluation and video plan — 4 November 2026

The owner authorized repairing the remaining historical CI failure, publishing the local interface, running fresh evaluation and preparing a 2:30–3:00 video plan. No deployment, public video upload or submission was performed. No application browser walkthrough was performed.

## CI repair

The [first pushed run](https://github.com/RaveenDi/NullLab/actions/runs/41696111945), commit `125e8b7`, reported **459 passed, one failed, 78 skipped and four deselected**. The failure was `tests/test_g9b_runner.py::test_run_stage_mocked_then_score_complete`: its scheduler/model/pipeline were mocked, but the B3 input builder still read gitignored historical data. On a fresh checkout that read failed and was recorded per unit before the mocked model call, leaving the asserted call list empty.

The repair makes this scheduling/scoring test self-contained: its case paths deliberately do not exist, and its agent-view builder returns an explicit test fixture. Five B3 calls, eight pipeline units, persisted repeat sizes, complete score and no-rerun behavior remain asserted. An additional assertion verifies that every B3 input used the stub. No production historical runner, outcome, acceptance rule or skip list was changed. The targeted test passed locally. The workflow's obsolete “never run on GitHub” comment was corrected.

The full local CI-equivalent suite and the new remote run are separate checks. Their completed results are appended at this release checkpoint; no pending run is counted as green. The [repository CI page](https://github.com/RaveenDi/NullLab/actions/workflows/ci.yml) supplies actual remote status.

## Fresh evaluation and repair

[Full report](../EVAL-V2-RELEASE.md). Forty actual instrument sources and ten new fixed cases were captured before execution. All scheduled outcomes remain retained: original live coverage **0/3** supported flawed controls, because the initial independent critic lacked the edit contract and returned malformed unsupported assessments. The failure was not rerolled.

The critic prompt now receives the same contract as the planner and separates capability from pipeline validity. Strict validation remains. Its **22 focused engine checks passed**, including new regression coverage for the observed defect. One intermediate test collection syntax error was corrected before confirmation preparation/inference and is disclosed in the report.

A distinct six-case confirmation captures 41 sources and new fixed CSV bytes. It measured **3/3** controls, with one disputed result, one no-effect result and one descriptive/inconclusive group result. Three clean cases received unmeasured model judgments; no empirical specificity or general accuracy is established. No harness failure or positive inflation verdict occurred in that live confirmation. Two schedules: **26 attempts, $4.84735975 reserved estimate**, no rerolls, within predeclared case/cohort/project ceilings. Exact source transitions and every provider outcome remain separate from the earlier two cohorts.

## Interface and video

The local changes include viewport-aware sections, a centered compact vector wordmark/header, smaller footer, finite reduced-motion-aware landing animation and fullscreen/focus workspace. Their earlier focused checks passed **26 tests**; offline component renders covered **102 fixed states at ten sizes**, with HTTP(S) blocked. No new scientific result is inferred from those interface checks. The dated [shell review](2026-11-04-shell-validation.md) remains its original checkpoint.

The [2:55 storyboard](../../submission/storyboard.md) supplies precise screen actions, mode/export constraints and on-screen emphasis. The [complete transcript](../../submission/transcript.txt) has 309 spoken words. It starts with the real-data constructed manufacturing result, shows the author decision and Spark's intervention, retains Wonder's challenge, and ends with inspectable evidence. Recording/upload remain owner work; no generated agent conversation or hidden reroll is planned.

## Publication verification

Ruff, both JavaScript parse checks and freeze verification passed; the historical manifest remains **53 files/10 logs**, unchanged. Exact-byte Git attributes preserve both new cohorts and their source snapshots. Source/evaluation packaging includes both original and confirmation outcomes and the complete video materials. Final artifact/build/test and remote publication results are recorded below when verified.

## Local completion checks

The full offline CI-equivalent run completed with **548 passed, one optional historical replay skipped and four deselected in 1213.63 seconds**. This process imported the engine before the final critic-prompt edit; the final edit is covered separately by the passing 22-test engine run and fresh confirmation. Do not combine them into a single post-edit full-suite claim. The final pushed Linux CI run will check the integrated version. One Starlette TestClient dependency deprecation warning remains; it does not fail the suite.

The curated source built a wheel successfully. A preliminary archive-test invocation from the repository directory passed 94 checks; a second invocation from inside the extracted archive explicitly verified its engine import path to avoid working-tree contamination. Its final result is recorded below. The verified idle localhost service was refreshed to the repaired engine, and read-only health/static-asset checks passed with zero model/job dispatches.

The isolated extracted-source invocation completed **94 passed in 63.61 seconds**, with zero failures and the same dependency deprecation warning. Its printed engine path points inside the extracted source tree. No model calls were made. Subsequent documentation-only packaging refreshes retain the identical tested product/test bytes.

The isolated installed wheel matched **12 current core/UI file bytes**. A real three-seed clean scaling baseline completed NOT TESTED at mean accuracy 0.824074 with zero model calls; its unmeasured assessment ZIP exported successfully. The original measured SECOM ZIP also exported after identity verification. This smoke validates installation/execution/export, not scientific reliability.

## Verified public source and CI

Product commit **[edb44d1831c99447f711b11d89af17eb13b503c5](https://github.com/RaveenDi/NullLab/commit/edb44d1831c99447f711b11d89af17eb13b503c5)** was pushed to `main`. Its [GitHub CI run 41715520171](https://github.com/RaveenDi/NullLab/actions/runs/41715520171) **passed**: Ruff, freeze verification (**53 files/10 logs**) and **473 passed, 78 skipped, four deselected in 297.00 seconds**. The skips concern absent gitignored historical inputs/optional replay; slow/live tests are deselected. The repaired mocked G9b scheduling test executes without those inputs and is not added to a skip list. One TestClient dependency warning and runner/action runtime migration notices remain non-blocking.

The original failed run remains linked above. The source tree was clean after publication; all 337 newly staged evidence files were checked byte-for-byte in Git and no configured credential or private path was included among 374 changed files. Both new cohorts retain their original outcome hashes. Source/demo/wheel asset bytes match, source/evaluation archive manifests verify, and ten current guides had no missing local links. The video plan/transcript are published source materials, not a recorded video. A subsequent documentation-only follow-up records this completed result without changing tested product/test bytes; the current repository badge points to its actual CI status.
