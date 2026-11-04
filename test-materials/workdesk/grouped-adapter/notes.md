# Synthetic repeated-rig study

This is simulated data for an internal researcher-style product session, not real industrial measurements.

The study contains 24 hypothetical sensor rigs, with eight readings per rig. device_id identifies the same rig across rows and is metadata, not an intended model predictor. The four numeric measurements are available before inspection. event is the binary inspection outcome.

Our intended use is to predict outcomes for rigs never represented during training. The supplied Decision Tree pipeline currently reports accuracy from three-fold shuffled stratified random-row validation. I want to understand what this evaluation establishes, what remains uncertain and which validation design would answer the intended question. Please preserve my model while examining the evaluation protocol.
