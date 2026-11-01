"""Meta Model API adapter (OpenAI-compatible chat completions, stdlib only).
Modes: "mock" (default; deterministic stub, NEVER a model result) | "live" (muse-spark-1.3, gated by bs.py spend check).
The key is read from C:\\dev\\bs\\.env (or env) at call time and is never printed, logged or stored."""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

BASE_URL = "https://api.meta.ai/v1"
MODEL = "muse-spark-1.3"
ENV_FILE = Path(os.environ.get("NULLLAB_ENV_FILE", r"C:\dev\bs\.env"))
BS = Path(__file__).resolve().parent.parent.parent / "battle-station" / "bs.py"
CALL_LOG = Path(__file__).resolve().parent.parent / "runs" / "live_calls.jsonl"
MAX_LIVE_CALLS = 10


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
    return sum(1 for _ in CALL_LOG.open()) if CALL_LOG.exists() else 0


def live_complete(system: str, user: str, est_usd: float = 0.02, max_tokens: int = 4000) -> str:
    """One live call. Refuses unless spend check passes and call budget (<=10) allows; logs spend afterwards."""
    if _calls_made() >= MAX_LIVE_CALLS:
        raise LiveNotAllowed("live call budget (10) exhausted")
    if not spend_ok(est_usd):
        raise LiveNotAllowed("bs.py spend check refused")
    body = json.dumps({"model": MODEL, "max_tokens": max_tokens, "temperature": 0, "reasoning_effort": "low",
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    CALL_LOG.parent.mkdir(exist_ok=True)
    with CALL_LOG.open("a") as f:
        f.write(json.dumps({"model": MODEL, "est_usd": est_usd}) + "\n")
    subprocess.run([sys.executable, str(BS), "spend", "add", "meta", MODEL, "1", str(est_usd), "nulllab"], capture_output=True)
    content = data["choices"][0]["message"].get("content")
    if not content:
        raise LiveNotAllowed("live reply had empty content: finish_reason=%s usage=%s" % (data["choices"][0].get("finish_reason"), data.get("usage")))
    return content


def parse_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t[t.find("{"): t.rfind("}") + 1])
