"""Research workspace API contracts; no browser, hosted model or external calls."""

import copy
import hashlib
import io
import json
import shutil
import time
import uuid
import zipfile

from fastapi.testclient import TestClient
import pytest

from agent import engine, evidence, intake
from app import server


STUDY = {
    "title": "Independent inspection study",
    "decision_time": "Before inspection outcome is known",
    "unit_of_analysis": "One independent part",
    "population": "independent_records",
    "entity_column": "entity",
    "time_column": "time",
    "excluded_columns": ["withheld"],
    "predictor_availability": "confirmed",
}
CSV = "entity,time,x,withheld,target\r\n" + "".join(
    f"line-{i % 4},2026-01-{i % 20 + 1:02d},{i},{i % 2},{i % 2}\r\n" for i in range(40)
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "JOBS_ROOT", tmp_path / "out" / "jobs")
    monkeypatch.setattr(server, "_ACTIVE", set())
    monkeypatch.delenv("NULLLAB_ALLOW_WEB_LIVE", raising=False)
    return tmp_path


def generated(workspace, name="user-fixture"):
    path = workspace / "examples" / name
    intake.prepare(CSV, "target", "Retrospective screening of independent parts", path, study=STUDY)
    return path


def stored_job(case, *, result_from=None, context=None):
    job_id = str(uuid.uuid4())
    directory = server.JOBS_ROOT / job_id
    shutil.copytree(case, directory / "inputs")
    job = {
        "id": job_id, "case": case.name, "status": "completed", "live": False, "critic": False,
        "created_at": "2026-11-03T10:00:00+00:00", "updated_at": "2026-11-03T10:00:01+00:00",
        "cancel_requested": False,
    }
    if result_from is None:
        sources = dict.fromkeys(("fix_A", "fix_B", "fix_both"), "# PRIVATE_CODE_SENTINEL\n")
        result = {
            "schema": engine.VERSION, "case": case.name, "status": "completed", "verdict": "NO_EFFECT_DETECTED",
            "mode": "rules", "events": [], "limitations": ["Synthetic API fixture; no scientific inference"],
            "baseline": {"metric": "accuracy", "score": 0.7},
            "summary": {"metric": "accuracy", "controlled": 0.7, "seeds": ["42", "43", "44"]},
            "sources": sources, "raw": {"private": "RAW_DATA_SENTINEL"},
            "evidence": evidence.capture(directory / "inputs", sources=sources, context=context or {"seeds": [42, 43, 44]}),
            "ledger": {"calls": 0, "est_usd": 0},
        }
        result["record"] = {"status": "ok", "sources": copy.deepcopy(sources), "evidence": copy.deepcopy(result["evidence"])}
    else:
        result = copy.deepcopy(result_from)
    result["job_id"] = job_id
    server._write(directory / "job.json", job)
    server._write(directory / "result.json", result)
    return job_id, result


def test_revision_preserves_csv_and_old_case_and_records_lineage(workspace):
    with TestClient(server.app) as client:
        imported = client.post("/api/intake", json={"csv": CSV, "target": "target", "intended_use": "Retrospective independent parts", "study": {**STUDY, "predictor_availability": "unknown"}})
        assert imported.status_code == 201, imported.text
        case_id = imported.json()["case"]
        path = workspace / "examples" / case_id
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}
        assert (path / "data.csv").read_bytes() == CSV.encode("utf-8")
        detail = client.get("/api/cases/" + case_id).json()
        assert detail["predictors"] == ["x"]
        assert detail["study_review"]["status"] == "needs_information"
        assert detail["study_review"]["facts"]["rows"] == 40
        assert detail["profile_source"] == "saved_intake_diagnostics"
        parent_id, _ = stored_job(path)
        revised = client.post(f"/api/cases/{case_id}/revisions", json={"study": {**STUDY, "title": "Clarified study"}, "intended_use": "Predict before outcome using available inspection features", "parent_job_id": parent_id, "reason": "Confirmed predictor timing; this is an author declaration"})
        assert revised.status_code == 201, revised.text
        new_id = revised.json()["case"]
        assert new_id != case_id
        new_path = workspace / "examples" / new_id
        assert (new_path / "data.csv").read_bytes() == (path / "data.csv").read_bytes()
        assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}
        lineage = json.loads((new_path / "case.json").read_text())["lineage"]
        assert lineage["root_case"] == case_id and lineage["parent_case"] == case_id and lineage["parent_job"] == parent_id
        assert lineage["parent_inputs"] == evidence.input_hashes(path)
        assert lineage["parent_manifest_sha256"]
        assert client.get("/api/cases/" + new_id).json()["title"] == "Clarified study"


