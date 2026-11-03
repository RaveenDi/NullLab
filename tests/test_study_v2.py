"""Study protocol gates, source enforcement and unmeasured export integrity."""

import json
import zipfile

import pytest

from agent import engine, evidence, intake, study
from sandbox import executor

CSV = "entity,time,sensor,post_test,target\r\n" + "".join(
    f"unit-{i % 4},2026-01-{i % 20 + 1:02d},{i / 40},{i % 2},{i % 2}\r\n" for i in range(40)
)
STUDY = {"decision_time": "Before final acceptance", "population": "independent_records",
         "entity_column": "entity", "time_column": "time", "excluded_columns": ["post_test"],
         "predictor_availability": "confirmed"}


def prepare(tmp_path, declaration=None):
    path = tmp_path / "case"
    intake.prepare(CSV, "target", "Predict an independent part's acceptance before its final test", path,
                   study=STUDY if declaration is None else declaration)
    return path


def raw(*args, seeds, **kwargs):
    y = [0, 1] * 20
    return {"status": "ok", "result": {"metric": "pr_auc", "seeds": {
        str(s): {name: {"y": y, "p": y} for name in ("orig", "fix_A", "fix_B", "fix_both")} for s in seeds}}}


def test_metadata_and_post_outcome_columns_stay_out_of_generated_features(tmp_path):
    case = prepare(tmp_path)
    info = engine.preflight(case)
    assert info["config"]["predictor_columns"] == ["sensor"]
    assert info["study_review"]["status"] == "ready"
    assert info["study_review"]["facts"]["predictor_count"] == 1
    assert (case / "data.csv").read_bytes() == CSV.encode()
    assert "agent/intake.py" in evidence.capture(case)["instruments"]


@pytest.mark.parametrize("before,after", [
    ("return PREDICTORS", 'return [c for c in df if c != TARGET]'),
    ("df[feats(df)]", 'df[["sensor", "post_test"]]'),
    ("N_TREES = 40", "N_TREES = 400"),
    ('TARGET = \'target\'', "TARGET = 'post_test'"),
])
def test_customized_generated_template_cannot_claim_role_enforcement(tmp_path, before, after):
    case = prepare(tmp_path)
    path = case / "train.py"
    assert before in path.read_text()
    path.write_text(path.read_text().replace(before, after))
    with pytest.raises(ValueError, match="Generated source"):
        engine.preflight(case)


def test_template_formatting_is_allowed_but_custom_adapter_is_explicit(tmp_path):
    case = prepare(tmp_path)
    source = case / "train.py"
    source.write_text("# Formatting is not behavior\n" + source.read_text())
    assert engine.preflight(case)["study_review"]["status"] == "ready"
    source.write_text(source.read_text().replace("return PREDICTORS", 'return [c for c in df if c != TARGET]'))
    cfg = json.loads((case / "case.json").read_text())
    cfg.update(adapter="custom", generated_pipeline=False)
    (case / "case.json").write_text(json.dumps(cfg))
    assert any("not been verified" in warning for warning in engine.preflight(case)["study_review"]["warnings"])


@pytest.mark.parametrize("changes,verdict", [
    ({"predictor_availability": "unknown"}, "NEEDS_INFORMATION"),
    ({"population": "undecided"}, "NEEDS_INFORMATION"),
    ({"decision_time": ""}, "NEEDS_INFORMATION"),
    ({"population": "unseen_entities"}, "UNSUPPORTED"),
    ({"population": "future_records"}, "UNSUPPORTED"),
])
def test_unresolved_or_unsupported_design_stops_before_fit_and_model(tmp_path, monkeypatch, changes, verdict):
    case = prepare(tmp_path, {**STUDY, **changes})

    def forbidden(*args, **kwargs):
        pytest.fail("Study gate must run before training or any model call")

    monkeypatch.setattr(executor, "run_factorial", forbidden)

    class ForbiddenProvider:
        complete = forbidden

        def ledger(self):
            return {"calls": 0, "est_usd": 0}

    result = engine.run_audit(case, tmp_path / "job", live=True, critic=True, provider=ForbiddenProvider())
    assert result["verdict"] == verdict and not result.get("baseline")
    assert result["review_room"]["participants"][-1]["status"] == "not_executed"
    assert evidence.verify(tmp_path / "job" / "inputs", result)
    with zipfile.ZipFile(engine.export_assessment(tmp_path / "job" / "result.json")) as archive:
        assert b"No counterfactual was measured" in archive.read("assessment.md")
        assert archive.read("inputs/data.csv") == CSV.encode()
        assert not any("control/" in name for name in archive.namelist())


