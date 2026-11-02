## Methods (excerpt)
We predict civil war onset in country-year data (1945-2000, about 1 onset per 100 country-years) with a random
forest that down-samples the majority class (30 peace and 90 war observations per tree); its tuning parameter is
chosen by 10-fold cross-validation on the training years only.
The model is trained on 1945-1989 and evaluated on the later years 1990-2000, which it never saw, to mimic forecasting.
## Results
We report the precision-recall performance of the forest on the held-out 1990-2000 country-years.