def test_changed_generated_source_and_mismatched_parent_cannot_be_silently_revised(workspace):
    case = generated(workspace)
    parent, _ = stored_job(case)
    request = {"study": STUDY, "intended_use": "Independent retrospective records", "parent_job_id": parent}
    source = (case / "train.py").read_text()
    with TestClient(server.app) as client:
        (case / "train.py").write_text(source.replace("return PREDICTORS", 'return [c for c in df if c != TARGET]'))
        assert client.post(f"/api/cases/{case.name}/revisions", json=request).status_code == 409
        (case / "train.py").write_text(source)
        (case / "data.csv").write_bytes(CSV.encode() + b"\r\n")
        assert client.post(f"/api/cases/{case.name}/revisions", json=request).status_code == 409
        detail = client.get("/api/cases/" + case.name).json()
        assert detail["profile_source"] == "not_available" and not detail["study_review"]["facts"]


def test_revision_rejects_unrelated_parent_and_external_code(workspace):
    case = generated(workspace)
    other = generated(workspace, "user-other")
    unrelated, _ = stored_job(other)
    request = {"study": STUDY, "intended_use": "Retrospective independent records", "parent_job_id": unrelated}
    with TestClient(server.app) as client:
        assert client.post(f"/api/cases/{case.name}/revisions", json=request).status_code == 400
        config = json.loads((case / "case.json").read_text())
        config["adapter"] = "unknown-custom-generator"
        server._write(case / "case.json", config)
        request.pop("parent_job_id")
        assert client.post(f"/api/cases/{case.name}/revisions", json=request).status_code == 409


def test_history_recovers_persisted_jobs_without_raw_evidence(workspace):
    case = generated(workspace)
    job_id, result = stored_job(case)
    with TestClient(server.app) as client:
        listed = client.get("/api/jobs?limit=1")
        assert listed.status_code == 200
        row = listed.json()["jobs"][0]
        assert row["id"] == job_id and row["metric"] == "accuracy" and row["baseline_score"] == 0.7
        assert "PRIVATE_CODE_SENTINEL" not in listed.text and "RAW_DATA_SENTINEL" not in listed.text
        assert row["evidence"]["inputs"] == result["evidence"]["inputs"]
        assert client.get("/api/jobs?case=unrelated").json()["jobs"] == []
        assert client.get("/api/jobs?limit=101").status_code == 422
    with TestClient(server.app) as reloaded:
        assert reloaded.get("/api/jobs").json()["jobs"][0]["id"] == job_id
        assert reloaded.get("/api/jobs/" + job_id).json()["result"]["job_id"] == job_id


def test_comparison_checks_contracts_and_snapshot_identity(workspace):
    case = generated(workspace)
    left, result = stored_job(case)
    right, _ = stored_job(case, result_from=result)
    with TestClient(server.app) as client:
        response = client.get(f"/api/jobs/compare?left={left}&right={right}")
        assert response.status_code == 200, response.text
        assert response.json()["comparable"] is True
        assert "metadata alignment only" in response.json()["interpretation"]
        path = server.JOBS_ROOT / right
        changed = json.loads((path / "result.json").read_text())
        changed["record"]["sources"]["fix_both"] = "# not the verified control\n"
        server._write(path / "result.json", changed)
        assert client.get(f"/api/jobs/compare?left={left}&right={right}").json()["comparable"] is False
        changed["record"]["sources"] = copy.deepcopy(changed["sources"])
        server._write(path / "result.json", changed)
        (path / "inputs" / "case.json").write_text((path / "inputs" / "case.json").read_text() + "\n")
        # A changed snapshot cannot borrow the old identity, even when both
        # stored manifests still look equal to the comparison table.
        mismatch = client.get(f"/api/jobs/compare?left={left}&right={right}").json()
        assert mismatch["comparable"] is False
        assert any("identity" in reason for reason in mismatch["reasons"])
        changed["evidence"] = evidence.capture(path / "inputs", sources=changed["sources"], context=changed["evidence"]["context"])
        changed["record"]["evidence"] = copy.deepcopy(changed["evidence"])
        server._write(path / "result.json", changed)
        difference = client.get(f"/api/jobs/compare?left={left}&right={right}").json()
        assert difference["comparable"] is False
        assert any(row["field"] == "inputs" for row in difference["differences"])
        assert client.get(f"/api/jobs/compare?left={left}&right={left}").status_code == 400


