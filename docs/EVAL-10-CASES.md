# EVAL-10: second REAL leakage case, EHG oversampling before cross-validation (Mon Nov 2, 2026)

Purpose: answer "does NullLab work on a case we did not write?". Builder B. Label: **REAL-PINNED** (real public data, published and
independently corrected flaw), with the honest qualifier that the pipeline is **our port** of the flaw on a smaller feature set, not the
authors' code. This audits an EVALUATION flaw only. No medical advice and no clinical claim (medical advice is a hackathon anti-project).
Loop NOT run (owner preregisters first). Files: `real/ehg_apparent`, `real/ehg_clean`, `real/ehg_disguised`, `real/ehg_disguised_clean`,
`eval/build_g8_cases.py`, `eval/g8_truth.json` (host-only), `runs_g8_cases/` (reference.py/json, probe.py, probe_*.json, call log, traces),
`tests/test_g8_cases.py` (7 tests, pass).

## 1. Sources, licence, files (verified 2026-11-02)
| Item | Finding | Source |
|---|---|---|
| Flaw paper | Vandewiele et al., "Overly optimistic prediction results on imbalanced data", arXiv 2001.06296 v2 (Nov 2020), Artif Intell Med 2021. Claim: SMOTE/ADASYN applied before the train/test split inflates AUC | https://arxiv.org/abs/2001.06296 (PDF read) |
| Code | github.com/GillesVandewiele/EHG-oversampling. **Ships no feature CSVs** (README: `process_feature_files.py` creates `raw_features.csv` from raw signals); no LICENSE file and no licence statement found in the README (**UNVERIFIED** code licence; the arXiv abstract says "open license") | https://github.com/GillesVandewiele/EHG-oversampling |
| Data | TPEHGDB v1.0.1 (Aug 21 2012), 300 records (262 term, 38 preterm), doi 10.13026/C2FW2V, **Open Data Commons Attribution License v1.0** (stated on the PhysioNet page; no LICENSE.txt file at the files URL, 404) | https://physionet.org/content/tpehgdb/1.0.1/ |
| Citation required | Fele-Zorz, Kavsek, Novak-Antolic, Jager (2008), Med Biol Eng Comput 46(9):911-922 | same page |

Raw extraction would be 245 MB of WFDB signals plus re-implementing the authors' per-study features. **Not done.** Instead PhysioNet itself ships
a small per-record feature table (RMS, median frequency, peak frequency, sample entropy, per channel x 3 channels). The case uses that. Downloaded
2026-11-02 06:39 UTC into `real/_downloads/ehg_raw/` (git-ignored; read only as text, never executed). sha256 of every file matches PhysioNet's `SHA256SUMS.txt`.

| File | bytes | md5 | sha256 (matches PhysioNet list) |
|---|---|---|---|
| RECORDS | 5301 | d71fe73b5b3ec0d69accaa27f801456f | dcdc856e...3b0f87 |
| SHA256SUMS.txt | 52554 | 652b73813cad92ddadbc73a5188743fb | n/a (the list itself) |
| tpehgdb.smr | 19037 | 9df80511dae8fb4ae6557a50321f0c5d | c8d2fa75cbb2fc2e1eb9c7a903c458dba49cef694e76f5e7ef05d0d51bb741cc |
| tpehgdb_features__filter_0.08_Hz-4.0_Hz.fvl (**used**) | 100133 | 3e9a7953e1d398e4f4be634c9d2d582f | f5351733629d33ddf67357fb89ea6a2d00842d87a81429d1174c23836041b9d4 |
| tpehgdb_features__filter_0.3_Hz-3.0_Hz.fvl | 100133 | 36174568df8102600f4d3558c7fd04b3 | 8a08962409f72217482a3cfce83290cb5979507a2707cd0cc2314bc5384b7843 |
| tpehgdb_features__filter_0.3_Hz-4.0_Hz.fvl | 100133 | f46b959bdbd6fe1006e73591620ffdf1 | 9bb1795fc85b1aca512f87c44d2841fdb33a8dc89a503a9f1f24f1d9107263be |

Used filter 0.08-4.0 Hz because the paper uses that band. Shipped features are 4 per channel = 12 features, n = 300 records, 38 positives.
The gestation-at-delivery and recording-time columns are deliberately **excluded** (gestation would leak the label by definition).
Redistribution: ODC-By permits it with attribution, but `data.csv` files stay git-ignored and are rebuilt by the script (consistent with the G6 policy).

