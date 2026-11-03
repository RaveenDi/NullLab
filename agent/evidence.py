"""Content identity for reusable evidence. Hashes detect changes, not authenticity.

Capture before execution, verify again after execution, and store the manifest on
the result as ``evidence``. A legacy result without identity is historical data;
it must never be silently upgraded by hashing today's input files.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "nulllab.evidence.v1"
INPUTS = ("train.py", "data.csv", "excerpt.md", "case.json", "contract.json")
INSTRUMENTS = (
    "agent/evidence.py",
    "sandbox/run.py",
    "sandbox/run_factorial.py",
    "sandbox/factorial_stats.py",
    "agent/edit_dsl.py",
    "agent/contract_g9.py",
    "agent/engine.py",
    "agent/study.py",
    "agent/intake.py",
    "agent/storage.py",
    "agent/provider.py",
    "sandbox/limits.py",
    "sandbox/executor.py",
    "agent/guard_g9.py",
)


class EvidenceError(ValueError):
    """A result cannot establish that it belongs to the supplied inputs."""


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def input_hashes(case_dir: str | Path) -> dict:
    case_dir = Path(case_dir)
    for name in ("train.py", "data.csv"):
        if not (case_dir / name).is_file():
            raise EvidenceError(f"missing required input: {name}")
    return {name: file_hash(case_dir / name) if (case_dir / name).is_file() else None for name in INPUTS}


def capture(case_dir: str | Path, *, sources: dict | None = None, context: dict | None = None) -> dict:
    """Capture exact input/patch bytes, execution context and instrument identity."""
    versions = {"python": platform.python_version()}
    for name in ("numpy", "pandas", "scikit-learn"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    result = {
        "schema": SCHEMA,
        "inputs": input_hashes(case_dir),
        "sources": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sorted((sources or {}).items())},
        "context": json.loads(json.dumps(context or {}, allow_nan=False)),
        "environment": versions,
        "instruments": {name: file_hash(ROOT / name) for name in INSTRUMENTS if (ROOT / name).is_file()},
    }
    result["manifest_sha256"] = digest(result)
    return result


def verify(
    case_dir: str | Path,
    record: dict,
    *,
    require: bool = True,
    context: dict | None = None,
    current_instrument: bool = False,
) -> bool:
    """Reject input/patch mismatch. Optionally require current engine/context for reuse.

    Exporting an immutable historical run may legitimately use an older instrument;
    model reuse should require ``current_instrument=True`` and its expected context.
    """
    manifest = record.get("evidence")
    if not manifest:
        if require:
            raise EvidenceError(
                "result has no audit-time input manifest; historical evidence cannot be reused/exported as a current audit"
            )
        return False
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise EvidenceError("unsupported evidence manifest")
    body = {k: v for k, v in manifest.items() if k != "manifest_sha256"}
    if manifest.get("manifest_sha256") != digest(body):
        raise EvidenceError("evidence manifest is inconsistent")
    if manifest.get("inputs") != input_hashes(case_dir):
        raise EvidenceError("input mismatch: code, data, claim or contract changed since the audit")
    patches = {k: hashlib.sha256(v.encode()).hexdigest() for k, v in sorted((record.get("sources") or {}).items())}
    if manifest.get("sources") != patches:
        raise EvidenceError("stored patch sources differ from audited patches")
    if context is not None and manifest.get("context") != context:
        raise EvidenceError("execution context changed; refusing reuse")
    if current_instrument:
        current = capture(case_dir, sources=record.get("sources"), context=manifest.get("context"))
        if any(current.get(k) != manifest.get(k) for k in ("environment", "instruments")):
            raise EvidenceError("instrument or environment changed; refusing reuse")
    return True