def test_baseline_assessment_is_separate_from_measured_bundle(workspace, monkeypatch):
    case = generated(workspace)
    job_id, result = stored_job(case)
    directory = server.JOBS_ROOT / job_id
    result.update(verdict="NOT_TESTED", summary=None, sources={})
    result.pop("record")
    result["evidence"] = evidence.capture(directory / "inputs")
    server._write(directory / "result.json", result)

    def memo(result_path):
        record = json.loads(result_path.read_text())
        evidence.verify(result_path.parent / "inputs", record)
        target = result_path.parent / "assessment.zip"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("assessment.md", "# Assessment\nNOT_TESTED: no counterfactual was measured.\n")
        return target

    monkeypatch.setattr(engine, "export_assessment", memo, raising=False)
    with TestClient(server.app) as client:
        bundle = client.get(f"/api/jobs/{job_id}/bundle")
        assert bundle.status_code == 409 and "No controlled experiment was measured" in bundle.text
        assessment = client.get(f"/api/jobs/{job_id}/assessment")
        assert assessment.status_code == 200
        with zipfile.ZipFile(io.BytesIO(assessment.content)) as archive:
            assert b"NOT_TESTED" in archive.read("assessment.md")
        assert "application/zip" in assessment.headers["content-type"]


def test_unknown_study_exports_real_assessment_without_fitting(workspace, monkeypatch):
    from sandbox import executor

    def forbidden(*args, **kwargs):
        raise AssertionError("An unresolved study must not fit a baseline")

    monkeypatch.setattr(executor, "run_factorial", forbidden)
    csv_text = "x,target\r\n" + "".join(f"{i},{i % 2}\r\n" for i in range(40))
    with TestClient(server.app) as client:
        imported = client.post("/api/intake", json={"csv": csv_text, "target": "target", "intended_use": "Inspection screening", "study": {"title": "Unresolved study"}})
        assert imported.status_code == 201
        case_id = imported.json()["case"]
        job = client.post("/api/jobs", json={"case": case_id}).json()
        for _ in range(100):
            state = client.get("/api/jobs/" + job["id"]).json()
            if state["status"] in server._TERMINAL:
                break
            time.sleep(0.02)
        assert state["result"]["verdict"] == "NEEDS_INFORMATION"
        assert not state["result"].get("baseline") and state["result"]["ledger"]["calls"] == 0
        assessment = client.get(f"/api/jobs/{job['id']}/assessment")
        assert assessment.status_code == 200, assessment.text
        with zipfile.ZipFile(io.BytesIO(assessment.content)) as archive:
            assert b"NEEDS_INFORMATION" in archive.read("assessment.md")
            assert archive.read("inputs/data.csv") == csv_text.encode("utf-8")
        assert client.get("/api/jobs").json()["jobs"][0]["id"] == job["id"]


def test_queued_audit_can_be_recovered_without_starting_another(workspace, monkeypatch):
    case = generated(workspace)

    class HeldQueue:
        def submit(self, *args):
            return None

    monkeypatch.setattr(server, "_POOL", HeldQueue())
    with TestClient(server.app) as client:
        job = client.post("/api/jobs", json={"case": case.name}).json()
        listed = client.get("/api/jobs").json()
        assert listed["active_job_ids"] == [job["id"]]
        assert listed["jobs"][0]["status"] == "queued"
        assert client.get("/api/jobs/" + job["id"]).json()["id"] == job["id"]
        assert client.post(f"/api/jobs/{job['id']}/cancel").json()["cancel_requested"]


def test_interrupted_checkpoint_cannot_be_reported_as_final_measured_evidence(workspace):
    case = generated(workspace)
    left, result = stored_job(case)
    right, _ = stored_job(case, result_from=result)
    path = server.JOBS_ROOT / right
    job = json.loads((path / "job.json").read_text())
    job.update(status="failed", error="Local server restarted before this audit finished.")
    server._write(path / "job.json", job)
    with TestClient(server.app) as client:
        row = next(item for item in client.get("/api/jobs").json()["jobs"] if item["id"] == right)
        assert row["checkpoint_only"] and row["verdict"] == "INCONCLUSIVE"
        assert not row["measured"] and row["controlled_score"] is None
        comparison = client.get(f"/api/jobs/compare?left={left}&right={right}").json()
        assert not comparison["comparable"]
        assert any("unfinished checkpoint" in reason for reason in comparison["reasons"])
        assert client.get(f"/api/jobs/{right}/bundle").status_code == 409
