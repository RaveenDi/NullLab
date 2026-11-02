## Methods (excerpt)
We classify 50 samples (two equal classes) from 5000 quantitative measurements.
We first screen the measurements, keeping the 100 with the strongest correlation with the class labels, then build a
1-nearest-neighbour classifier on this subset and estimate its prediction error by 5-fold cross-validation.
## Results
The cross-validated error rate is about 3%: the classifier separates the two classes almost perfectly on new samples.
