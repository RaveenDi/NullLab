# Synthetic repeated-rig study

This is simulated data for an internal researcher-style product session, not real industrial measurements.

The study contains 24 hypothetical sensor rigs, with eight readings per rig. device_id identifies the same rig across rows and is metadata, not an intended model predictor. The four numeric measurements are available before inspection. event is the binary inspection outcome.

Our intended use is to predict outcomes for rigs never represented during training. The supplied Decision Tree pipeline currently reports accuracy from three-fold shuffled stratified random-row validation. I want to understand what this evaluation establishes, what remains uncertain and which validation design would answer the intended question. Please preserve my model while examining the evaluation protocol.


## Explicit new input revision

The device_id metadata strings have been replaced by a reviewed one-to-one integer mapping (mapping.json), solely for the frozen runtime guard's numeric identity representation. Original rows, row order, target, predictor values, adapter bytes, Decision Tree and random-row validation are unchanged. Original string IDs and the failed guard check remain retained. This is a known synthetic engineering recovery, not new scientific evidence.
