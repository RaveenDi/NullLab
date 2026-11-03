"""Local workspace contract checks, without browser or model calls."""

from fastapi.testclient import TestClient
from app import server


def test_local_workspace_assets_and_intake(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "JOBS_ROOT", tmp_path / "jobs")
    with TestClient(server.app) as c:
        assert c.get("/").status_code == 200
        assert c.get("/static/workspace.js").status_code == 200
        assert c.get("/static/workspace-shell.js").status_code == 200
        assert "cases" in c.get("/api/cases").json()
        assert c.post("/api/jobs", json={"case": "../../private"}).status_code == 400
        assert c.post("/api/jobs", json={"case": "secom", "live": True}).status_code == 403
        assert (
            c.post("/api/jobs", json={"case": "secom"}, headers={"origin": "https://evil.example"}).status_code == 403
        )
        assert c.get("/", headers={"host": "evil.example"}).status_code == 403
        assert c.get("/api/jobs/not-an-id").status_code == 404


def test_job_uses_engine_and_unique_persisted_state(tmp_path, monkeypatch):
    import time
    from agent import engine

    monkeypatch.setattr(server, "JOBS_ROOT", tmp_path / "jobs")
    monkeypatch.setattr(
        engine,
        "run_audit",
        lambda *a, **kw: {"schema": "nulllab.audit.v2", "status": "completed", "verdict": "NOT_TESTED", "events": []},
    )
    with TestClient(server.app) as c:
        j = c.post("/api/jobs", json={"case": "secom"}).json()
        for _ in range(50):
            state = c.get("/api/jobs/" + j["id"]).json()
            if state["status"] == "completed":
                break
            time.sleep(0.01)
        assert state["result"]["schema"] == "nulllab.audit.v2"
        assert (tmp_path / "jobs" / j["id"] / "job.json").exists()


def test_data_adapter_rejects_invalid_targets(tmp_path):
    import pytest
    from agent.intake import prepare

    with pytest.raises(ValueError, match="both 0 and 1"):
        prepare("x,y\n" + "1,0\n" * 30, "y", "retrospective", tmp_path / "case")
