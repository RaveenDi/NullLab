## Methods (excerpt)
We train a random forest (100 trees) to detect a rare event in 300 units (about 1 in 8 is positive) from 12 numeric summary
measures per unit. The classes are balanced by adding synthetic positive rows, each placed on the segment between a positive unit
and one of its 5 nearest positive neighbours. Performance is estimated by 10-fold stratified cross-validation.
## Results
The cross-validated ROC-AUC is about 0.96: the detector separates positive from negative units almost perfectly on unseen units.
