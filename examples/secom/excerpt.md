# Manufacturing quality evaluation

Estimate pass/fail screening quality for production entities drawn from the observed process distribution. This is a constructed benchmark on real UCI SECOM sensor records, not a forecast or a deployed quality-control system. Metric: average precision (PR-AUC). Three stratified folds; resampling placement is part of the evaluation under review. Missing measurements are replaced with a fixed zero constant, not a learned full-data statistic. Do not infer a UCI author error from this benchmark.
