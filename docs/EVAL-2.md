# NullLab EVAL-2: 9-case live evaluation (protocol + status)

Date: Nov 1, iteration 2. Status: **PROTOCOL READY, LIVE RUN PENDING** — no new live calls were made
in this session (the session shell was unavailable, so `pipeline.py --live` could not be executed and no
`pip install` was possible). Nothing below is presented as a new model result. Earlier measured numbers are
quoted from the earlier recorded runs (the first live run, 3 cases, 3 seeds) and labelled as such.

## Protocol

1. Materialize the corpus: `python eval/build_corpus.py` (writes `corpus/<9 cases>/` + `eval/ground_truth.json`).
2. Run the loop live: `python pipeline.py --live` (plan → act → verify → recover, 3 seeds 42/43/44, n_boot=1000).
   Spend-gated by `bs.py` (`spend check` before every call, `spend add` after); Meta cap is $30.
   Falsifier `max_tokens` stays ≥ 12000 with `reasoning_effort: "low"` (a smaller budget returned empty
   `content` with `finish_reason=length` in the first live run).
3. Run B3 live: `python -m eval.score --live` (one single-prompt call per case, NO code execution).
4. Live-call budget: hard cap **40** (`MAX_LIVE_CALLS` in `agent/llm.py`). Worst case for 9 cases:
   9 extract + 9 falsify + up to 9 recover-retries + 9 B3 = 36 ≤ 40. If the cap trips mid-eval, the eval stops
   and the missing cases are reported as UNMEASURED, not filled in.

## Metrics (per case, then aggregates)

- Verdict per case: FALSIFIED / SURVIVED / INCONCLUSIVE (3-seed agreement required; paired-bootstrap 95% CI
  of claimed−controlled delta must exclude 0 with delta ≥ 0.03 on all 3 seeds for FALSIFIED).
- Recall on the 6 leaky cases; false-alarm rate on the 3 clean cases (must be 0).
- Grounding precision: fraction of the two pointers (`methods_line`+number, `code_line`+number) that match
  the source files under normalised whitespace at the reported line number, after at most one live retry.
  Reported separately from verdicts; `cites_ok` in each run JSON.
- Loop-vs-single-prompt: the loop wins only if recall(loop) ≥ recall(B3) with strictly fewer false alarms
  AND ≥ 1 non-checklist win (B0, B1 and B3 all miss the case; the loop falsifies it with a 3-seed CI).

## Previously measured (earlier sessions, NOT this one)

- Offline MOCK (plumbing only, never a model result): 24 pytest passing; 3/3 seed-fixed; hero FALSIFIED,
  clean SURVIVED, synthetic FALSIFIED; B0/B1 reimplementations 0/2 recall, 0/1 false alarms.
- First LIVE run, 3 cases × 3 seeds (`muse-spark-1.3` as extractor + falsifier): 3/3 verdicts correct
  (hero FALSIFIED, synthetic FALSIFIED, clean SURVIVED), grounding precision 0.5 — every `code_line` missed
  verbatim, which is what iteration-2 step 1 fixes (line numbers + normalised-whitespace verify + one retry).

## New in this iteration (implemented, NOT yet measured)

- 9-case corpus (Kapoor–Narayanan classes): hero (augment-then-split), `leak_prescale` (pre-split
  scaling+selection), `leak_temporal` (random split over drifting time), `leak_proxy` (label-carrying proxy
  feature), `leak_group` (site identifier as a feature, sites repeat across split), `synthetic_leak`
  (target-rate feature), plus 3 clean controls (`clean_control`, `clean_wine_correct`, `clean_group_correct`).
- B3 single-prompt baseline (one call, no execution) for the loop-vs-single-prompt ablation.
- Real-suite probe: the (MOCK, since removed, regenerable with `python -m eval.score`) `runs/ablation.json` recorded whether `deepchecks`/`giskard` are importable. They are not
  installed here; B0/B1 remain labelled reimplementations. To run the real suites:
  `pip install deepchecks` (giskard only if easy), then extend `eval/score.py` — the reimplementation rows
  stay for comparison.

## Known gaps (do not present as done)

1. No new live numbers: verdicts, recall, false alarms, grounding, and the loop-vs-single comparison are
   UNMEASURED until `pipeline.py --live` + `eval.score --live` execute within the 40-call cap.
2. Corpus files for the 6 new cases are not yet materialized (`python eval/build_corpus.py` pending).
3. Mock falsifier routing for the new classes is scripted (regex), same caveat as before: a mock "win" is
   plumbing, not evidence the model can do it.
4. Sandbox is a restricted subprocess, not Docker; sklearn is unpinned (1.9.1 vs planned 1.3).
5. Excerpt claim percentages are nominal; the measured claimed-protocol accuracies came from the MOCK `runs/*.json` (removed in the hygiene pass; `python pipeline.py` regenerates them).
