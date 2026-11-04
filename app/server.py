"""Local author workspace: uvicorn app.server:app --host 127.0.0.1 --port 8099.
Curated repository cases execute as trusted local code, not public uploads.
"""

from __future__ import annotations

import json
import csv
import math
import os
import sys
import time
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from agent.storage import publish_directory, write_json

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("NULLLAB_WORKSPACE", Path.cwd())).resolve()
STATIC = Path(__file__).parent / "static"
JOBS_ROOT = WORKSPACE / "out" / "jobs"
_LOCK = threading.RLock()
_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="nulllab")
_ACTIVE: set[str] = set()
_TERMINAL = {"completed", "inconclusive", "failed", "cancelled"}


def _now():
    return datetime.now(UTC).isoformat()


def _write(path: Path, value: dict):
    write_json(path, value)


def _read(path: Path):
    # Windows indexers/sync can briefly deny reads while an atomic checkpoint
    # replacement completes. Retry only sharing/access failures, not corruption
    # or a genuinely missing record. Total backoff is bounded to 0.31 seconds.
    delays = (0.01, 0.02, 0.04, 0.08, 0.16)
    for attempt in range(len(delays) + 1):
        try:
            if path.is_symlink():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            transient = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33}
            if not transient or attempt == len(delays):
                return None
            time.sleep(delays[attempt])
        except ValueError:
            return None
    return None


def _job_path(job_id: str):
    try:
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError
    except ValueError:
        raise HTTPException(404, "Unknown audit") from None
    path = JOBS_ROOT / job_id
    if path.is_symlink() or not path.resolve().is_relative_to(JOBS_ROOT.resolve()):
        raise HTTPException(404, "Unknown audit")
    return path


def cases():
    """Expose curated examples only; never resolve a caller-supplied path."""
    result = {}
    examples = (WORKSPACE / "examples").resolve()
    if not examples.exists():
        return result
    for folder in sorted(examples.iterdir()):
        if (
            not folder.is_dir()
            or folder.name.startswith(".")
            or folder.is_symlink()
            or not folder.resolve().is_relative_to(examples)
            or not all((folder / f).is_file() and not (folder / f).is_symlink() for f in ("train.py", "data.csv", "excerpt.md"))
            or ((folder / "case.json").exists() and ((folder / "case.json").is_symlink() or not (folder / "case.json").is_file()))
        ):
            continue
        result[folder.name] = folder
    return result


def _config(case_dir):
    if case_dir.is_symlink():
        return {}
    value = _read(case_dir / "case.json")
    return value if isinstance(value, dict) else {}


def _case_detail(case_id):
    from agent import evidence
    from agent import study as study_contract

    case_dir = cases().get(case_id)
    if case_dir is None:
        raise HTTPException(404, "Unknown local case")
    config = _config(case_dir)
    with (case_dir / "data.csv").open(encoding="utf-8-sig", newline="") as handle:
        columns = next(csv.reader(handle), [])
    predictors = config.get("predictor_columns")
    if not isinstance(predictors, list):
        predictors = [name for name in columns if name != config.get("target")]
    declaration = config.get("study")
    profile = config.get("intake_profile")
    profile_matches = (isinstance(profile, dict) and profile.get("schema") == "nulllab.intake-profile.v1"
                       and profile.get("data_sha256") == evidence.file_hash(case_dir / "data.csv")
                       and profile.get("target") == config.get("target") and profile.get("predictor_columns") == predictors)
    try:
        if declaration is not None:
            declaration = study_contract.normalize(declaration, columns, config.get("target"))
        review = study_contract.review(declaration, generated=config.get("generated_pipeline") is True, predictor_columns=predictors,
                                      facts=profile.get("facts") if profile_matches else None)
        if profile and not profile_matches:
            review["warnings"].append("Saved intake diagnostics no longer match these inputs. An audit recomputes the diagnostics before execution.")
    except (ValueError, KeyError, TypeError):
        review = {"status": "invalid", "questions": [], "scope_gaps": [], "warnings": ["The stored research brief could not be validated."]}
    return {
        "id": case_id,
        "title": config.get("title", case_id),
        "claim": (case_dir / "excerpt.md").read_text(encoding="utf-8"),
        "intended_use": config.get("intended_use", ""),
        "target": config.get("target"),
        "study": declaration,
        "study_review": review,
        "predictors": predictors,
        "generated_pipeline": config.get("generated_pipeline") is True,
        "lineage": config.get("lineage"),
        "profile_source": "saved_intake_diagnostics" if profile_matches else "not_available",
    }


