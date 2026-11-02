# G9 run stopped by the owner's decision (2026-11-02 17:32 SLT): INCOMPLETE

The live G9 run (`python -m agent.factorial_g9 run 1 2 3 4 5`, started 15:28 SLT, preregistered and frozen in docs/EVAL-13-G9-PREREG.md) was stopped by killing its processes. It did NOT finish its preregistered 16 units. It is reported as an incomplete run, not as a pass or a fail of its acceptance clauses.

## What was recorded before the stop (8 of 16 units)
- `ehg_disguised` (leaky): repeats 1, 2, 3 recorded. `ehg_disguised_clean`: repeats 1, 2, 3 recorded.
- `civilwar_disguised_clean`: repeats 1, 2 recorded.
- NOT recorded (never completed or never started): `civilwar_disguised` (leaky) repeats 1, 2, 3 (started, never finished); `ehg_disguised` and `ehg_disguised_clean` repeats 4, 5 and `civilwar_disguised_clean` repeat 3 (never started, queued behind the stuck units).
- 22 live calls in `live_calls_g9.jsonl` (planner and B3 calls). The last event was written at 15:58 SLT.

## Why it was stopped
Between 15:58 and 17:32 SLT the three worker threads were all busy with the three `civilwar_disguised` (leaky) units and produced no output. A stack dump of the live process (py-spy, 17:2x SLT) showed all three threads inside the behavioural guard, `agent/guard_g9.py` (`analyze` at lines 328-329 and the `_arr` generator at line 288, called from `behaviour_check`). The guard builds a Python set of row ids for every recorded fit and score event; the civil-war pipeline tunes with about 9,000 forest fits over thousands of rows, so the analysis is far too slow (hours, not minutes, for the same case that the G8 harness finished in about 10 minutes). No model call was in flight and no Meta spend accrued while stuck. This diagnosis comes from the stack dump; the exact running time of the analysis was not measured and is UNVERIFIED.

## What this means
- G9's acceptance clauses (EHG direction >= 4/5, 0/5 clean false alarms, size within 0.15 of +0.43 in >= 3/5; civil-war not worse than G8) cannot be evaluated: the preregistered 5 EHG repeats and 3 civil-war leaky repeats do not exist.
- No stalled unit produced an observed outcome, so continuing the missing units is a continuation of unobserved work, not a re-roll. The continuation will be a separate, clearly labelled run (G9b) with its own preregistration, run after a speed fix to the guard that must give identical decisions on every recorded trace. The change to `agent/guard_g9.py` will be recorded in docs/FROZEN-CHANGELOG with the old hash and the reason.
- The 8 recorded units stay reported as recorded, scored as they stand.
