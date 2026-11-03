"""Current-engine contract regressions using synthetic prediction vectors."""

import json
from pathlib import Path
import shutil

import pytest

from agent import engine, evidence
from sandbox import executor

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def case(tmp_path):
    path = tmp_path / "case"
    shutil.copytree(ROOT / "examples" / "secom", path, ignore=shutil.ignore_patterns("results.json"))
    return path


def fake_raw(case_dir, patches, seeds, **kw):
    y = [0, 1] * 20
    return {
        "status": "ok",
        "result": {
            "metric": "accuracy",
            "seeds": {str(s): {k: {"y": y, "p": y} for k in ("orig", "fix_A", "fix_B", "fix_both")} for s in seeds},
        },
    }


def test_no_hypothesis_is_not_tested_and_inputs_are_snapshotted(case, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "run_factorial", fake_raw)
    monkeypatch.setattr(engine, "_rule_plan", lambda src: None)
    out = tmp_path / "job"
    r = engine.run_audit(case, out, n_boot=10)
    assert r["verdict"] == "NOT_TESTED" and r["summary"] is None
    assert evidence.verify(out / "inputs", r)
    assert r["ledger"]["calls"] == 0


def test_roc_auc_reference_is_chance_rather_than_majority_accuracy(case, tmp_path, monkeypatch):
    def raw(*args, **kwargs):
        value = fake_raw(*args, **kwargs)
        value["result"]["metric"] = "roc_auc"
        return value

    monkeypatch.setattr(executor, "run_factorial", raw)
    monkeypatch.setattr(engine, "_rule_plan", lambda src: None)
    result = engine.run_audit(case, tmp_path / "job", n_boot=10)
    assert result["baseline"]["reference"] == 0.5
    assert result["input"]["positive_prevalence"] < 0.1


def test_model_no_flaw_does_not_mean_measured_clean(case, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "run_factorial", fake_raw)

    class FakeProvider:
        def complete(self, *a, **kw):
            return json.dumps({"verdict": "no_flaw", "factors": [], "reason": "No supported concern"})

        def ledger(self):
            return {"calls": 1, "est_usd": 0}

    r = engine.run_audit(case, tmp_path / "job", live=True, provider=FakeProvider(), n_boot=10)
    assert r["verdict"] == "MODEL_NO_FLAW" and r["summary"] is None


@pytest.mark.parametrize("answer,field,expected", [("needs_information", "questions", "NEEDS_INFORMATION"), ("unsupported", "scope_gaps", "UNSUPPORTED")])
def test_known_gaps_and_missing_information_are_explicit(case, tmp_path, monkeypatch, answer, field, expected):
    monkeypatch.setattr(executor, "run_factorial", fake_raw)
    plan = {"verdict": answer, "factors": [], "reason": "Cannot justify a test yet", field: ["Establish predictor availability at decision time"]}
    r = engine.run_audit(case, tmp_path / "job", plan=plan, n_boot=10)
    assert r["verdict"] == expected and r["summary"] is None
    assert r[field] == plan[field]
    assert not engine._check_plan({**plan, field: []}, case)["ok"]


@pytest.mark.parametrize("assessment,expected", [("needs_information", "NEEDS_INFORMATION"), ("unsupported", "UNSUPPORTED"), (None, "DISPUTED")])
def test_independent_concerns_survive_no_flaw_early_return(case, tmp_path, monkeypatch, assessment, expected):
    monkeypatch.setattr(executor, "run_factorial", fake_raw)

    class FakeProvider:
        def complete(self, *a, role="planner", **kw):
            if role == "critic":
                review = {"concerns": ["Predictor timing is unresolved"], "questions": ["When is it available?"], "reason": "The supplied timing is unresolved"}
                if assessment == "unsupported":
                    review["scope_gaps"] = ["Predictor timing cannot be resolved by the supported edits"]
                if assessment is not None:
                    review["assessment"] = assessment
                return json.dumps(review)
            return json.dumps({"verdict": "no_flaw", "factors": [], "reason": "No expressible edit"})

        def ledger(self):
            return {"calls": 2, "est_usd": 0}

    r = engine.run_audit(case, tmp_path / "job", live=True, critic=True, provider=FakeProvider(), n_boot=10)
    assert r["verdict"] == expected and r["summary"] is None
    assert r["unresolved_concerns"] == ["Predictor timing is unresolved"]


def test_input_mutation_invalidates_result(case, tmp_path, monkeypatch):
    def mutate(*a, **kw):
        raw = fake_raw(*a, **kw)
        with (case / "data.csv").open("a") as f:
            f.write("\n")
        return raw

    monkeypatch.setattr(executor, "run_factorial", mutate)
    monkeypatch.setattr(engine, "_rule_plan", lambda src: None)
    r = engine.run_audit(case, tmp_path / "job", n_boot=10)
    assert r["status"] == "failed" and r["verdict"] == "INCONCLUSIVE"
    assert "Inputs changed" in r["error"]


def test_preview_does_not_include_raw_rows(case):
    preview = engine.outbound_preview(case)
    assert "no raw rows" in preview["data"].lower()
    assert not {"source", "rows_data", "samples"} & preview.keys()


