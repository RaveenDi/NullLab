"""app/server.py renders the demo once (startup / mock run), not on every GET."""

import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402

from app import server  # noqa: E402


def test_index_is_rendered_once_not_per_request(monkeypatch):
    calls = []
    monkeypatch.setattr(server.render, "render_all", lambda: calls.append(1) or 9)
    monkeypatch.setattr(server, "_INDEX_HTML", None)
    with TestClient(server.app) as client:  # entering the context runs the startup render
        assert len(calls) == 1
        for _ in range(3):
            r = client.get("/")
            assert r.status_code == 200 and "NullLab" in r.text
        assert len(calls) == 1


def test_lazy_render_without_lifespan(monkeypatch):
    calls = []
    monkeypatch.setattr(server.render, "render_all", lambda: calls.append(1) or 9)
    monkeypatch.setattr(server, "_INDEX_HTML", None)
    client = TestClient(server.app)  # no `with`: no startup hook
    assert client.get("/").status_code == 200
    assert client.get("/").status_code == 200
    assert len(calls) == 1


def test_demo_api_unchanged():
    r = TestClient(server.app).get("/api/demo")
    assert r.status_code == 200 and isinstance(r.json(), dict)
