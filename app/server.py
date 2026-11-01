"""FastAPI: serves the static verdict pages and can (re)run a case in MOCK mode.  uvicorn app.server:app --port 8099"""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

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


@app.post("/api/run/{case}")
def run_case(case: str):
    if case not in pipeline.cases():
        raise HTTPException(404)
    r = pipeline.run_case(case, mode="mock")  # live mode is CLI-only (spend-gated)
    render.render_all()
    return {"case": case, "mode": r["mode"], "verdict": r["verdict"]}