def _new_generated_case(csv_text, target, intended_use, study, lineage=None):
    """Commit a complete generated case; partial imports never enter the catalog."""
    from agent.intake import prepare

    examples = (WORKSPACE / "examples").resolve()
    staging_root = (WORKSPACE / "out" / "intake-staging").resolve()
    if not examples.is_relative_to(WORKSPACE) or not staging_root.is_relative_to(WORKSPACE):
        raise ValueError("The configured workspace cannot contain external case links")
    name = "user-" + uuid.uuid4().hex
    staging = staging_root / name
    detail = prepare(csv_text, target, intended_use, staging, study=study)
    if lineage is not None:
        config = _config(staging)
        config["lineage"] = lineage
        _write(staging / "case.json", config)
    examples.mkdir(parents=True, exist_ok=True)
    publish_directory(staging, examples / name)
    return {"case": name, **detail, "lineage": lineage}


def _result_integrity(job, result):
    """Read-time provenance projection; never rewrite historical result bytes."""
    finalized = job.get("status") in _TERMINAL and isinstance(result, dict) and result.get("status") == job.get("status")
    view = {"result_finalized": finalized, "evidence_verified": False, "evidence_error": None}
    if job.get("status") not in _TERMINAL:
        return view
    if not finalized:
        view["evidence_error"] = "The saved checkpoint was not finalized. No completed measurement is established."
        return view
    try:
        from agent.evidence import verify

        verify(_job_path(job["id"]) / "inputs", result)
        record = result.get("record")
        if result.get("summary") and not isinstance(record, dict):
            raise ValueError("Missing measured control identity")
        if record is not None and (not isinstance(record, dict) or record.get("evidence") != result.get("evidence") or record.get("sources") != result.get("sources")):
            raise ValueError("Nested measured control identity differs")
        view["evidence_verified"] = True
    except (OSError, ValueError, TypeError, KeyError):
        view["evidence_error"] = "Saved input/control identity could not be verified. No numerical conclusion or verified export is supplied."
    return view


