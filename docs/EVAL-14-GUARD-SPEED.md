# EVAL-14: G9 behavioural guard speed fix

Engineering note, 2026-11-02. No model calls, no spend. Performance fix to `agent/guard_g9.py` with identical decisions. Acknowledged in `docs/FROZEN-CHANGELOG.json`.

## 1. Problem

The live G9 run stalled for about 90 minutes inside `guard_g9.behaviour_check` on `real/civilwar_disguised` (7140 rows x 90 features). A py-spy dump showed every thread in `analyze` (the `_arr` generator and the context union). The pipeline tunes `mtry` with 3 grid values x 10 folds = 30 forests of 300 trees, so a trace has 18,600 events per config (9,300 tree fits and 9,300 tree scorings).

Causes, found by reading the code and confirmed by profile:

1. The worker stored one Python list of ints per event, and `json.dumps` / `json.loads` moved them to the parent (about 3 GB in the parent).
2. `analyze` rebuilt a Python `set` from those lists for every event, several times.
3. For every scoring event it rescanned all events since the previous evaluation-scoring event (`ev[prev_end+1:i]`) and unioned their sets. Within one forest all 300 tree scorings see the 300 tree fits as "context", so the cost is quadratic in the number of trees per forest.

## 2. Measurements (Windows laptop, 2026-11-02, `scripts/bench_guard.py`)

Plan: one factor, `replace_split(temporal, epoch)` on `split_rows`, as in the G9 offline replay. `T` = trees per forest (`N_TREES` override). Time is `behaviour_check` only (the two worker runs are separate, about 23-26 s each at T=300 for both versions). Memory is peak RSS of the parent process in MB (sampled every 0.1 s). Original = the frozen file at the baseline commit.

| case | events per trace | original check | original parent RSS | new check | new parent RSS |
|---|---|---|---|---|---|
| civil war T=10 | 620 | 3.4 s | 96 MB | 0.0 s | 38 MB |
| civil war T=20 | 1,240 | 14.0 s | 207 MB | 0.1 s | 42 MB |
| civil war T=40 | 2,480 | 58.6 s | 397 MB | 0.2 s | 46 MB |
| civil war T=80 | 4,960 | did not finish in 230 s | not recorded | 0.3 s | 61 MB |
| **civil war T=300 (real G9 profile)** | 18,600 | **did not finish in 240 s cap** (about 190 s of analysis after 52 s of tracing) | not recorded | **1.2 s** | **123 MB** (274 MB with the worker) |
| EHG (real profile) | 23 / 50 | 0.0 s | 23 MB | 0.0 s | 33 MB |

The original scales x4.1 per doubling of T (quadratic). Extrapolated honestly from T=40: T=300 is (300/40)^2 = 56x, about 3,300 s (55 min) alone, and memory about 7.5x, about 3 GB, matching the observed 3 GB. With the live run's three concurrent cases competing for CPU, a 90 minute stall is consistent. The original's full-size run was not completed (capped at 240 s as instructed); the extrapolation is a model fit on T=10, 20, 40, not a measurement.

Targets (under 90 s and under 1.5 GB for civil war and EHG): met with a wide margin. Decision on the real civil-war plan: ACCEPT, with the same facts as the original at T=10, 20, 40 (all three finished on both versions and gave ACCEPT with equal problems and facts). On EHG both give ACCEPT and equal facts except that the new `fix_contam.ctx` also lists `NearestNeighbors: 0` (section 5).

## 3. Changes

All in `agent/guard_g9.py`:

