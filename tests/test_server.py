"""Current server must not render legacy experiment pages."""
from fastapi.testclient import TestClient
from app import server

def test_workspace_does_not_depend_on_legacy_render(monkeypatch):
    from report import render
    def forbidden():
        raise AssertionError("Historical rendering must not run on current product requests")
    monkeypatch.setattr(render, "render_all", forbidden)
    with TestClient(server.app) as c:
        for _ in range(2):
            r = c.get("/")
            assert r.status_code == 200 and "From claim to evidence" in r.text

def test_demo_is_versioned_manufacturing_evidence():
    with TestClient(server.app) as c:
        r = c.get("/api/demo")
        assert r.status_code == 200 and r.json()["schema"] == "nulllab.demo.v2"
        assert all(x["case"].startswith("secom") for x in r.json()["cases"])
