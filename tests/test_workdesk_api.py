"""Researcher-owned workdesk acceptance and failure checks; no live inference."""
from __future__ import annotations

import json
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from agent import engine, workdesk
from app import server
from app.workdesk_api import create_router

CSV = "sensor,event\n" + "\n".join(f"{i / 100},{i % 2}" for i in range(60)) + "\n"
STUDY = {"title": "Own study", "decision_time": "Before the outcome", "population": "independent_records", "predictor_availability": "confirmed", "unit_of_analysis": "One component"}
CUSTOM = '''import pandas as pd
TARGET = "event"
METRIC = "accuracy"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return ["sensor"]
def claimed_eval(df, seed):
    y = df[TARGET].to_numpy()
    return y, y
'''


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WORKSPACE", tmp_path)
    monkeypatch.setattr(server, "JOBS_ROOT", tmp_path / "out/jobs")
    monkeypatch.setattr(server, "_ACTIVE", set())
    monkeypatch.delenv("NULLLAB_ALLOW_WEB_LIVE", raising=False)
    app = FastAPI(lifespan=server.lifespan)
    app.include_router(create_router(server))
    with TestClient(app) as connection:
        yield connection


def create(client):
    response = client.post("/api/investigations", json={"question": "Does my protocol support its evaluation claim?"})
    assert response.status_code == 201, response.text
    return response.json()


def attach(client, pid, filename="measurements.csv", content=CSV):
    response = client.post(f"/api/investigations/{pid}/materials", json={"filename": filename, "content": content})
    assert response.status_code == 201, response.text
    return response.json()