* Worker: each event's row ids are stored as the set of non-negative ids, packed as a bitset (bit k = row id k), interned by content in a pool shipped once (`rid_pool`, base64). Events carry a pool index. Identical row sets (e.g. the same fold scored by 300 trees) share storage. Lists remain the fallback for non-integer or huge ids.
* `trace_run` decodes the pool into shared `_Packed` objects (`_decode_trace`). Old list-format traces (tests, saved traces) still work everywhere.
* `analyze`: one pass, numpy bit operations. The context window (fit/fn events since the previous evaluation-scoring event, excluding the scoring object's own) is maintained incrementally per component name with a per-name union, per-object unions and a per-row count array, so "union excluding this object" is `(count - own) > 0`. Results are interned `RowSet` objects (an immutable set-like view: `len`, iteration, `&`, `|`, `==`, `in`, `bool`). The original set implementation is kept as `_analyze_sets` and used for traces the packed path does not cover (event index different from position, row ids above 50M).
* `relation_violations`: vectorised for `RowSet` inputs (`max`/`min` / intersection over numpy value arrays), with the original dict code as the fallback when the column has NaN, ids outside the column index, etc., so exceptions and NaN ordering are unchanged.
* `_structure_sig`: compares canonical bytes of the exact row sets instead of `hash(frozenset(...))`.
* Worker object keys: events carry a key that is never reused (weakref-tracked counter) instead of `id(obj)`. See section 5.

Not changed: `behaviour_check`, `model_signature`, `contamination`, `guard_plan`, `_ctor_consts`, the worker's wrappers and provenance rules.

## 4. Equivalence evidence (`tests/test_guard_g9_equivalence.py`)

The test file embeds the complete original `guard_g9.py` as `REF_SRC` (sha256 of its LF form `4a084a1c...`), and loads it as a reference module with its own worker.

* (a) Synthetic: 400 random traces x 3 input forms (lists, packed pool, numpy arrays) comparing the full `analyze` output (every field of every score record including S, R, ctx with key order, eval flags, `untracked_events`, `fn_calls`, `E_synth`), `model_signature`, `contamination`, and `relation_violations` for random/group/temporal and scoped variants; plus 120 traces with NaN columns and 60 with ids missing from the column index (same exception type); plus 500 random (original, fixed) pairs through the full `behaviour_check` x 3 forms with random op lists, resize and hold-step flags: decisions and problem texts and facts identical (reference decision mix: 365 REJECT, 62 UNVERIFIABLE, 50 ACCEPT, 23 KeyError raised identically). Fixed seeds throughout.
* (b) Real workers: both workers run on EHG (move_into_fold, drop_from_eval, clean variant), ESL selection, civil war (temporal, random, clean temporal; 1,500-row subsample, 4 trees): every event field except object keys and row sets are equal, row sets equal, `guard_plan` decisions, problems, layout and crash flag equal, per-config facts equal (see section 5 for the one allowed difference), and the new `analyze` on the original list-format trace equals the reference analysis exactly.
* (c) Offline replay: `NULLLAB_EQ_REPLAY=1 pytest tests/test_guard_g9_equivalence.py -k replay` runs `eval.validate_dsl_replay --allow-unfrozen` into a temp dir and compares it with `runs_g9_offline`: all 82 plans, every decision and problem list, the coverage and crosstab counts, P1/P2/P2b/P3 and PASS are reproduced exactly. (`--allow-unfrozen` is needed because the replay refuses to run when the doc's recorded hash of `guard_g9.py` differs from disk.)
* Unit test that `RowSet` behaves like a Python set (200 random pairs).

## 5. One finding: the original keyed objects by `id()`

The worker identified a model instance by `id(obj)`. CPython reuses an address once a temporary object is freed, so two different estimators (for example the `NearestNeighbors` inside the oversampler and the next `RandomForestClassifier`) can get the same key. In the original, that silently merges them: `last_fit` and the "own object is excluded from the context" rule then see one instance. This depends on the allocator state, so it varies between runs; the stored `runs_g9_offline` facts show runs with and without it (`NearestNeighbors: 185` present in the context). The new worker uses never-reused keys, which makes the trace deterministic and equal to the "no collision" case.

Consequence for equivalence: decisions and problem texts are identical in every comparison above. The only field that can differ between an original run that happened to collide and the new run is the content of `facts[...]["ctx"]`, where the new guard may report an extra component or larger counts (the original's collision hid events). The tests assert that relation (new context is a superset of the original's) and exact equality everywhere else. No decision in the 82-plan replay or the real-case tests depends on it.

## 6. Reproduce

```
python scripts/bench_guard.py --case civilwar_disguised --impl new
python scripts/bench_guard.py --case civilwar_disguised --impl orig --rev <baseline-commit> --trees 40   # a full-size original run exceeds 4 minutes
```

Wrap every original-guard run in `timeout`.

## 7. Frozen-file bookkeeping

* `agent/guard_g9.py`: old LF sha256 `4a084a1c466b1e8ff53ce3da94307796dc7475c275e0fdb889888f182fa17dba`, new `983d2ffe81725ae2ed4703a287b74800270034af712185e2331218e18dce79b8`, recorded in `docs/FROZEN-CHANGELOG.json`. `docs/FROZEN-HASHES.json` was not regenerated. Results produced before this change stay tied to the old hash.
* `python scripts/freeze_check.py verify`: ok. `tests/test_frozen_hashes.py`: passes.
* Known consequence, needs an owner decision: `tests/test_g9_runner.py::test_frozen_eval12_hashes_match_doc` compares the FROZEN_FILE hash printed in the frozen doc `docs/EVAL-12-G9-DSL.md` with the file on disk and fails (it does not consult the changelog). Fixing it means editing a frozen test or doc, which this change did not do. The runner's own source-hash verification (`factorial_g9.verify_problems`, `runs_g9/prereg_log.jsonl`) also compares against the pre-change hash; check that it honours the changelog before the G9 run is resumed.
