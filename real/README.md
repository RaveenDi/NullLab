# real/ (documented real and textbook cases)

The raw data files are not stored in this repository.

- **civilwar_* (REAL-PINNED)**: Muchlinski et al. 2016 civil-war onset data. Download `SambnisImp.csv` from the Harvard Dataverse (doi:10.7910/DVN/KRKWK8), then run `python eval/build_g6.py path/to/SambnisImp.csv`; the script verifies the published md5 before writing anything.
- **esl_selection* (TEXTBOOK)**: generated random data for the feature-screening-before-cross-validation example (Hastie, Tibshirani, Friedman, Elements of Statistical Learning section 7.10.2); `python eval/build_g6.py` regenerates it deterministically.

Each case folder keeps `train.py` and `excerpt.md`. The tests that need the raw data skip when it is absent.