def save(client, pid, **fields):
    body = {"target": "event", "intended_use": "Screen independent components before the outcome", "study": STUDY, **fields}
    response = client.post(f"/api/investigations/{pid}/brief", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def plan(client, pid):
    response = client.post(f"/api/investigations/{pid}/plan", json={})
    assert response.status_code == 200, response.text
    return response.json()


def test_question_only_project_persists_without_case_or_job_or_model(client, tmp_path):
    project = create(client)
    assert project["materials"] == [] and project["runs"] == [] and project["brief"] is None
    assert project["dashboard"]["readiness"] == "needs_materials"
    assert client.get("/api/investigations/" + project["id"]).json()["question"] == project["question"]
    assert client.get("/api/investigations").json()["investigations"][0]["id"] == project["id"]
    assert not list((tmp_path / "out/jobs").glob("*/job.json"))
    assert not (tmp_path / "examples").exists()
    assert workdesk.WorkdeskStore(tmp_path).get(project["id"])["question"] == project["question"]


def test_own_csv_profile_missing_info_then_new_brief_and_snapshot(client, tmp_path):
    pid = create(client)["id"]
    project = attach(client, pid)
    material = project["materials"][0]
    assert material["profile"]["rows"] == 60 and material["profile"]["target_candidates"] == ["event"]
    unknown = save(client, pid, study={**STUDY, "predictor_availability": "unknown"})
    first_id = unknown["brief"]["id"]
    blocked = plan(client, pid)
    assert blocked["plan"]["status"] == "needs_information" and blocked["plan"]["case"] is None
    assert client.post(f"/api/investigations/{pid}/runs", json={}).status_code == 400
    updated = save(client, pid)
    assert updated["brief"]["id"] != first_id and updated["brief"]["parent_revision_id"] == first_id
    planned = plan(client, pid)
    assert planned["plan"]["status"] == "ready"
    case = server.cases()[planned["plan"]["case"]]
    assert (case / "data.csv").read_bytes() == CSV.encode()
    config = json.loads((case / "case.json").read_text())
    assert config["generated_pipeline"] is True
    assert config["workdesk"]["investigation_id"] == pid
    assert config["workdesk"]["materials"][0]["sha256"] == material["sha256"]
    assert workdesk.WorkdeskStore(tmp_path).get(pid)["brief_revisions"][0]["id"] == first_id


def test_unsupported_generated_future_request_never_prepares_case(client, tmp_path):
    pid = create(client)["id"]
    content = "sensor,time,event\n" + "\n".join(f"{i / 10},{i},{i % 2}" for i in range(60))
    attach(client, pid, content=content)
    save(client, pid, study={**STUDY, "population": "future_records", "time_column": "time"})
    project = plan(client, pid)
    assert project["plan"]["status"] == "unsupported" and project["plan"]["scope_gaps"]
    assert not (tmp_path / "examples").exists()


def test_custom_code_needs_review_and_is_never_host_imported(client, tmp_path):
    pid = create(client)["id"]
    attach(client, pid)
    sentinel = tmp_path / "SHOULD_NOT_EXIST"
    source = f"from pathlib import Path\nPath({str(sentinel)!r}).write_text('executed')\n" + CUSTOM
    attached = attach(client, pid, "train.py", source)
    assert attached["suggested_source_mode"] == "custom"
    assert not sentinel.exists()
    response = client.post(f"/api/investigations/{pid}/brief", json={"target": "event", "intended_use": "Before outcome", "study": STUDY, "source_mode": "custom"})
    assert response.status_code == 400 and "trusted-local" in response.json()["detail"]
    save(client, pid, source_mode="custom", trust_code=True)
    project = plan(client, pid)
    assert project["plan"]["source_mode"] == "custom" and project["plan"]["status"] == "ready"
    assert (server.cases()[project["plan"]["case"]] / "train.py").read_bytes() == source.encode()
    assert not sentinel.exists()


def test_incompatible_and_invalid_materials_are_explicit(client):
    pid = create(client)["id"]
    for filename in ("../../data.csv", "C:\\data.csv", "paper.pdf", "notebook.ipynb"):
        assert client.post(f"/api/investigations/{pid}/materials", json={"filename": filename, "content": CSV}).status_code == 400
    attach(client, pid)
    project = attach(client, pid, "other.py", "print('not an adapter')")
    assert project["materials"][-1]["compatibility"]["status"] == "needs_adapter"
    response = client.post(f"/api/investigations/{pid}/brief", json={"target": "event", "intended_use": "Before outcome", "study": STUDY, "source_mode": "custom", "trust_code": True})
    assert response.status_code == 400


def test_material_tampering_and_revisions_do_not_reuse_case(client, tmp_path):
    pid = create(client)["id"]
    attach(client, pid)
    save(client, pid)
    original = plan(client, pid)
    first_case = original["plan"]["case"]
    first_bytes = (server.cases()[first_case] / "data.csv").read_bytes()
    attach(client, pid, "new.csv", CSV.replace("0.01,1", "1.01,1"))
    assert client.post(f"/api/investigations/{pid}/plan").status_code == 400
    save(client, pid)
    second = plan(client, pid)
    assert second["plan"]["case"] != first_case
    assert (server.cases()[first_case] / "data.csv").read_bytes() == first_bytes
    store = workdesk.WorkdeskStore(tmp_path)
    latest = second["materials"][-1]
    (store.materials_root / latest["id"]).write_text("tampered")
    assert client.post(f"/api/investigations/{pid}/plan").status_code == 400


def test_run_dispatch_links_real_job_and_keeps_pending_verdict_hidden(client, monkeypatch):
    started, finish = threading.Event(), threading.Event()

    def fake_engine(*args, **kwargs):
        started.set()
        finish.wait(5)
        return {"schema": engine.VERSION, "status": "inconclusive", "verdict": "NOT_TESTED", "events": [], "ledger": {"calls": 0, "est_usd": 0}}

    monkeypatch.setattr(engine, "run_audit", fake_engine)
    pid = create(client)["id"]
    attach(client, pid)
    save(client, pid)
    prepared = plan(client, pid)
    try:
        response = client.post(f"/api/investigations/{pid}/runs", json={"plan_id": prepared["plan"]["id"]})
        assert response.status_code == 202, response.text
        project = response.json()
        assert started.wait(2)
        assert project["runs"][0]["plan_id"] == prepared["plan"]["id"]
        assert project["runs"][0]["verdict"] is None
        assert client.post(f"/api/investigations/{pid}/runs", json={"plan_id": prepared["plan"]["id"]}).status_code == 400
        assert client.post(f"/api/investigations/{pid}/brief", json={"target": "event", "intended_use": "changed", "study": STUDY}).status_code == 400
    finally:
        finish.set()
    for _ in range(100):
        recovered = client.get(f"/api/investigations/{pid}").json()
        if recovered["runs"][0]["status"] == "inconclusive":
            break
        time.sleep(0.01)
    assert recovered["runs"][0]["verdict"] == "NOT_TESTED"
    assert recovered["dashboard"]["active_job_ids"] == []


def test_guidance_is_labelled_local_and_meta_requires_ack(client, monkeypatch):
    pid = create(client)["id"]
    local = client.post(f"/api/investigations/{pid}/messages", json={"text": "What should I upload?"})
    assert local.status_code == 200
    assert local.json()["messages"][-1]["kind"] == "local_guidance"
    assert client.post(f"/api/investigations/{pid}/messages", json={"text": "Review", "live": True, "outbound_confirmed": True}).status_code == 403
    monkeypatch.setenv("NULLLAB_ALLOW_WEB_LIVE", "1")
    assert client.post(f"/api/investigations/{pid}/messages", json={"text": "Review", "live": True}).status_code == 400


def test_meta_context_excludes_csv_rows_and_malformed_answer_stays_error(client, monkeypatch):
    from app import workdesk_api

    pid = create(client)["id"]
    attach(client, pid, content=CSV.replace("0.01,1", "7654321.123,1"))
    monkeypatch.setenv("NULLLAB_ALLOW_WEB_LIVE", "1")
    contexts = []

    class FakeProvider:
        def __init__(self, config, directory, **kwargs):
            assert kwargs == {"max_usd": 0.25, "max_calls": 4}

        def complete(self, system, user, **kwargs):
            contexts.append(user)
            return json.dumps({"text": "Inspect your target and timing", "questions": ["When is the prediction made?"], "references": ["invented-material"]})

        def ledger(self):
            return {"calls": 1, "est_usd": 0}

    monkeypatch.setattr(workdesk_api, "Provider", FakeProvider)
    preview = client.get(f"/api/investigations/{pid}").json()["outbound_preview"]["context_sha256"]
    response = client.post(f"/api/investigations/{pid}/messages", json={"text": "Please review this dataset", "live": True, "outbound_confirmed": True, "context_sha256": preview})
    assert response.status_code == 200
    assert contexts and "7654321.123" not in contexts[0]
    assert response.json()["messages"][-1]["kind"] == "guidance_error"
    assert response.json()["runs"] == []


def test_new_material_bytes_are_verified_on_explicit_read(client, tmp_path):
    pid = create(client)["id"]
    project = attach(client, pid)
    mid = project["materials"][0]["id"]
    assert client.get(f"/api/investigations/{pid}/materials/{mid}").json()["content"] == CSV
    assert client.get("/api/investigations/not-a-uuid").status_code == 400
    assert client.get(f"/api/investigations/{pid}/materials/../../private").status_code == 400
    (workdesk.WorkdeskStore(tmp_path).materials_root / mid).write_text("tampered")
    assert client.get(f"/api/investigations/{pid}/materials/{mid}").status_code == 400


def test_base64_upload_preserves_original_bom_and_line_endings(client, tmp_path):
    import base64
    import hashlib

    pid = create(client)["id"]
    raw = b"\xef\xbb\xbf" + CSV.replace("\n", "\r\n").encode()
    response = client.post(f"/api/investigations/{pid}/materials", json={"filename": "original.csv", "content_b64": base64.b64encode(raw).decode()})
    assert response.status_code == 201, response.text
    material = response.json()["materials"][0]
    assert material["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (workdesk.WorkdeskStore(tmp_path).materials_root / material["id"]).read_bytes() == raw
    save(client, pid)
    prepared = plan(client, pid)
    assert (server.cases()[prepared["plan"]["case"]] / "data.csv").read_bytes() == raw
    assert client.post(f"/api/investigations/{pid}/materials", json={"filename": "bad.csv", "content_b64": "not base64"}).status_code == 400


def test_real_own_data_investigation_baseline_and_assessment_export(client, monkeypatch):
    import zipfile

    monkeypatch.setenv("NULLLAB_NO_DOCKER", "1")
    pid = create(client)["id"]
    attach(client, pid)
    save(client, pid)
    prepared = plan(client, pid)
    response = client.post(f"/api/investigations/{pid}/runs", json={"plan_id": prepared["plan"]["id"]})
    assert response.status_code == 202, response.text
    job_id = response.json()["job"]["id"]
    for _ in range(600):
        state = server.get_job(job_id)
        if state["status"] in {"completed", "inconclusive", "failed", "cancelled"}:
            break
        time.sleep(0.05)
    assert state["status"] == "inconclusive", state
    result = state["result"]
    assert result["verdict"] == "NOT_TESTED" and result["baseline"]["reproduced"]
    assert result["baseline"]["seeds"] == [42, 43, 44] and result["ledger"]["calls"] == 0
    assert result["summary"] is None
    case = server.cases()[prepared["plan"]["case"]]
    assert (server._job_path(job_id) / "inputs/data.csv").read_bytes() == CSV.encode()
    assert json.loads((case / "case.json").read_text())["workdesk"]["investigation_id"] == pid
    target = engine.export_assessment(server._job_path(job_id) / "result.json")
    with zipfile.ZipFile(target) as archive:
        assert archive.read("inputs/data.csv") == CSV.encode()
    reopened = client.get(f"/api/investigations/{pid}").json()
    assert reopened["runs"][0]["job_id"] == job_id and reopened["runs"][0]["verdict"] == "NOT_TESTED"
    assert reopened["runs"][0]["evidence_verified"]

    # Explaining a result uses the verified completed baseline and correct role
    # model identity. No additional experiment or real inference is dispatched.
    from app import workdesk_api

    contexts = []

    class Guidance:
        def __init__(self, config, directory, **kwargs):
            pass

        def complete(self, system, user, **kwargs):
            contexts.append(json.loads(user))
            return json.dumps({"text": "A verified baseline exists; no counterfactual was measured.", "questions": [], "references": []})

        def model_for(self, role):
            assert role == "intake"
            return "test-intake-role-model"

        def ledger(self):
            return {"calls": 1, "est_usd": 0}

    monkeypatch.setattr(workdesk_api, "Provider", Guidance)
    monkeypatch.setenv("NULLLAB_ALLOW_WEB_LIVE", "1")
    response = client.post(f"/api/investigations/{pid}/messages", json={"text": "Explain my result", "live": True, "outbound_confirmed": True, "context_sha256": reopened["outbound_preview"]["context_sha256"]})
    assert response.status_code == 200, response.text
    assert contexts[0]["latest_run"]["evidence_verified"]
    assert contexts[0]["latest_run"]["baseline"]["score"] == result["baseline"]["score"]
    assert contexts[0]["latest_run"]["evidence_manifest_sha256"] == result["evidence"]["manifest_sha256"]
    assert response.json()["messages"][-1]["model"] == "test-intake-role-model"


def test_generated_engine_context_contains_question_and_actual_notes(client):
    pid = create(client)["id"]
    attach(client, pid)
    note = "Material context marker: only measurements available before the decision can be used."
    attach(client, pid, "research-notes.md", note)
    save(client, pid)
    prepared = plan(client, pid)
    case = server.cases()[prepared["plan"]["case"]]
    context = json.loads(engine._context(case, engine.preflight(case)))
    assert "Does my protocol support its evaluation claim?" in context["claim"]
    assert note in context["claim"]
    assert "Author-provided notes (not independently verified)" in context["claim"]


def test_stale_material_consent_rejected_before_meta_construction(client, monkeypatch):
    from app import workdesk_api

    pid = create(client)["id"]
    project = attach(client, pid)
    old_hash = project["outbound_preview"]["context_sha256"]
    updated = attach(client, pid, "new-private-context.md", "Changed author context")
    assert updated["outbound_preview"]["context_sha256"] != old_hash
    monkeypatch.setenv("NULLLAB_ALLOW_WEB_LIVE", "1")
    monkeypatch.setattr(workdesk_api, "Provider", lambda *args, **kwargs: pytest.fail("Provider constructed with stale consent"))
    response = client.post(f"/api/investigations/{pid}/messages", json={"text": "Review", "live": True, "outbound_confirmed": True, "context_sha256": old_hash})
    assert response.status_code == 409
    assert client.get(f"/api/investigations/{pid}").json()["messages"] == updated["messages"]


def test_reviewed_plan_id_cannot_be_replaced_by_another_tab(client):
    pid = create(client)["id"]
    attach(client, pid)
    save(client, pid)
    first = plan(client, pid)
    second = plan(client, pid)
    assert first["plan"]["id"] != second["plan"]["id"]
    response = client.post(f"/api/investigations/{pid}/runs", json={"plan_id": first["plan"]["id"]})
    assert response.status_code == 409
    assert client.get(f"/api/investigations/{pid}").json()["runs"] == []


def test_failed_checkpoint_numbers_never_become_chat_or_dashboard_findings(client, tmp_path):
    from agent.storage import write_json

    pid = create(client)["id"]
    attach(client, pid)
    job_id = workdesk.uid()
    path = server._job_path(job_id)
    write_json(path / "job.json", {"id": job_id, "status": "failed", "error": "Server restarted", "case": "saved"})
    write_json(path / "result.json", {"status": "completed", "verdict": "INFLATED", "summary": {"claimed": 0.971234, "controlled": 0.321234, "metric": "accuracy"}, "baseline": {"score": 0.971234}})
    workdesk.WorkdeskStore(tmp_path).change(pid, lambda p: p["runs"].append({"job_id": job_id, "revision_id": "prior", "plan_id": "prior", "created_at": workdesk.now()}))
    detail = client.get(f"/api/investigations/{pid}").json()
    assert detail["runs"][0]["summary"] is None and detail["runs"][0]["baseline"] is None
    assert not detail["runs"][0]["measured"] and detail["runs"][0]["checkpoint_only"]
    response = client.post(f"/api/investigations/{pid}/messages", json={"text": "What does my result mean?"})
    assert response.status_code == 200
    text = response.json()["messages"][-1]["text"]
    assert "0.971234" not in text and "0.321234" not in text and "finalized" in text


def test_db_link_failure_cancels_queued_job_before_execution(client, monkeypatch):
    import sqlite3

    pid = create(client)["id"]
    attach(client, pid)
    save(client, pid)
    prepared = plan(client, pid)
    executed = threading.Event()
    monkeypatch.setattr(engine, "run_audit", lambda *args, **kwargs: executed.set() or pytest.fail("Orphan audit executed"))

    def fail_change(*args, **kwargs):
        raise sqlite3.OperationalError("simulated linkage failure")

    monkeypatch.setattr(workdesk.WorkdeskStore, "change", fail_change)
    response = client.post(f"/api/investigations/{pid}/runs", json={"plan_id": prepared["plan"]["id"]})
    assert response.status_code == 503 and "cancelled" in response.json()["detail"]
    paths = list(server.JOBS_ROOT.glob("*/job.json"))
    assert len(paths) == 1
    for _ in range(100):
        job = json.loads(paths[0].read_text())
        if job["status"] == "cancelled":
            break
        time.sleep(0.01)
    assert job["status"] == "cancelled" and not executed.is_set()


def test_explicit_example_copies_only_original_inputs_with_exact_bytes(client, tmp_path):
    source = tmp_path / "examples/secom"
    source.mkdir(parents=True)
    csv = b"\xef\xbb\xbf" + CSV.replace("\n", "\r\n").encode()
    originals = {"data.csv": csv, "train.py": CUSTOM.replace("\n", "\r\n").encode(), "excerpt.md": b"Same-process synthetic example\r\n"}
    for name, data in originals.items():
        (source / name).write_bytes(data)
    (source / "results.json").write_text('{"never_copy":"precomputed result"}')
    pid = create(client)["id"]
    response = client.post(f"/api/investigations/{pid}/example", json={"case": "secom"})
    assert response.status_code == 200, response.text
    project = response.json()
    assert len(project["materials"]) == 3 and project["runs"] == []
    store = workdesk.WorkdeskStore(tmp_path)
    for material in project["materials"]:
        assert (store.materials_root / material["id"]).read_bytes() == originals[material["filename"]]


def test_example_batch_failure_rolls_back_material_records_and_staged_files(client, tmp_path):
    source = tmp_path / "examples/secom"
    source.mkdir(parents=True)
    (source / "data.csv").write_text(CSV)
    (source / "train.py").write_text(CUSTOM)
    (source / "excerpt.md").write_text("x" * (workdesk.MAX_TEXT_BYTES + 1))
    pid = create(client)["id"]
    response = client.post(f"/api/investigations/{pid}/example", json={"case": "secom"})
    assert response.status_code == 400
    assert client.get(f"/api/investigations/{pid}").json()["materials"] == []
    assert not list(workdesk.WorkdeskStore(tmp_path).materials_root.iterdir())


def test_changed_material_bytes_block_live_guidance_even_with_current_preview(client, monkeypatch, tmp_path):
    from app import workdesk_api

    pid = create(client)["id"]
    project = attach(client, pid)
    mid = project["materials"][0]["id"]
    (workdesk.WorkdeskStore(tmp_path).materials_root / mid).write_text("changed on disk")
    monkeypatch.setenv("NULLLAB_ALLOW_WEB_LIVE", "1")
    monkeypatch.setattr(workdesk_api, "Provider", lambda *args, **kwargs: pytest.fail("Provider constructed from changed material bytes"))
    response = client.post(f"/api/investigations/{pid}/messages", json={"text": "Review", "live": True, "outbound_confirmed": True, "context_sha256": project["outbound_preview"]["context_sha256"]})
    assert response.status_code == 400 and "changed" in response.json()["detail"]
