# NullLab EVAL-2 results: 9 cases, LIVE muse-spark-1.3 (Sun Nov 1, ~12:00 SLT)

Run by the evaluation driver: `python pipeline.py --live` then `python -m eval.score --live`. 27 live calls, Meta spend about $1.0 (running total $9.84 of the $30 cap). The mock runs (formerly runs_mock2/) were removed in the hygiene pass; `python pipeline.py` regenerates them. Corpus: 9 cases written by builder agents (6 leaky, 3 clean), small and synthetic or sklearn-derived. Rates below are from 9 cases and are not population estimates.

| Method | Recall (6 leaky) | False alarms (3 clean) |
|---|---|---|
| **NullLab loop** (plan -> execute -> verify, 3 seeds) | **5/6** (leak_prescale INCONCLUSIVE: seeds disagree) | **0/3** |
| **B3 single-prompt Spark (no execution)** | **6/6** | **0/3** |
| B0 Deepchecks-style checklist (our reimplementation, real Deepchecks not installed) | 0/6 | 0/3 |
| B1 fixed GroupKFold (only applicable to 3 cases) | 1/6 | 0/3 |

- Grounding precision (verbatim line citations): **1.0** (was 0.5; the line-number fix worked).
- `non_checklist_win` is false for every case: B3 catches everything the loop catches.

## Honest reading
1. **Detection is not where the loop wins.** Every flaw in this corpus is visible in the code, so asking Spark to read it is enough (6/6). The 'loop beats single prompt' ablation FAILS on detection.
2. **Where the loop adds something:** it MEASURES the damage (claimed vs controlled accuracy with a CI) and can disagree with a confident static call: B3 flagged `leak_prescale` at 0.95 confidence, the experiment says the effect is small and seed-dependent (INCONCLUSIVE). That is the defensible value: quantified inflation and avoiding false alarms on suspicious-looking but harmless code.
3. The corpus is too easy for the claim 'executing experiments matters'. Needed: cases where STATIC reading fails: (a) code looks clean but the DATA contains the leak (duplicates / near-duplicates, label-correlated identifiers only visible by running); (b) code looks suspicious but the measured effect is negligible (B3 should false-alarm, the loop should not).
