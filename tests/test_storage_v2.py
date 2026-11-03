"""Checkpoint replacement must keep the old record intact during sharing locks."""

import json

import pytest

from agent import storage


def test_transient_sharing_locks_keep_the_old_checkpoint_until_atomic_replace(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    path.write_text('{"status":"running"}')
    replace = storage.os.replace
    attempts, delays = [], []

    def sharing_lock(source, target):
        attempts.append(True)
        if len(attempts) <= 2:
            assert json.loads(path.read_text())["status"] == "running"
            raise PermissionError("transient sharing lock")
        replace(source, target)

    monkeypatch.setattr(storage.os, "replace", sharing_lock)
    monkeypatch.setattr(storage.time, "sleep", delays.append)
    storage.write_json(path, {"status": "completed"})
    assert len(attempts) == 3 and delays == [0.01, 0.02]
    assert json.loads(path.read_text())["status"] == "completed"
    assert not list(tmp_path.glob("*.tmp"))


def test_permanent_failure_is_bounded_and_preserves_old_record(tmp_path, monkeypatch):
    path = tmp_path / "result.json"
    path.write_text('{"status":"running"}')
    attempts, delays = [], []

    def denied(*args):
        attempts.append(True)
        raise PermissionError("permanent denial")

    monkeypatch.setattr(storage.os, "replace", denied)
    monkeypatch.setattr(storage.time, "sleep", delays.append)
    with pytest.raises(PermissionError):
        storage.write_json(path, {"status": "completed"})
    assert len(attempts) == 7 and sum(delays) < 1
    assert json.loads(path.read_text())["status"] == "running"
    assert not list(tmp_path.glob("*.tmp"))
