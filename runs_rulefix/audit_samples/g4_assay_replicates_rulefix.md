# Audit: g4_assay_replicates

**Provenance: SYNTHETIC** | rulefix run | sign + | built from `runs_rulefix/g4_assay_replicates.json` without any API call

## 1. Claim as stated

> Our model achieves 92% accuracy on held-out wells and is intended to triage newly synthesised compounds.

Methods as stated: We predict whether a compound is active from 12 plate-reader readouts; each compound was assayed in three wells, and failed reads (about 15%) were imputed.
Wells were randomly divided into 75% training and 25% test with a fixed random seed.

Source of the claim text: `factorial/g4_assay_replicates/excerpt.md` (sha256 `ac1ab58f9c06b641`). Provenance: Synthetic case built by NullLab; no external source.

## 2. Claimed vs controlled (accuracy)

Drop = claimed minus controlled. Interval: 95%, unpaired bootstrap over test rows.

| seed | claimed | controlled | drop | 95% interval of drop | n claimed | n controlled |
|---|---|---|---|---|---|---|
| 42 | 91.6% | 81.9% | +9.7 pp | [+5.5, +13.9] | 525 | 525 |
| 43 | 92.4% | 80.8% | +11.6 pp | [+7.6, +15.6] | 525 | 525 |
| 44 | 92.6% | 81.5% | +11.0 pp | [+7.2, +15.0] | 525 | 525 |
| mean | 92.2% | 81.4% | +10.8 pp | | | |

Factors (mean drop): A alone +10.8 pp, B alone +0.0 pp, interaction +0.0 pp.

## 3. Exact patch: only split_idx changed

```diff
--- train.py (claim)
+++ fix_both (executed)
@@ -23,5 +23,6 @@
 
 def split_idx(df, seed, test_size=0.25):
-    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)
+    idx = np.arange(len(df))
+    return next(GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed).split(idx, groups=np.asarray(df['c_2cd377'])))
 
 def claimed_eval(df, seed):
```

## 4. Fidelity check

Stored: `rules applied R3; steps changed split_idx`

Re-audit: not applicable (rule-baseline record: no model-written plan to audit)

## 5. Preregistration

- rulefix_prereg: 2026-11-02T02:49:20Z sha256 `b10c5b88ad50525a8a643833017ed494b7ec5e2fe7dcede68970d90a6c3a3fd2`
- PREREG.md sha256 `b10c5b88ad50525a8a643833017ed494b7ec5e2fe7dcede68970d90a6c3a3fd2`

## 6. Rerun (offline, no API)

```
python -m agent.audit factorial/g4_assay_replicates --run runs_rulefix/g4_assay_replicates.json --case g4_assay_replicates --remeasure --report out.html
```

## 7. What we could not test

- This record comes from a fixed rule library with no model: it applies standard remedies to code idioms it recognises and cannot reason about the claim.
- We re-ran the evaluation code in the case folder, not the authors' original pipeline, raw data or software versions.
- Only two evaluation steps (factors A and B) were varied per run. Other leakage types were not examined, and the model, metric and features are held fixed by construction.
- Intervals come from an unpaired bootstrap over test rows for 3 seeds (42/43/44). They do not cover variation across training sets, model initialisations or a fresh draw of the data.
- The case is synthetic (built by NullLab). A real study can differ in ways that matter.

## 8. Leakage type (Kapoor and Narayanan, arXiv:2207.07048)

- **L3.2 Non-independence between train and test samples**: rule R3 fired and was applied

## 9. Suggested note to the authors

> The headline result (92%) appears to depend on the evaluation protocol: related samples sit on both sides of the split.
>
> In our reanalysis the code was run with only split_idx changed (fidelity guard: rules applied R3; steps changed split_idx). The same model then scored 81.4% against 92.2% under the claimed protocol (metric: accuracy), a drop of +10.8 pp (mean of seeds 42/43/44; 95% unpaired-bootstrap intervals for the drop: seed 42 [+5.5, +13.9]; seed 43 [+7.6, +15.6]; seed 44 [+7.2, +15.0]; 525 rows scored by the claim, 525 after the change).
>
> This matches the leakage pattern 'Non-independence between train and test samples' (L3.2, Kapoor and Narayanan 2023). We would ask the authors to report the score under a split that keeps related samples (the same patient, site, compound or well) on one side, or to explain why the current protocol is appropriate for the stated use.
>
> We did not re-run the authors' original pipeline and cannot rule out that other choices explain part of the gap.
>

## 10. Copy as reviewer note

```text
The reported result (92%) may be inflated: related samples sit on both sides of the split. With only split_idx changed, the same model scores 81.4% instead of 92.2% accuracy (+10.8 pp, mean of seeds 42/43/44). The 95% unpaired-bootstrap interval for the drop excludes zero on 3 of 3 seeds (seed 42 [+5.5, +13.9]; seed 43 [+7.6, +15.6]; seed 44 [+7.2, +15.0]); 525 rows scored by the claim, 525 after the change. Separately, step A alone moves the score by +10.8 pp, step B alone by +0.0 pp, and their interaction by +0.0 pp. Pattern: Non-independence between train and test samples (L3.2, Kapoor and Narayanan). Please report the score under a split that keeps related samples (the same patient, site, compound or well) on one side, or justify the current protocol. Caveat: we re-ran the evaluation code supplied, not the authors' full pipeline; 5 limits are listed in the audit report.
```
