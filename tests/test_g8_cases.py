"""G8 EHG case tests: hygiene of the disguised agent view, truth outside case folders, leaky/clean differ minimally,
reference direction. Offline; the reference test needs the git-ignored data.csv and skips otherwise."""
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
REAL = ROOT / "real"
DIS = [REAL / "ehg_disguised", REAL / "ehg_disguised_clean"]
NAMED = [REAL / "ehg_apparent", REAL / "ehg_clean"]
FORBIDDEN = ("smote", "preterm", "premature", "ehg", "electrohyster", "pregnan", "birth", "uterin", "gestation", "physionet", "tpehg",
             "vandewiele", "arxiv", "clinical", "medical", "rms", "fmed", "fpeak", "sampen", "0.49", "0.494")


def _text(case):
    return ((case / "train.py").read_text(encoding="utf-8") + (case / "excerpt.md").read_text(encoding="utf-8")).lower()


@pytest.mark.parametrize("case", DIS, ids=lambda p: p.name)
def test_disguised_view_has_no_fingerprints(case):
    t = _text(case)
    for w in FORBIDDEN:
        assert w not in t, f"{w!r} leaks into {case.name}"
    assert 'TARGET = "target"' in (case / "train.py").read_text(encoding="utf-8")


def test_truth_outside_case_folders_and_folders_hold_only_agent_files():
    truth = json.loads((ROOT / "eval" / "g8_truth.json").read_text(encoding="utf-8"))
    assert truth["ehg_disguised"]["leaky"] is True and truth["ehg_disguised_clean"]["leaky"] is False
    assert truth["ehg_apparent"]["leaky"] is True and truth["ehg_clean"]["leaky"] is False
    assert 0.3 < truth["ehg_disguised"]["published_inflation_roc_auc"] < 0.6
    for case in DIS + NAMED:
        files = sorted(p.name for p in case.iterdir() if p.is_file())
        ok = (["data.csv", "excerpt.md", "train.py"], ["excerpt.md", "train.py"])
        if case in NAMED:  # only the named (non-disguised) folders carry the no-medical-advice README
            ok += (["README.md", "data.csv", "excerpt.md", "train.py"], ["README.md", "excerpt.md", "train.py"])
        assert files in ok
        assert "published" not in (case / "train.py").read_text(encoding="utf-8").lower()


@pytest.mark.parametrize("pair", [NAMED, DIS], ids=["named", "disguised"])
def test_leaky_and_clean_differ_only_in_where_oversampling_happens(pair):
    a = (pair[0] / "train.py").read_text(encoding="utf-8").splitlines()
    b = (pair[1] / "train.py").read_text(encoding="utf-8").splitlines()
    sa, sb = set(a), set(b)
    assert (sa ^ sb) == {"    X, y = oversample(X, y, seed)", "    return X_tr, y_tr", "    return oversample(X_tr, y_tr, seed)"}
    assert (pair[0] / "excerpt.md").read_text() == (pair[1] / "excerpt.md").read_text()


@pytest.mark.skipif(not (DIS[0] / "data.csv").exists(), reason="data.csv is git-ignored; rebuild with eval/build_g8_cases.py")
def test_disguised_data_is_a_power_of_two_relabelling_of_the_named_data():
    truth = json.loads((ROOT / "eval" / "g8_truth.json").read_text(encoding="utf-8"))["ehg_disguised"]
    named, dis = pd.read_csv(NAMED[0] / "data.csv"), pd.read_csv(DIS[0] / "data.csv")
    assert dis.shape == (300, 13) and int(dis["target"].sum()) == 38
    for old, new in truth["column_map_original_to_disguised"].items():
        if old == "premature":
            assert (named[old] == dis[new]).all()
        else:
            np.testing.assert_array_equal(named[old].to_numpy() * 2.0 ** truth["pow2_exponent"][new], dis[new].to_numpy())


@pytest.mark.skipif(not (DIS[0] / "data.csv").exists(), reason="data.csv is git-ignored")
def test_reference_reproduces_published_direction():
    ref = json.loads((ROOT / "runs_g8_cases" / "reference.json").read_text(encoding="utf-8"))
    assert ref["inflation_named_mean"] > 0.25 and ref["inflation_disguised_mean"] > 0.25
    assert min(ref["inflation_named"]) > 0.2
    assert abs(ref["mean"]["ehg_clean"] - 0.5) < 0.12 and max(abs(a - b) for a, b in zip(ref["inflation_named"], ref["inflation_disguised"])) < 0.01
