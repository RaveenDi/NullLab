## Methods (excerpt)
We compare a random forest with logistic regression models for predicting civil war onset in country-year data
(1945-2000, about 1 onset per 100 country-years). The forest down-samples the majority class (30 peace and 90 war
observations per tree) and its tuning parameter is chosen by 10-fold cross-validation.
The models are meant to forecast civil war onsets in country-years they were not trained on.
## Results
We report cross-validated performance: the random forest reaches an area under the ROC curve of 0.91 and
offers superior predictive power for civil war onset compared to logistic regression.
