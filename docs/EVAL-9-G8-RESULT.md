# G8 result (scored exactly as frozen in EVAL-9-G8-PREREG.md)

G8 is a NEW labelled run after G7 failed its preregistered acceptance. G7 stays reported as failed and is not merged with, or re-scored by, G8.

Case: `civilwar_disguised` (leaky) and `civilwar_disguised_clean`, disguise recipe v2, `muse-spark-1.3-contributor`, temperature 0.7, 5 repeats each. Provenance: REAL-PINNED data, disguised. Scored with `python -m agent.factorial_g8 score` (`runs_g8/score.json`).

| Clause (preregistered) | Needed | Measured |
|---|---|---|
| (a) direction right | at least 4 of 5 | 4 of 5 |
| (b) clean false alarms | 0 | 0 of 5 |
| (c) inflation within 0.15 of +0.36 | at least 3 of 5 | 4 of 5 |
| Harness-INCONCLUSIVE (target, not a pass clause) | 0 of 10 | 1 of 10 (not met) |

Acceptance clauses (a) to (c): met. Harness target: not met.

Leaky repeats: r1 INCONCLUSIVE (harness failure: api_error, a read timeout after about 500 s, the transport problem described in EVAL-12-G9-INSTRUMENT.md); r2 to r5 inflation found, measured +0.340, +0.339, +0.341, +0.328 (published +0.36). Clean repeats: all five "no effect (interval spans 0)", measured -0.005, -0.005, -0.004, -0.015, -0.005.

Caveats (stated up front):
- The SPLIT-USE-REQUIRED guard rejected a random-split first plan in the leaky repeats; the temporal split comes from the guard plus the model, not from the model alone (see the room note `claude-round4/skeptic.md`).
- The rules baseline (EVAL-8) was never run on the disguised case; rules matched or beat the loop on the undisguised civil-war case.
- Spark's refusal to name the source in two probe calls shows it did not name it, not that it has no memory of it.
- n = 5 per arm; these are counts, not rates. Unpaired bootstrap intervals.
- The one harness failure is counted in the denominator and listed; it was not re-rolled.
- Spend: about 15 planner-side calls, estimated USD 1.50 (estimates, not billing).