## 2. Published numbers (arXiv PDF, Tables 2 and 3, AUC x 100)
Oversampling before partition (Table 2, "Reprod.") vs after partition with default oversampler (Table 3 "Default") vs no oversampling ("None"):
| Study | before (leaky) | after, default | None | inflation vs after |
|---|---|---|---|---|
| [27] SVM+SMOTE | 96.57 | 60.75 | 49.54 | +35.8 |
| [30] RF+SMOTE (closest to our model) | 96.40 | 46.97 | 43.78 | **+49.4** |
| [28] AdaBoost+SMOTE | 96.13 | 57.43 | 46.38 | +38.7 |
| [32] NN+SMOTE | 95.63 | 50.74 | 49.10 | +44.9 |
The published reports themselves were 92.0 to 99.4 AUC for these studies. Artificial data (10,000 random 5-D points, 10% positive): 0.95 with
SMOTE first vs 0.49 / 0.48 without or after the split. Published 10-fold stratified CV. Their numbers use their own 298-recording feature
sets (many features per study), so our smaller feature set is comparable only in direction and rough size.
Stored as `published_inflation_roc_auc` = 0.494 (RF row) in `eval/g8_truth.json`; the SVM row (0.358) is the low end of the published range.

## 3. Reference measurement (OFFLINE, no model, `runs_g8_cases/reference.json`; n = 10 seeds, 300 records each)
Pipeline: SMOTE-style interpolation (5 neighbours, standardised distance) to 1:1, random forest 100 trees, 10-fold stratified CV, pooled ROC-AUC.
| Case | mean ROC-AUC | range |
|---|---|---|
| ehg_apparent (oversample first) | **0.970** | 0.965 to 0.975 |
| ehg_clean (oversample inside training fold) | **0.540** | 0.502 to 0.571 |
| ehg_disguised / ehg_disguised_clean | 0.970 / 0.540 | within 0.003 of the named versions per seed |
Inflation mean **+0.430** (per seed +0.40 to +0.47), n = 10. Published RF row: 0.964 vs 0.470 (+0.494); SVM row +0.358. So the direction
reproduces and the size (+0.43) sits between the two published rows. The clean estimate is near chance (0.54), as in the paper (0.44 to 0.61 range).
Disguise is not bit-identical to the named case only through float ties in neighbour search after rescaling (max per-seed difference < 0.01, tested).

## 4. Disguise (G7 recipe v2) and contamination probes
Disguised case: columns `f01..f12`, `target`; each feature multiplied by a power of two (exponents in -4..6, neighbours unchanged because distances
are standardised); excerpt rewritten ("rare event", "units", "synthetic positive rows between a positive unit and its 5 nearest positive neighbours"),
no words SMOTE / preterm / EHG / pregnancy / clinical / medical, no citation-flavoured sentence; train.py comments neutral. Leaky and clean differ in
3 lines only (where `oversample` is called), asserted by test. Row order shuffled (record id order dropped).
Probes: `muse-spark-1.3-contributor`, temperature 0, via `agent.llm.live_complete` (own G8-phase log `runs_g8_cases/live_calls_g8cases.jsonl`, spend check
ran each call). **6 calls, est. USD 0.18** (budget: 8 calls, 0.40). P1 name the source or UNKNOWN; P2 domain of f01..f12; P3 headline ROC-AUC of the
published study, shown the Methods text only (the excerpt's own "0.96" removed, otherwise the number is just read back).
| Case | P1 source | P2 domain (verbatim) | P3 headline | Verdict |
|---|---|---|---|---|
| ehg_disguised (leaky) | UNKNOWN | "anonymized clinical measurements for rare-disease detection" | UNKNOWN | CLEAN |
| ehg_disguised_clean | UNKNOWN | "clinical medical diagnostics ... patient biomarkers/vitals to detect a rare disease" | UNKNOWN | CLEAN |
Word lists for hits: source (Vandewiele, PhysioNet, TPEHG, EHG, Fele, arXiv) and domain (preterm, birth, pregnancy, obstetric, uterine, EHG/EMG, labour,
gestation, maternal, fetal): no hits. **Caveat:** P2 guessed "clinical/medical" (generic, wrong subdomain). Strictly that is a domain-class guess, not the domain;
I count it CLEAN under the rule "names the source, the domain, or the headline", but the owner may be stricter. Passing three probes shows Spark did not
name the source, not that it has no memory. No re-disguise was needed (0 of 3 used). Label: REAL-PINNED, not dev-only.

## 5. UNVERIFIED / limits
- Code licence of github.com/GillesVandewiele/EHG-oversampling (none found; we copied no code, our `oversample` is a fresh numpy implementation).
- The PhysioNet-shipped features are the dataset authors' (Fele-Zorz et al.), not the Vandewiele feature sets; the case does not reproduce Vandewiele's
  per-study numbers, only the flaw and its direction. Their Table 3 "after" values are not an exact target for ours.
- Published inflation is a range (+0.36 to +0.49 over the four rows quoted), model dependent; the stored truth value 0.494 is the RF row.
- Record count: paper used 298 recordings (two dropped for short length); PhysioNet table has 300. We use all 300.
- sklearn 1.9.1, seeds 0 to 9; RF `random_state` = seed.
- Rebuild: `python eval/build_g8_cases.py real/_downloads/ehg_raw 2`, then `python runs_g8_cases/reference.py`.

## 6. TargetFinder (step 5)
Not attempted: steps 1 to 4 consumed the timebox and probes need no further owner approval pass; no probes were run for it.
