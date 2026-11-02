"""Guards the preregistration freeze: frozen files must still match docs/FROZEN-HASHES.json
and the hashes written into the prereg logs. A deliberate change must be acknowledged in
docs/FROZEN-CHANGELOG.json (old hash, new hash, reason). Runs in well under a second."""

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("freeze_check", ROOT / "scripts" / "freeze_check.py")
fc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fc)
fc.ALLOW_MISSING_DATA = bool(os.environ.get("CI"))  # gitignored frozen data.csv is absent in a fresh clone


def test_manifest_matches_working_tree():
    assert fc.check_manifest() == []


def test_prereg_logs_match_working_tree():
    assert fc.check_logs() == []


def test_manifest_covers_the_frozen_list():
    m = json.loads(fc.MANIFEST.read_text(encoding="utf-8"))
    assert set(m["files"]) == set(fc.frozen_paths())
    assert set(m["prereg_logs"]) == set(fc.LOGS)
    assert len(m["files"]) >= 50


def test_changelog_entries_are_complete():
    for c in fc.load_changelog():
        assert {"path", "old_sha256", "new_sha256", "reason", "date"} <= set(c)
        assert c["reason"].strip()


def test_changelog_acknowledges_only_the_exact_transition(tmp_path, monkeypatch):
    cl = tmp_path / "c.json"
    cl.write_text(
        json.dumps(
            {
                "changes": [
                    {
                        "path": "sandbox/run.py",
                        "old_sha256": "a",
                        "new_sha256": "b",
                        "reason": "security fix",
                        "date": "2026-11-05",
                    }
                ]
            }
        )
    )
    monkeypatch.setattr(fc, "CHANGELOG", cl)
    assert fc.acknowledged("sandbox/run.py", "a", "b")
    assert not fc.acknowledged("sandbox/run.py", "a", "c")
    assert not fc.acknowledged("sandbox/executor.py", "a", "b")


def test_unacknowledged_edit_is_detected(tmp_path, monkeypatch):
    m = json.loads(fc.MANIFEST.read_text(encoding="utf-8"))
    m["files"]["sandbox/run.py"] = "0" * 64
    fake = tmp_path / "m.json"
    fake.write_text(json.dumps(m))
    monkeypatch.setattr(fc, "MANIFEST", fake)
    assert any("sandbox/run.py" in p for p in fc.check_manifest())
