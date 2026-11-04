"""Checkpoint replacement must keep the old record intact during sharing locks."""

import json
from pathlib import Path

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


def test_case_publication_retries_sharing_denials_and_preserves_complete_bytes(tmp_path, monkeypatch):
    source, destination = tmp_path / ".staging", tmp_path / "case"
    source.mkdir()
    (source / "data.csv").write_bytes(b"x,y\r\n1,0\r\n")
    rename, attempts, delays = Path.rename, [], []

    def locked(path, target):
        attempts.append(True)
        if len(attempts) < 3:
            raise PermissionError("Windows indexer sharing denial")
        return rename(path, target)

    monkeypatch.setattr(Path, "rename", locked)
    monkeypatch.setattr(storage.time, "sleep", delays.append)
    storage.publish_directory(source, destination)
    assert len(attempts) == 3 and delays == [0.01, 0.02]
    assert not source.exists() and (destination / "data.csv").read_bytes() == b"x,y\r\n1,0\r\n"


def test_case_publication_never_overwrites_an_existing_revision(tmp_path, monkeypatch):
    source, destination = tmp_path / ".staging", tmp_path / "case"
    source.mkdir()
    destination.mkdir()
    (destination / "original").write_bytes(b"original")
    monkeypatch.setattr(Path, "rename", lambda *_: pytest.fail("Existing destination must not be renamed over"))
    with pytest.raises(FileExistsError):
        storage.publish_directory(source, destination)
    assert source.is_dir() and (destination / "original").read_bytes() == b"original"


@pytest.mark.parametrize("failure", [PermissionError("permanent denial"), FileNotFoundError("missing staging")])
def test_case_publication_fails_bounded_without_publishing_partial_inputs(tmp_path, monkeypatch, failure):
    source, destination = tmp_path / ".staging", tmp_path / "case"
    source.mkdir()
    attempts, delays = [], []

    def denied(*args):
        attempts.append(True)
        raise failure

    monkeypatch.setattr(Path, "rename", denied)
    monkeypatch.setattr(storage.time, "sleep", delays.append)
    with pytest.raises(type(failure)):
        storage.publish_directory(source, destination)
    assert len(attempts) == (6 if isinstance(failure, PermissionError) else 1)
    assert sum(delays) < 0.32 and source.is_dir() and not destination.exists()