def test_baseline_export_keeps_raw_seed_evidence_and_excludes_untracked_files(tmp_path, monkeypatch):
    case = prepare(tmp_path)
    monkeypatch.setattr(executor, "run_factorial", raw)
    result = engine.run_audit(case, tmp_path / "job", n_boot=10)
    assert result["verdict"] == "NOT_TESTED"
    assert set(result["baseline"]["per_seed_scores"]) == {"42", "43", "44"}
    assert set(result["baseline_raw"]["seeds"]) == {"42", "43", "44"}
    snap = tmp_path / "job" / "inputs"
    (snap / "private-untracked.txt").write_text("Never include an unbound file")
    path = tmp_path / "job" / "result.json"
    with zipfile.ZipFile(engine.export_assessment(path)) as archive:
        assert "inputs/private-untracked.txt" not in archive.namelist()
        assert b"baseline score" in archive.read("assessment.md")
    with pytest.raises(ValueError, match="Only measured"):
        engine.export_bundle(path)
    (snap / "case.json").write_text((snap / "case.json").read_text() + "\n")
    with pytest.raises(evidence.EvidenceError):
        engine.export_assessment(path)


@pytest.mark.parametrize("response", [{}, [], {"reason": "Reviewed"}, {"reason": "Reviewed", "concerns": "none"},
                                     {"reason": "Missing context", "concerns": [], "assessment": "needs_information"},
                                     {"reason": "Different protocol needed", "concerns": [], "assessment": "unsupported", "scope_gaps": []},
                                     {"reason": "Missing context", "concerns": [], "assessment": "needs_information", "questions": [" "]}])
def test_malformed_independent_assessment_fails_closed(tmp_path, monkeypatch, response):
    case = prepare(tmp_path)
    monkeypatch.setattr(executor, "run_factorial", raw)
    roles = []

    class Provider:
        def complete(self, *args, role="planner", **kwargs):
            roles.append(role)
            return json.dumps(response)

        def ledger(self):
            return {"calls": len(roles), "est_usd": 0}

    result = engine.run_audit(case, tmp_path / "job", live=True, critic=True, provider=Provider(), n_boot=10)
    assert result["status"] == "failed" and result["verdict"] == "INCONCLUSIVE"
    assert roles == ["critic"] and not result.get("plan")
    assert "Reviewer" in result["error"]
    assert engine.export_assessment(tmp_path / "job" / "result.json").is_file()


@pytest.mark.parametrize("changes", [{"entity_column": "target"}, {"time_column": "missing"}, {"unexpected": "field"},
                                     {"excluded_columns": ["sensor", "entity", "time", "post_test"]}])
def test_bad_roles_rejected_without_visible_partial_case(tmp_path, changes):
    with pytest.raises(ValueError):
        prepare(tmp_path, {**STUDY, **changes})
    assert not (tmp_path / "case").exists()


def test_represented_entities_remain_descriptive_and_exact_target_match_is_warning():
    value = study.normalize({**STUDY, "population": "represented_entities"}, ["sensor", "entity", "time", "post_test", "target"], "target")
    review = study.review(value, generated=True, predictor_columns=["sensor"], facts={"target_matching_columns": ["sensor"]})
    assert review["status"] == "ready" and review["inference_scope"] == "descriptive_only"
    assert any("not a leakage finding" in warning for warning in review["warnings"])
