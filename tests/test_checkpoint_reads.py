"""Transient Windows sharing failures must not invent a missing saved audit."""
from pathlib import Path

from app import server


def test_checkpoint_read_recovers_from_transient_access_denial(tmp_path, monkeypatch):
    path = tmp_path / "job.json"
    path.write_text('{"status":"running"}', encoding="utf-8")
    original, attempts, waits = Path.read_text, [], []

    def read(value, **kwargs):
        attempts.append(value)
        if len(attempts) < 3:
            raise PermissionError("transient checkpoint sharing")
        return original(value, **kwargs)

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(server.time, "sleep", waits.append)
    assert server._read(path) == {"status": "running"}
    assert len(attempts) == 3 and waits == [0.01, 0.02]


def test_corrupt_checkpoint_is_not_retried_or_repaired(tmp_path, monkeypatch):
    path = tmp_path / "job.json"
    path.write_text('{"unfinished":', encoding="utf-8")
    waits = []
    monkeypatch.setattr(server.time, "sleep", waits.append)
    assert server._read(path) is None and waits == []
    assert path.read_text(encoding="utf-8") == '{"unfinished":'


def test_permanent_read_denial_has_bounded_backoff(tmp_path, monkeypatch):
    waits = []

    def denied(*args, **kwargs):
        raise PermissionError("permanent denial")

    monkeypatch.setattr(Path, "read_text", denied)
    monkeypatch.setattr(server.time, "sleep", waits.append)
    assert server._read(tmp_path / "job.json") is None
    assert waits == [0.01, 0.02, 0.04, 0.08, 0.16]