def _job_summary(job):
    directory = _job_path(job["id"])
    result = _read(directory / "result.json")
    result = result if isinstance(result, dict) else {}
    config = _config(directory / "inputs")
    evidence = result.get("evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    summary, baseline = result.get("summary"), result.get("baseline")
    summary = summary if isinstance(summary, dict) else {}
    baseline = baseline if isinstance(baseline, dict) else {}
    ledger = result.get("ledger")
    ledger = ledger if isinstance(ledger, dict) else {}
    checkpoint_only = job.get("status") in _TERMINAL and bool(result) and result.get("status") != job.get("status")
    integrity = _result_integrity(job, result)
    verified = integrity["evidence_verified"]

    def number(value):
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None

    return {
        **{name: job.get(name) for name in ("id", "case", "status", "created_at", "updated_at", "live", "critic")},
        "title": config.get("title", job.get("title", job.get("case"))),
        "lineage": config.get("lineage", job.get("lineage")),
        "verdict": "INCONCLUSIVE" if checkpoint_only else result.get("verdict") if verified else None,
        **integrity,
        "checkpoint_only": checkpoint_only,
        "mode": result.get("mode", "live" if job.get("live") else "rules"),
        "metric": summary.get("metric", baseline.get("metric")),
        "seeds": summary.get("seeds", baseline.get("seeds", (evidence.get("context") or {}).get("seeds"))),
        "baseline_score": number(baseline.get("score")) if verified else None,
        "controlled_score": number(summary.get("controlled")) if verified else None,
        "measured": bool(summary) and verified,
        "evidence": {name: evidence.get(name) for name in ("inputs", "sources", "instruments", "environment", "context")},
        "ledger": {name: number(ledger.get(name, 0)) for name in ("calls", "est_usd")},
    }


def _run(job_id, case_dir):
    from agent import engine

    directory = _job_path(job_id)
    path = directory / "job.json"
    with _LOCK:
        job = _read(path)
        if job["cancel_requested"]:
            job.update(status="cancelled", updated_at=_now())
            _write(path, job)
            _ACTIVE.discard(job_id)
            return
        job.update(status="running", updated_at=_now())
        _write(path, job)

    def cancelled():
        with _LOCK:
            return bool((_read(path) or {}).get("cancel_requested"))

    try:
        result = engine.run_audit(case_dir, directory, live=job["live"], critic=job["critic"], cancelled=cancelled)
        _write(directory / "result.json", result)
        with _LOCK:
            latest = _read(path)
            latest.update(status=result.get("status", "completed"), updated_at=_now())
            if latest["status"] not in _TERMINAL:
                latest.update(status="failed", error="Engine returned an invalid terminal state")
            _write(path, latest)
    except Exception as exc:
        # Never put a provider payload/credential-bearing exception into browser output.
        with _LOCK:
            latest = _read(path)
            latest.update(
                status="failed",
                error=f"Audit could not finish ({type(exc).__name__}). Inspect local configuration.",
                updated_at=_now(),
            )
            _write(path, latest)
    finally:
        with _LOCK:
            _ACTIVE.discard(job_id)


@asynccontextmanager
async def lifespan(_app):
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        for file in JOBS_ROOT.glob("*/job.json"):
            job = _read(file)
            if job and job.get("status") in ("queued", "running") and job.get("id") not in _ACTIVE:
                job.update(
                    status="failed",
                    error="Local server restarted before this audit finished. Start a new audit.",
                    updated_at=_now(),
                )
                _write(file, job)
    yield


app = FastAPI(title="NullLab author workspace", version="2.0", lifespan=lifespan)


@app.middleware("http")
async def local_boundary(request: Request, call_next):
    host = request.url.hostname
    client = request.client.host if request.client else ""
    # testclient/testserver are in-process identities and never network addresses.
    if host not in {"localhost", "127.0.0.1", "::1", "testserver"} or client not in {"127.0.0.1", "::1", "testclient"}:
        return JSONResponse({"detail": "This workspace accepts local connections only."}, status_code=403)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.url.netloc:
            return JSONResponse({"detail": "Cross-origin audit requests are refused."}, status_code=403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse({"detail": "Cross-site audit requests are refused."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
    )
    response.headers["Cache-Control"] = "no-store"
    return response


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index(request: Request):
    # Preserve previously shared saved-job links after separating the pages.
    return FileResponse(STATIC / ("evidence.html" if request.query_params.get("job") else "index.html"))


@app.get("/workdesk")
def workdesk_page():
    return FileResponse(STATIC / "workdesk.html")


@app.get("/evidence")
def evidence_page():
    return FileResponse(STATIC / "evidence.html")


@app.get("/architecture")
def architecture_page():
    return FileResponse(STATIC / "architecture.html")


@app.get("/api/cases")
def api_cases():
    return {
        "cases": [
            {
                "id": name,
                "title": _config(path).get("title", name),
                "claim": (path / "excerpt.md").read_text(encoding="utf-8") if (path / "excerpt.md").exists() else "",
            }
            for name, path in cases().items()
        ],
        "live_enabled": os.environ.get("NULLLAB_ALLOW_WEB_LIVE") == "1",
        "input_mode": "curated_local_cases",
    }


@app.get("/api/cases/{case_id}")
def get_case(case_id: str):
    return _case_detail(case_id)


class DataRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str
    target: str
    intended_use: str
    study: dict | None = None


@app.post("/api/intake", status_code=201)
async def data_intake(request: Request):
    raw = bytearray()
    async for chunk in request.stream():
        raw.extend(chunk)
        if len(raw) > 6_000_000:
            raise HTTPException(413, "CSV intake request exceeds 6 MB")
    try:
        body = DataRequest.model_validate_json(raw)
        return _new_generated_case(body.csv, body.target, body.intended_use, body.study)
    except (ValueError, TypeError) as exc:
        raise HTTPException(400, str(exc)[:500]) from None


class RevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study: dict
    intended_use: str = Field(min_length=1, max_length=4000)
    parent_job_id: uuid.UUID | None = None
    reason: str | None = Field(default=None, max_length=4000)


@app.post("/api/cases/{case_id}/revisions", status_code=201)
def revise_case(case_id: str, body: RevisionRequest):
    from agent import engine, evidence

    source = cases().get(case_id)
    if source is None:
        raise HTTPException(404, "Unknown local case")
    config = _config(source)
    if config.get("generated_pipeline") is not True or config.get("adapter") not in {"numeric-binary-rf-v1", "numeric-binary-rf-v2"}:
        raise HTTPException(409, "This case contains external code. Revise it through the trusted local adapter; it will not be silently regenerated.")
    try:
        if config.get("adapter") == "numeric-binary-rf-v2":
            engine.preflight(source)
        parent_inputs = evidence.input_hashes(source)
    except (OSError, ValueError, KeyError, TypeError):
        raise HTTPException(409, "The generated case was modified outside its adapter. Restore it or import an explicitly custom local case.") from None
    parent_job = str(body.parent_job_id) if body.parent_job_id else None
    parent_manifest = None
    if parent_job:
        job = _read(_job_path(parent_job) / "job.json")
        if not isinstance(job, dict) or job.get("case") != case_id:
            raise HTTPException(400, "The source audit does not belong to this case")
        if job.get("status") not in _TERMINAL:
            raise HTTPException(409, "Wait for the source audit to finish before creating a linked revision")
        result = _read(_job_path(parent_job) / "result.json")
        if isinstance(result, dict) and result.get("evidence"):
            try:
                evidence.verify(_job_path(parent_job) / "inputs", result)
                if result["evidence"]["inputs"] != parent_inputs:
                    raise ValueError("case changed since the linked audit")
                parent_manifest = result["evidence"]["manifest_sha256"]
            except (OSError, ValueError, KeyError, TypeError):
                raise HTTPException(409, "The linked audit no longer matches this case's input identity") from None
    old_lineage = config.get("lineage")
    old_lineage = old_lineage if isinstance(old_lineage, dict) else {}
    lineage = {
        "root_case": old_lineage.get("root_case", case_id),
        "parent_case": case_id,
        "parent_job": parent_job,
        "parent_inputs": parent_inputs,
        "parent_manifest_sha256": parent_manifest,
        "reason": body.reason or "Author updated the research brief; declarations require re-evaluation.",
        "created_at": _now(),
    }
    try:
        return _new_generated_case((source / "data.csv").read_bytes().decode("utf-8"), config["target"], body.intended_use, body.study, lineage)
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(400, str(exc)[:500]) from None


@app.get("/api/demo")
def api_demo():
    demo = _read(WORKSPACE / "examples" / "secom" / "results.json")
    return (
        demo
        if demo is not None
        else {
            "schema": "nulllab.demo.v2",
            "cases": [],
            "status": "not_recorded",
            "message": "No manufacturing recording exists yet. Run an available case to generate fresh evidence.",
        }
    )


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case: str
    live: bool = False
    critic: bool = False
    outbound_confirmed: bool = False


@app.post("/api/jobs", status_code=202)
def create_job(body: AuditRequest):
    available = cases()
    if body.case not in available:
        raise HTTPException(400, "Select an available local example. Arbitrary paths and uploads are unsupported.")
    if body.live and os.environ.get("NULLLAB_ALLOW_WEB_LIVE") != "1":
        raise HTTPException(403, "Live model calls are disabled. Configure the local provider first.")
    if body.live and not body.outbound_confirmed:
        raise HTTPException(400, "Review and acknowledge outbound data before using a hosted model.")
    if body.critic and not body.live:
        raise HTTPException(400, "The methodology critic requires live model access.")
    with _LOCK:
        if len(_ACTIVE) >= 4:
            raise HTTPException(429, "The local queue is full. Wait for an audit to finish or cancel one.")
        job_id = str(uuid.uuid4())
        job = {
            "id": job_id,
            "case": body.case,
            "live": body.live,
            "critic": body.critic,
            "status": "queued",
            "created_at": _now(),
            "updated_at": _now(),
            "cancel_requested": False,
            "title": _config(available[body.case]).get("title", body.case),
            "lineage": _config(available[body.case]).get("lineage"),
        }
        _write(_job_path(job_id) / "job.json", job)
        _ACTIVE.add(job_id)
        try:
            _POOL.submit(_run, job_id, available[body.case])
        except RuntimeError:
            _ACTIVE.discard(job_id)
            job.update(status="failed", error="Audit worker unavailable", updated_at=_now())
            _write(_job_path(job_id) / "job.json", job)
            raise HTTPException(503, "Audit worker unavailable") from None
    return job


@app.get("/api/jobs")
def list_jobs(limit: int = Query(default=30, ge=1, le=100), case: str | None = Query(default=None, max_length=128)):
    """Recover local audits without returning vectors, code or dataset rows."""
    jobs = []
    for file in JOBS_ROOT.glob("*/job.json"):
        if file.is_symlink() or file.parent.is_symlink() or not file.resolve().is_relative_to(JOBS_ROOT.resolve()):
            continue
        job = _read(file)
        if not isinstance(job, dict) or job.get("id") != file.parent.name:
            continue
        try:
            _job_path(job["id"])
        except HTTPException:
            continue
        if case is None or job.get("case") == case:
            jobs.append(job)
    jobs.sort(key=lambda job: str(job.get("created_at", "")), reverse=True)
    return {
        "jobs": [_job_summary(job) for job in jobs[:limit]],
        "active_job_ids": [job["id"] for job in jobs if job.get("status") in {"queued", "running"}],
    }


@app.get("/api/jobs/compare")
def compare_jobs(left: str, right: str):
    from agent import evidence

    paths = [_job_path(left), _job_path(right)]
    if left == right:
        raise HTTPException(400, "Select two different audits")
    jobs, results = [], []
    for path in paths:
        job, result = _read(path / "job.json"), _read(path / "result.json")
        if not isinstance(job, dict):
            raise HTTPException(404, "Unknown audit")
        if job.get("id") != path.name:
            raise HTTPException(409, "Stored audit metadata does not match its identifier")
        if job.get("status") not in _TERMINAL or not isinstance(result, dict):
            raise HTTPException(409, "Both audits must finish with a stored result before comparison")
        jobs.append(job)
        results.append(result)
    summaries = [_job_summary(job) for job in jobs]
    differences, reasons = [], []
    for side, path, result, job in zip(("Left", "Right"), paths, results, jobs, strict=True):
        if result.get("status") not in _TERMINAL or result.get("status") != job.get("status"):
            reasons.append(f"{side} audit contains an unfinished checkpoint rather than a finalized result")
        try:
            evidence.verify(path / "inputs", result)
            record = result.get("record")
            if result.get("summary") and not isinstance(record, dict):
                raise ValueError("missing measured control identity")
            if isinstance(record, dict) and (record.get("sources") != result.get("sources") or record.get("evidence") != result.get("evidence")):
                raise ValueError("nested measured control identity differs")
        except (OSError, ValueError, TypeError, KeyError):
            reasons.append(f"{side} audit input/control identity could not be verified")
    for field in ("inputs", "sources", "instruments", "environment", "context"):
        values = [summary["evidence"][field] for summary in summaries]
        if values[0] != values[1]:
            differences.append({"field": field, "left": values[0], "right": values[1]})
            reasons.append(f"The {field} metadata differ")
    for field in ("metric", "seeds"):
        if summaries[0][field] != summaries[1][field]:
            differences.append({"field": field, "left": summaries[0][field], "right": summaries[1][field]})
            reasons.append(f"The reported {field} differ")
    if not all(summary["measured"] for summary in summaries):
        reasons.append("One or both audits have no measured control; their assessment states can be reviewed descriptively")
    return {
        "left": summaries[0], "right": summaries[1],
        "comparable": not reasons,
        "reasons": reasons, "differences": differences,
        "interpretation": "Comparability means verified metadata alignment only. This table is descriptive and computes no new statistical test, causal effect or model ranking.",
    }


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    directory = _job_path(job_id)
    job = _read(directory / "job.json")
    if not isinstance(job, dict):
        raise HTTPException(404, "Unknown audit")
    if job.get("id") != job_id:
        raise HTTPException(409, "Stored audit metadata does not match its identifier")
    result = _read(directory / "result.json")
    return {**job, "result": result, **_result_integrity(job, result)}


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    path = _job_path(job_id) / "job.json"
    with _LOCK:
        job = _read(path)
        if job is None:
            raise HTTPException(404, "Unknown audit")
        if job["status"] not in _TERMINAL:
            job.update(cancel_requested=True, updated_at=_now())
            _write(path, job)
    return job


@app.get("/api/jobs/{job_id}/bundle")
def download_bundle(job_id: str):
    from agent import engine

    directory = _job_path(job_id)
    job = get_job(job_id)
    if job["status"] not in {"completed", "inconclusive"}:
        raise HTTPException(409, "Finish the audit before exporting evidence.")
    if not job["result_finalized"] or not job["evidence_verified"]:
        raise HTTPException(409, job["evidence_error"] or "No finalized verified evidence is available")
    result = job["result"]
    if isinstance(result, dict) and not result.get("record"):
        raise HTTPException(409, "No controlled experiment was measured. Download the assessment memo instead.")
    try:
        target = Path(engine.export_bundle(directory / "result.json"))
        if not target.resolve().is_relative_to(directory.resolve()) or not target.is_file():
            raise ValueError("invalid artifact")
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, "This audit cannot be exported with its current evidence identity.") from exc
    return FileResponse(target, filename=f"nulllab-{job_id}.zip", media_type="application/zip")


@app.get("/api/jobs/{job_id}/assessment")
def download_assessment(job_id: str):
    from agent import engine

    directory = _job_path(job_id)
    job = get_job(job_id)
    if job.get("status") not in _TERMINAL:
        raise HTTPException(409, "Finish the audit before exporting its assessment")
    if not job["result_finalized"] or not job["evidence_verified"]:
        raise HTTPException(409, job["evidence_error"] or "No finalized verified assessment is available")
    try:
        target = Path(engine.export_assessment(directory / "result.json"))
        if not target.resolve().is_relative_to(directory.resolve()) or not target.is_file():
            raise ValueError("invalid artifact")
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, "This assessment has no verified input identity available for export") from exc
    return FileResponse(target, filename=f"nulllab-assessment-{job_id}.zip", media_type="application/zip")


# The workdesk composes the existing local job/measurement service.
from app.workdesk_api import create_router  # noqa: E402

app.include_router(create_router(sys.modules[__name__]))