def test_cancel_before_baseline_is_terminal(case, tmp_path, monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("must not execute")

    monkeypatch.setattr(executor, "run_factorial", forbidden)
    r = engine.run_audit(case, tmp_path / "job", cancelled=lambda: True)
    assert r["status"] == "cancelled"


def test_declared_reference_must_reproduce_before_planning(case, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "run_factorial", fake_raw)
    config = json.loads((case / "case.json").read_text())
    config.update(expected_score=0.1, score_tolerance=0.01)
    (case / "case.json").write_text(json.dumps(config))
    monkeypatch.setattr(engine, "_rule_plan", lambda src: pytest.fail("must stop before planning"))
    r = engine.run_audit(case, tmp_path / "job", n_boot=10)
    assert r["status"] == "failed" and not r["baseline"]["reproduced"]
    assert "does not reproduce" in r["error"]


def test_cancellation_after_critic_prevents_planner(case, tmp_path, monkeypatch):
    monkeypatch.setattr(executor, "run_factorial", fake_raw)
    stop, roles = [], []

    class FakeProvider:
        def complete(self, *a, role="planner", **kw):
            roles.append(role)
            stop.append(True)
            return json.dumps({"concerns": [], "reason": "reviewed"})

        def ledger(self):
            return {"calls": len(roles), "est_usd": 0}

    r = engine.run_audit(
        case, tmp_path / "job", live=True, critic=True, provider=FakeProvider(), cancelled=lambda: bool(stop), n_boot=10
    )
    assert roles == ["critic"] and r["status"] == "cancelled"


def test_negative_effect_is_a_detected_improvement(case, tmp_path, monkeypatch):
    from agent import contract_g9

    def raw(*a, **kw):
        value = fake_raw(*a, **kw)
        for seed in value["result"]["seeds"].values():
            seed["orig"]["p"] = [0] * len(seed["orig"]["y"])
        return value

    monkeypatch.setattr(executor, "run_factorial", raw)
    monkeypatch.setattr(contract_g9, "check_plan", lambda *a, **kw: {"ok": True, "problems": []})
    r = engine.run_audit(case, tmp_path / "job", n_boot=40)
    assert r["summary"]["sign"] == "-" and r["verdict"] == "CONTROL_SCORE_HIGHER"


@pytest.mark.parametrize("kind", ["group", "temporal"])
def test_dependent_split_cannot_claim_calibrated_inflation(case, tmp_path, monkeypatch, kind):
    from agent import contract_g9, edit_dsl

    def raw(*a, **kw):
        value = fake_raw(*a, **kw)
        for seed in value["result"]["seeds"].values():
            seed["fix_both"]["p"] = [0] * len(seed["fix_both"]["y"])
        return value

    source = (case / "train.py").read_text()
    monkeypatch.setattr(executor, "run_factorial", raw)
    monkeypatch.setattr(contract_g9, "check_plan", lambda *a, **kw: {"ok": True, "problems": []})
    monkeypatch.setattr(edit_dsl, "compile_plan", lambda *a: None)
    monkeypatch.setattr(edit_dsl, "legacy_sources", lambda *a: dict.fromkeys(("fix_A", "fix_B", "fix_both"), source))
    plan = {"verdict": "flaw", "factors": [{"ops": [{"op": "replace_split", "kind": kind}]}]}
    r = engine.run_audit(case, tmp_path / "job", plan=plan, n_boot=40)
    assert r["summary"]["sign"] == "+"
    assert r["status"] == "completed" and r["verdict"] == "INCONCLUSIVE"
    assert any("dependence-aware inference" in text for text in r["limitations"])


def test_export_rejects_nested_source_and_patch_changes(tmp_path):
    import difflib

    path = tmp_path / "job"
    case = path / "inputs"
    case.mkdir(parents=True)
    original = "# original\n"
    control = "# tested control\n"
    for name, text in (("train.py", original), ("data.csv", "target\n0\n"), ("excerpt.md", "claim")):
        (case / name).write_text(text)
    sources = dict.fromkeys(("fix_A", "fix_B", "fix_both"), control)
    identity = evidence.capture(case, sources=sources)
    result = {
        "schema": engine.VERSION,
        "sources": sources,
        "evidence": identity,
        "record": {"sources": sources.copy(), "evidence": identity},
        "diff": "".join(
            difflib.unified_diff(
                original.splitlines(True),
                control.splitlines(True),
                fromfile="original/train.py",
                tofile="controlled/train.py",
            )
        ),
    }
    p = path / "result.json"
    p.write_text(json.dumps(result))
    assert engine.export_bundle(p).exists()
    result["record"]["sources"]["fix_both"] = "# untested\n"
    p.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Nested record"):
        engine.export_bundle(p)
    result["record"]["sources"] = sources.copy()
    result["diff"] += "tampering"
    p.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="Stored patch"):
        engine.export_bundle(p)


@pytest.mark.parametrize("reply", [{}, {"decision": "accept"}, {"decision": "maybe", "reason": "Unclear"}])
def test_invalid_final_critic_cannot_clear_a_measured_result(case, tmp_path, monkeypatch, reply):
    from agent import contract_g9

    monkeypatch.setattr(executor, "run_factorial", fake_raw)
    monkeypatch.setattr(contract_g9, "check_plan", lambda *a, **kw: {"ok": True, "problems": []})
    roles = []

    class Provider:
        def complete(self, *args, role="planner", **kwargs):
            roles.append(role)
            if role == "planner":
                return json.dumps(engine._rule_plan((case / "train.py").read_text()))
            return json.dumps({"concerns": [], "reason": "Reviewed independently"} if len(roles) == 1 else reply)

        def ledger(self):
            return {"calls": len(roles), "est_usd": 0}

    result = engine.run_audit(case, tmp_path / "job", live=True, critic=True, provider=Provider(), n_boot=10)
    assert roles == ["critic", "planner", "critic"]
    assert result["summary"] and result["verdict"] == "DISPUTED"
    assert "Reviewer" in result["error"]
