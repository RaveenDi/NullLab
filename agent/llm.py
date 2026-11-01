"""Meta Model API adapter (OpenAI-compatible chat completions, stdlib only).
Modes: "mock" (default; deterministic stub, NEVER a model result) | "live" (muse-spark-1.3, gated by bs.py spend check).
The key is read from C:\\dev\\bs\\.env (or env) at call time and is never printed, logged or stored."""
import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"
ENV_FILE = Path(os.environ.get("NULLLAB_ENV_FILE", r"C:\dev\bs\.env"))
BS = Path(__file__).resolve().parent.parent.parent / "battle-station" / "bs.py"
CALL_LOG = Path(__file__).resolve().parent.parent / "runs" / "live_calls.jsonl"
# Per-phase call log + hard cap. Spike (G2+G3) used runs/live_calls_spike4.jsonl with cap 14 (4 used).
# G4 phase: runs/live_calls_g4.jsonl, cap 70 (43 used).
# G5 phase (patch-fidelity guard + repeats): own log, cap 140 live calls (owner pre-approved up to $12 more Meta spend;
# $30 cap enforced by bs.py spend check; g5.py also stops if projected spend passes the ~$22 ceiling).
# G6 phase (real + textbook cases): own log runs/live_calls_g6.jsonl; the cap of 190 counts G5 + G6 calls together
# (owner brief: raise MAX_LIVE_CALLS to 190 total; at most ~$3.50 more Meta spend, enforced by g6.py's ceiling).
G5_LOG = Path(__file__).resolve().parent.parent / "runs" / "live_calls_g5.jsonl"
SPIKE_LOG = Path(__file__).resolve().parent.parent / "runs" / "live_calls_g6.jsonl"
MAX_LIVE_CALLS = 190
MIN_MAX_TOKENS = 12000  # reasoning model: short budgets returned empty content (STATUS smoke call)


_LOCK = threading.Lock()  # G5 runs calls from a few threads: serialise cap check, spend check, logs and spend add


class LiveNotAllowed(RuntimeError):
    pass


def _key():
    if os.environ.get("MODEL_API_KEY"):
        return os.environ["MODEL_API_KEY"]
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("MODEL_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"')
    raise LiveNotAllowed("MODEL_API_KEY not found")


def spend_ok(est_usd: float) -> bool:
    r = subprocess.run([sys.executable, str(BS), "spend", "check", "meta", str(est_usd)], capture_output=True, text=True)
    return r.returncode == 0 and r.stdout.strip().startswith("ok")


def _calls_made() -> int:
    return sum(sum(1 for _ in p.open()) for p in (G5_LOG, SPIKE_LOG) if p.exists())


def live_complete(system: str, user: str, est_usd: float = 0.02, max_tokens: int = MIN_MAX_TOKENS, tag: str = "") -> str:
    """One live call. Refuses unless spend check passes and the phase call budget (MAX_LIVE_CALLS) allows; logs spend afterwards."""
    with _LOCK:
        if _calls_made() >= MAX_LIVE_CALLS:
            raise LiveNotAllowed(f"live call budget ({MAX_LIVE_CALLS}) exhausted")
        if not spend_ok(est_usd):
            raise LiveNotAllowed("bs.py spend check refused")
        CALL_LOG.parent.mkdir(exist_ok=True)
        for log in (CALL_LOG, SPIKE_LOG):  # count the attempt against the cap BEFORE the request (also if it fails)
            with log.open("a") as f:
                f.write(json.dumps({"model": MODEL, "est_usd": est_usd, "tag": tag}) + "\n")
    max_tokens = max(max_tokens, MIN_MAX_TOKENS)
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens, "temperature": 0, "reasoning_effort": "low",
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read())
    finally:  # log spend even if the request failed mid-way
        with _LOCK:
            subprocess.run([sys.executable, str(BS), "spend", "add", "meta", MODEL, "1", str(est_usd), "nulllab"], capture_output=True)
    usage = data.get("usage") or {}
    with _LOCK, SPIKE_LOG.with_suffix(".usage.jsonl").open("a") as f:
        f.write(json.dumps({"tag": tag, "usage": usage, "finish_reason": data["choices"][0].get("finish_reason")}) + "\n")
    content = data["choices"][0]["message"].get("content")
    if not content:
        raise LiveNotAllowed("live reply had empty content: finish_reason=%s usage=%s" % (data["choices"][0].get("finish_reason"), data.get("usage")))
    return content


def parse_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t[t.find("{"): t.rfind("}") + 1])
