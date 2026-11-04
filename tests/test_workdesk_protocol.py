"""Pre-spend AST applicability and known synthetic adapter recovery checks.

These engineering checks do not rerun or rescore the original researcher audit.
"""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import runpy

import numpy as np
import pytest

from agent import edit_dsl, workdesk_protocol


FIXTURE = Path(__file__).resolve().parents[1] / "test-materials/workdesk/grouped-adapter"
ORIGINAL = (FIXTURE / "original_pipeline.py").read_text(encoding="utf-8")
ADAPTED = (FIXTURE / "train.py").read_text(encoding="utf-8")
BRIEF = {
    "target": "event",
    "study": {
        "population": "unseen_entities", "entity_column": "device_id", "time_column": "",
        "decision_time": "Before inspection", "excluded_columns": ["device_id"],
    },
}


def check(source=ADAPTED, csv_text=None, **study):
    return workdesk_protocol.check(source, {**BRIEF, "study": {**BRIEF["study"], **study}}, csv_text=csv_text)


def test_original_cv_is_blocked_before_execution_or_model_dispatch():
    result = check(ORIGINAL)
    assert result["status"] == "blocked" and not result["candidates"]
    assert any("groups" in item["reason"] for item in result["rejected"])
    assert "No baseline or model call has started" in result["messages"][0]
    assert "new material version" in result["messages"][1]


def test_canonical_explicit_group_adapter_is_only_ast_applicable():
    result = check()
    assert result["status"] == "applicable"
    assert result["candidates"] == [{"op": "replace_split", "step": "cv_eval", "kind": "group", "col": "device_id"}]
    assert result["protocol"]["source_sha256"] == hashlib.sha256(ADAPTED.encode()).hexdigest()
    assert result["protocol"]["seeds"] == [42, 43, 44]
    assert "Runtime provenance" in result["note"] and "remain unverified" in result["note"]
    assert "may choose" in result["protocol"]["selection"]
    assert "descriptive" in result["protocol"]["inference"]


def test_unused_group_helper_does_not_make_original_pipeline_applicable():
    helper = ast.unparse(edit_dsl.defs_of(ast.parse(ADAPTED))["cv_eval"])
    result = check(ORIGINAL + "\n\n" + helper)
    assert result["status"] == "blocked" and not result["candidates"]


def test_adding_optional_groups_to_entry_point_does_not_supply_a_vector():
    result = check(ORIGINAL.replace("def claimed_eval(df, seed):", "def claimed_eval(df, seed, groups=None):"))
    assert result["status"] == "blocked" and not result["candidates"]
    assert any("groups=None is insufficient" in item["reason"] for item in result["rejected"])


@pytest.mark.parametrize("change", [
    lambda source: source.replace("df['device_id'].to_numpy()", "None"),
    lambda source: source.replace("df['device_id'].to_numpy()", "df['wrong_column'].to_numpy()"),
    lambda source: source.replace("def cv_eval(X, y, seed, groups):", "def cv_eval(X, y, seed, groups):\n    groups = None"),
    lambda source: source + "\ndef unrelated_call(df):\n    return cv_eval(None, None, 42, None)\n",
])
def test_unverified_group_bindings_are_conservatively_blocked(change):
    result = check(change(ADAPTED))
    assert result["status"] == "blocked" and not result["candidates"]


@pytest.mark.parametrize("argument", ["groups=df['device_id'].to_numpy()", "df['device_id'].values", "df['device_id']"])
def test_direct_positional_and_keyword_vectors_are_recognized(argument):
    result = check(ADAPTED.replace("df['device_id'].to_numpy()", argument))
    assert result["status"] == "applicable"


def test_temporal_cv_does_not_claim_to_sort_time():
    result = check(population="future_records", time_column="time")
    assert result["status"] == "blocked"
    assert any("does not sort" in item["reason"] for item in result["rejected"])


def test_nonnumeric_time_recovery_requires_chronological_conversion_not_arbitrary_ids():
    result = workdesk_protocol.check(ADAPTED, {**BRIEF, "study": {**BRIEF["study"], "population": "future_records", "time_column": "device_id", "entity_column": ""}}, csv_text=(FIXTURE / "data.csv").read_text())
    assert result["status"] == "blocked"
    assert any("chronological order and timezone" in message for message in result["messages"])
    assert not any("For categorical entity IDs" in message for message in result["messages"])


