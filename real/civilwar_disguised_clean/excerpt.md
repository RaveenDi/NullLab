## Methods (excerpt)
We train a random forest to predict line-stoppage onset in line-shifts records
(epochs 1-56, about 1 onset per 100 line-shifts) of a factory group. The forest down-samples the majority class
(30 running and 90 stoppage observations per tree) and its tuning parameter is chosen by 10-fold cross-validation.
The model is meant to forecast stoppage onsets in line-shifts it was not trained on.
## Results
We report cross-validated performance: the random forest reaches an area under the ROC curve above 0.9,
which we take as strong predictive power for line-stoppage onset.
