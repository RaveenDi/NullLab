# NullLab KILL-LOG

## 2026-11-01, BRIEF-4 spike (G0 to G3): kill rule NOT triggered, but only narrowly
Evidence is in [EVAL-3.md](EVAL-3.md). Each clause of the kill rule, checked against the measurements:

| Kill clause | Measured | Triggered? |
|---|---|---|
| G0 not green | pytest 41/41 | no |
| Exfil test fails | 11/11 attempts blocked | no |
| Real Deepchecks or Giskard ≥5/6 **and** ranks the interaction | best result 4/6 (Deepchecks), with 2/3 to 3/3 false alarms; neither tool ranks the interaction | no |
| G2 parse fails | both calls parsed; extractor pointers 2/2 | no |
| Spike I CI includes 0 on any seed, or fix-both drop <5pp | I CI lower bounds +10.8 to +12.2pp; fix-both drop 22.9pp | no |
| B3 ranks correctly **with point inside CI** | B3 ranked correctly (AxB), but its 32pp is outside the CI on 3/3 seeds | no, but **near-miss** |
| Projected spend >$12 additional | +$0.26 logged | no |

**Risk flag:** B3 got the culprit ranking right. The spike survives only because B3 over-predicted the magnitude. With the builder's reference patches, one seed's CI would contain B3's number. Before spending on G4, the owner should decide whether a magnitude-only win is enough for the "execution beats reading" claim.

## 2026-11-01, G4 (4 new cases + 4 clean): preregistered acceptance FAILS on the clean-case clause
Evidence: [EVAL-4.md](EVAL-4.md), `runs_g4/score.json`. Scoring rule sha256 `54c35b18…` was logged before any B3, planner or loop run.

| Clause | Measured | Pass? |
|---|---|---|
| Loop CI sign correct on ≥3/4 new cases | 4/4 (cancellation −, wrong-culprit +, benign 0, synergy +) | yes |
| B3 wrong (sign or culprit or verdict) on ≥2/4 | 3/4 (cancellation: sign and verdict; benign: verdict; synergy: culprit B vs AxB, a 2pp margin) | yes |
| Loop false alarms on clean cases = 0/4 | **1/4** (clean_group_correct, +11 to +15pp on 3/3 seeds) | **no** |

- **Cause:** the planner's "fix" dropped the most label-correlated legitimate feature and changed the CV scheme. The loop has no fidelity check that a patch changes only the named step.
- **The same failure class showed up again** in the EVAL-2 live rerun (`runs_live/`). That run had a loop false alarm on clean_wine_correct: an ordered split on class-sorted rows. The earlier EVAL-2 run had 0/3 false alarms.
- **What is supported:** execution got the sign right where reading got it wrong, in 2 cases:
  - Cancellation: B3 said +7pp, and the planner itself said +9pp. The executed result was −5.5pp; the truth is −10.4pp.
  - Benign: B3 said leak, +3.5pp. Executed, the CI spans 0.
- **What is not supported:** "the loop is reliable on clean code". Its clean false-alarm count (1/4) is close to B3's (2/4).
- **The wrong-culprit design did not fool Spark.**
- **Not pivoting yet.** The recommendation is not "execution adds quantification only", because the cancellation and benign cases show sign and verdict wins.
- **Recommendation:** continue only if a patch-fidelity guard is added and preregistered *before* re-running the clean cases. Example guards:
  - Reject a patch whose fix_X changes the feature set or model hyperparameters, unless step X is about features.
  - Or require the claimed-protocol model to be reused unchanged.

  Re-run all 8 cases with fresh B3 and planner calls, so the guard is not tuned on these results. If the clean false alarms persist, pivot.

## 2026-11-01, G5 (patch-fidelity guard + 3 repeats): preregistered acceptance PASSES; kill rule not triggered
Evidence: [EVAL-5.md](EVAL-5.md), `runs_g5/score.json`. Rule sha256 `734de856…` was logged before any G5 call.

| Clause | Measured |
|---|---|
| Clean false alarms | 1/12 |
| Hard sign right | 11/12 |
| B3 wrong | 9/12 |
| Fidelity audit failures | 0 |

- **Spend:** +$4.72, 52 calls.
- **Residual risk:** wine r2 was a declared, in-scope but unjustified fix (a named column drop plus an ordered split). The guard checks scope, not justification.
- **Independence:** the hard-case repeats are near-identical, so they are weakly independent.
- **Decision:** not pivoting. Keep "execution beats reading on sign/verdict" as the claim, scoped to synthetic cases.
