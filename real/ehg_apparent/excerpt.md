## Methods (excerpt)
We classify 300 records (38 in the rare class) from 12 signal features (RMS, median frequency, peak frequency and sample
entropy of 3 channels). The rare class is oversampled with SMOTE (5 nearest neighbours) until the classes are balanced, then a
random forest (100 trees) is evaluated by 10-fold stratified cross-validation.
## Results
The cross-validated ROC-AUC is about 0.96: the classifier separates the two classes almost perfectly on unseen records.
