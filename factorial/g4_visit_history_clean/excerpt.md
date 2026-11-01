## Methods (excerpt)
We predict whether an outpatient visit ends in an adverse event from five routine lab measurements plus the patient's historical adverse-event rate, computed from training labels only (out-of-fold).
Whole patients were held out: 25% of patients form the test set (group split by patient, fixed random seed); test patients receive the training prior as their rate.
## Results
Our model achieves 61% accuracy on held-out patients and is intended to triage new patients at their first referral.