def test_temporal_df_holdout_template_is_an_unmeasured_candidate():
    source = '''import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
TARGET = "event"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return ["sensor"]
def split_rows(df, seed):
    return train_test_split(np.arange(len(df)), test_size=0.25, random_state=seed)
def claimed_eval(df, seed):
    tr, te = split_rows(df, seed)
    return df[TARGET].to_numpy()[te], np.zeros(len(te))
'''
    result = check(source, population="future_records", time_column="time")
    assert result["status"] == "applicable"
    assert result["candidates"] == [{"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "time"}]
    assert "remain unverified" in result["note"]


def test_independent_population_does_not_assert_group_validation():
    result = check(population="independent_records", entity_column="")
    assert result["status"] == "not_required" and not result["candidates"]
    assert result["required_kind"] is None
    steps = workdesk_protocol.steps(result["protocol"], "custom")
    assert len(steps) == 6 and "does not promise a measured control" in steps[2]


def test_preflight_never_imports_uploaded_python_or_mutates_source(tmp_path):
    sentinel = tmp_path / "EXECUTED"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('bad')\n" + ADAPTED
    digest = hashlib.sha256(source.encode()).hexdigest()
    result = check(source)
    assert result["status"] == "applicable" and not sentinel.exists()
    assert hashlib.sha256(source.encode()).hexdigest() == digest == result["protocol"]["source_sha256"]


def test_known_adapter_preserves_original_baseline_vectors_on_every_seed():
    # Both files are explicitly trusted, checked-in synthetic fixtures. No model
    # provider is called, and no historical engine audit/result is modified.
    original = runpy.run_path(str(FIXTURE / "original_pipeline.py"))
    adapted = runpy.run_path(str(FIXTURE / "train.py"))
    frame = original["load"](FIXTURE / "data.csv")
    assert original["feats"](frame) == adapted["feats"](frame)
    assert len(frame) == 192 and frame["device_id"].nunique() == 24
    for seed in (42, 43, 44):
        original_y, original_p = original["claimed_eval"](frame, seed)
        adapted_y, adapted_p = adapted["claimed_eval"](frame, seed)
        np.testing.assert_array_equal(original_y, adapted_y)
        np.testing.assert_array_equal(original_p, adapted_p)
    original_models = [ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(ORIGINAL))
                       if isinstance(n, ast.Call) and edit_dsl.fname(n) == "DecisionTreeClassifier"]
    adapted_models = [ast.dump(n, include_attributes=False) for n in ast.walk(ast.parse(ADAPTED))
                      if isinstance(n, ast.Call) and edit_dsl.fname(n) == "DecisionTreeClassifier"]
    assert original_models == adapted_models


def test_fixture_hashes_and_compiled_group_vector_are_bound():
    provenance = json.loads((FIXTURE / "PROVENANCE.json").read_text(encoding="utf-8"))
    for name, expected in provenance["files"].items():
        assert hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest() == expected
    compiled = edit_dsl.compile_ops(ADAPTED, check()["candidates"])
    assert "_G9GKF(n_splits=3)" in compiled and "groups=groups" in compiled


def test_original_string_metadata_is_blocked_before_guard_or_spend():
    result = check(csv_text=(FIXTURE / "data.csv").read_text())
    assert result["status"] == "blocked" and not result["candidates"]
    assert result["ast_candidates"]
    assert result["column_diagnostics"]["nonnumeric_values"] == 192
    assert any("NEW input revision" in message for message in result["messages"])


@pytest.mark.parametrize(("values", "diagnostic"), [
    (["0", "1", ""], "missing_values"),
    (["0", "1", "inf"], "nonfinite_values"),
    (["0", "1", "rig-2"], "nonnumeric_values"),
    (["0", "1", str(2**53 + 1)], "unsafe_precision"),
    (["0", "1", str(-(2**53 + 1))], "unsafe_precision"),
])
def test_incomplete_nonfinite_or_unsafe_metadata_is_blocked(values, diagnostic):
    csv = "device_id,event\n" + "\n".join(f"{value},0" for value in values) + "\n"
    result = check(csv_text=csv)
    assert result["status"] == "blocked"
    assert result["column_diagnostics"][diagnostic]


def test_group_count_must_support_literal_cv_folds():
    result = check(csv_text="device_id,event\n0,0\n1,1\n0,0\n1,1\n")
    assert result["status"] == "blocked"
    assert result["column_diagnostics"]["required_distinct"] == 3
    assert result["column_diagnostics"]["numeric_unique_values"] == 2


def test_missing_metadata_column_is_blocked():
    result = check(csv_text="sensor,event\n1,0\n2,1\n3,0\n")
    assert result["status"] == "blocked"
    assert "absent" in result["column_diagnostics"]["issues"][0]


def test_sufficient_numeric_metadata_passes_only_early_data_check():
    result = check(csv_text="device_id,event\n0,0\n1,1\n2,0\n0,1\n")
    assert result["status"] == "applicable"
    assert result["column_diagnostics"]["status"] == "compatible"
    assert "Runtime provenance" in result["note"]


def test_explicit_numeric_revision_preserves_all_baseline_vectors_and_identities():
    import pandas as pd

    numeric = FIXTURE / "numeric-metadata"
    original = runpy.run_path(str(FIXTURE / "original_pipeline.py"))
    adapted = runpy.run_path(str(numeric / "train.py"))
    original_frame = original["load"](FIXTURE / "data.csv")
    numeric_frame = adapted["load"](numeric / "data.csv")
    mapping = json.loads((numeric / "mapping.json").read_text())["mapping"]
    assert len(mapping) == len(set(mapping.values())) == 24
    np.testing.assert_array_equal(original_frame["device_id"].map(mapping), numeric_frame["device_id"])
    pd.testing.assert_frame_equal(original_frame.drop(columns="device_id"), numeric_frame.drop(columns="device_id"))
    assert (numeric / "train.py").read_bytes() == (FIXTURE / "train.py").read_bytes()
    for seed in (42, 43, 44):
        expected = original["claimed_eval"](original_frame, seed)
        actual = adapted["claimed_eval"](numeric_frame, seed)
        np.testing.assert_array_equal(expected[0], actual[0])
        np.testing.assert_array_equal(expected[1], actual[1])
    result = check(csv_text=(numeric / "data.csv").read_text())
    assert result["status"] == "applicable"
    assert result["column_diagnostics"]["numeric_unique_values"] == 24
