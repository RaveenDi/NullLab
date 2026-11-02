# Audit: g4_assay_replicates

**Provenance: SYNTHETIC** | loop run | sign + | built from `runs_g5/r1.json` without any API call

## 1. Claim as stated

> Our model achieves 92% accuracy on held-out wells and is intended to triage newly synthesised compounds.

Methods as stated: We predict whether a compound is active from 12 plate-reader readouts; each compound was assayed in three wells, and failed reads (about 15%) were imputed.
Wells were randomly divided into 75% training and 25% test with a fixed random seed.

Source of the claim text: `factorial/g4_assay_replicates/excerpt.md` (sha256 `ac1ab58f9c06b641`). Provenance: Synthetic case built by NullLab; no external source.

## 2. Claimed vs controlled (accuracy)

Drop = claimed minus controlled. Interval: 95%, unpaired bootstrap over test rows.

| seed | claimed | controlled | drop | 95% interval of drop | n claimed | n controlled |
|---|---|---|---|---|---|---|
| 42 | 91.6% | 66.3% | +25.3 pp | [+20.9, +30.1] | 525 | 525 |
| 43 | 92.4% | 58.7% | +33.7 pp | [+29.0, +38.3] | 525 | 525 |
| 44 | 92.6% | 61.9% | +30.7 pp | [+26.3, +35.0] | 525 | 525 |
| mean | 92.2% | 62.3% | +29.9 pp | | | |

Factors (mean drop): A alone +10.8 pp, B alone +6.3 pp, interaction +12.8 pp.

## 3. Exact patch: only claimed_eval, impute, split_idx changed

```diff
--- train.py (claim)
+++ fix_both (executed)
@@ -15,5 +15,6 @@
     df = df.copy()
     cols = feats(df)
-    df[cols] = df.groupby(TARGET)[cols].transform(lambda s: s.fillna(s.mean()))
+    means = df[cols].mean()
+    df[cols] = df[cols].fillna(means)
     return df
 
@@ -23,10 +24,24 @@
 
 def split_idx(df, seed, test_size=0.25):
-    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)
+    from sklearn.model_selection import GroupShuffleSplit
+    import numpy as np
+    groups = df[COMPOUND].to_numpy()
+    gss = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
+    tr, te = next(gss.split(np.arange(len(df)), groups=groups))
+    return (tr, te)
 
 def claimed_eval(df, seed):
-    data = impute(df)
-    tr, te = split_idx(data, seed)
-    f = feats(data)
-    X, y = (data[f].to_numpy(), data[TARGET].to_numpy())
-    return (y[te], fit_predict(X[tr], y[tr], X[te], seed))
+    tr, te = split_idx(df, seed)
+    f = feats(df)
+    train = df.iloc[tr]
+    test = df.iloc[te]
+    means = train[f].mean()
+    train_f = train.copy()
+    test_f = test.copy()
+    train_f[f] = train[f].fillna(means)
+    test_f[f] = test[f].fillna(means)
+    Xtr = train_f[f].to_numpy()
+    ytr = train_f[TARGET].to_numpy()
+    Xte = test_f[f].to_numpy()
+    yte = test_f[TARGET].to_numpy()
+    return (yte, fit_predict(Xtr, ytr, Xte, seed))
```

## 4. Fidelity check

Stored: `only step(s) claimed_eval, impute, split_idx changed (split/fit_scope)`

Re-audit: ACCEPT

## 5. Preregistration

- loop_planner g5-r1: 2026-11-01T07:35:41Z sha256 `8184602e77a9e499e08554667ac727093199cb1cf10e175cd8833351a183ec0e`
- scoring_rule: 2026-11-01T07:33:46Z sha256 `734de8562057e9b60c8feec534db2f845b2fc728c7698fe3b7c0fd7d4d2076d3`

## 6. Rerun (offline, no API)

```
python -m agent.audit factorial/g4_assay_replicates --run runs_g5/r1.json --case g4_assay_replicates --repeat 1 --remeasure --report out.html
```

## 7. What we could not test

- We re-ran the evaluation code in the case folder, not the authors' original pipeline, raw data or software versions.
- Only two evaluation steps (factors A and B) were varied per run. Other leakage types were not examined, and the model, metric and features are held fixed by construction.
- Intervals come from an unpaired bootstrap over test rows for 3 seeds (42/43/44). They do not cover variation across training sets, model initialisations or a fresh draw of the data.
- The case is synthetic (built by NullLab). A real study can differ in ways that matter.

## 8. Leakage type (Kapoor and Narayanan, arXiv:2207.07048)

- **L3.2 Non-independence between train and test samples**: the planner's description of suspect step A mentions 'compound', 'identity across', 'well '
- **L2 Illegitimate features**: the planner's description of suspect step B mentions 'label into features', 'leaks the label', 'target-conditioned'

## 9. Suggested note to the authors

> The headline result (92%) appears to depend on the evaluation protocol: related samples sit on both sides of the split.
>
> In our reanalysis the code was run with only claimed_eval, impute, split_idx changed (fidelity guard: only step(s) claimed_eval, impute, split_idx changed (split/fit_scope)). The same model then scored 62.3% against 92.2% under the claimed protocol (metric: accuracy), a drop of +29.9 pp (mean of seeds 42/43/44; 95% unpaired-bootstrap intervals for the drop: seed 42 [+20.9, +30.1]; seed 43 [+29.0, +38.3]; seed 44 [+26.3, +35.0]; 525 rows scored by the claim, 525 after the change).
>
> This matches the leakage pattern 'Non-independence between train and test samples' (L3.2, Kapoor and Narayanan 2023). We would ask the authors to report the score under a split that keeps related samples (the same patient, site, compound or well) on one side, or to explain why the current protocol is appropriate for the stated use.
>
> We did not re-run the authors' original pipeline and cannot rule out that other choices explain part of the gap.
>

## 10. Copy as reviewer note

```text
The reported result (92%) may be inflated: related samples sit on both sides of the split. With only claimed_eval, impute, split_idx changed, the same model scores 62.3% instead of 92.2% accuracy (+29.9 pp, mean of seeds 42/43/44). The 95% unpaired-bootstrap interval for the drop excludes zero on 3 of 3 seeds (seed 42 [+20.9, +30.1]; seed 43 [+29.0, +38.3]; seed 44 [+26.3, +35.0]); 525 rows scored by the claim, 525 after the change. Separately, step A alone moves the score by +10.8 pp, step B alone by +6.3 pp, and their interaction by +12.8 pp. Pattern: Non-independence between train and test samples (L3.2, Kapoor and Narayanan). Please report the score under a split that keeps related samples (the same patient, site, compound or well) on one side, or justify the current protocol. Caveat: we re-ran the evaluation code supplied, not the authors' full pipeline; 4 limits are listed in the audit report.
```
