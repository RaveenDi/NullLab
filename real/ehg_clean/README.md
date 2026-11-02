# ehg_apparent / ehg_clean (REAL-PINNED, named columns)

Evaluation-flaw case only: oversampling (SMOTE-style) applied BEFORE cross-validation (`ehg_apparent`, as published-and-criticised)
versus inside each training fold (`ehg_clean`). Source of the flaw: Vandewiele et al., arXiv 2001.06296 (Artif Intell Med 2021).
Data: PhysioNet TPEHGDB v1.0.1 shipped feature file (ODC-By 1.0). Rebuild data.csv with `python eval/build_g8_cases.py <dir>`
(see docs/EVAL-10-CASES.md). Nothing here is medical advice or a clinical claim; the models are not validated for any
clinical use, and a prediction-quality number from these folders must not be read as evidence about pregnancy or birth outcomes.
Medical advice is a hackathon anti-project; this case audits the evaluation only. Ground truth lives in eval/g8_truth.json.
