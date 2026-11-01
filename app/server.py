"""FastAPI: serves the single-page demo (/) with JSON APIs, per-case verdict pages,
and can (re)run a case in MOCK mode.  uvicorn app.server:app --port 8099
Live mode stays CLI-only (spend-gated): POST /api/run/{case}?mode=live is refused; use pipeline.py --live."""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

import pipeline
from report import render

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="NullLab")


@app.get("/", response_class=HTMLResponse)
def index():
    render.render_all()
    return (ROOT / "report" / "index.html").read_text(encoding="utf-8")


@app.get("/verdict/{case}")
def verdict(case: str):
    p = ROOT / "report" / f"{case}.html"
    if case not in pipeline.cases():
        raise HTTPException(404)
    if not p.exists():
        run_case(case)
    return FileResponse(p)


@app.get("/api/cases")
def api_cases():
    return sorted(pipeline.cases())


@app.get("/api/case/{case}")
def api_case(case: str):
    if case not in pipeline.cases():
        raise HTTPException(404)
    p = ROOT / "runs_live" / f"{case}.json"   # live evidence first, mock run as fallback
    if not p.exists():
        p = ROOT / "runs" / f"{case}.json"
    if not p.exists():
        raise HTTPException(404, f"no run for {case}; POST /api/run/{case} first")
    return JSONResponse(json.loads(p.read_text()))


@app.get("/api/ablation")
def api_ablation():
    p = ROOT / "runs_live" / "ablation.json"
    if not p.exists():
        p = ROOT / "runs" / "ablation.json"
    if not p.exists():
        raise HTTPException(404, "no ablation; run python -m eval.score")
    return JSONResponse(json.loads(p.read_text()))


@app.post("/api/run/{case}")
def run_case(case: str):
    if case not in pipeline.cases():
        raise HTTPException(404)
    r = pipeline.run_case(case, mode="mock")  # live mode is CLI-only (spend-gated)
    render.render_all()
    return {"case": case, "mode": r["mode"], "verdict": r["verdict"]}
