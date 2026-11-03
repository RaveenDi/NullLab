"""Meta Model API adapter (OpenAI-compatible chat completions, stdlib only).
Modes: "mock" (default; deterministic stub, NEVER a model result) | "live" (muse-spark-1.3, gated by bs.py spend check).
The key is read from C:\\dev\\bs\\.env (or env) at call time and is never printed, logged or stored."""
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
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


# ---------------- G7 phase: swappable model, own call log + cap, traces, replay ----------------
# Phase G7 (disguised civil-war case, traces, wonder probe): enabled by env NULLLAB_PHASE=g7. Own call log
# runs_g7/live_calls_g7.jsonl (override: NULLLAB_G7_LOG) and its own cap MAX_G7_CALLS, counted in _calls_made().
# Owner brief: about USD 4.50 for the phase, enforced by the driver's ceiling and bs.py spend check before each call.
G7_LOG = Path(__file__).resolve().parent.parent / "runs_g7" / "live_calls_g7.jsonl"
TRACE_FILE = Path(__file__).resolve().parent.parent / "runs_g7" / "traces.jsonl"
MAX_G7_CALLS = 70
_REPLAY = {"queues": None, "path": None}


# G8 phase (loop hardening re-run of the G7 pair): NULLLAB_PHASE=g8. Own log runs_g8/live_calls_g8.jsonl, cap MAX_G8_CALLS,
# own traces runs_g8/traces.jsonl. Counted in _calls_made(). Override: NULLLAB_G8_LOG.
G8_LOG = Path(__file__).resolve().parent.parent / "runs_g8" / "live_calls_g8.jsonl"
G8_TRACE_FILE = Path(__file__).resolve().parent.parent / "runs_g8" / "traces.jsonl"
MAX_G8_CALLS = 70


def g8_log() -> Path:
    return Path(os.environ.get("NULLLAB_G8_LOG") or G8_LOG)


def g8_phase() -> bool:
    return os.environ.get("NULLLAB_PHASE") == "g8"


def g7_log() -> Path:
    return Path(os.environ.get("NULLLAB_G7_LOG") or G7_LOG)


def trace_file() -> Path:
    return Path(os.environ.get("NULLLAB_TRACES") or (G8_TRACE_FILE if g8_phase() else TRACE_FILE))


def g7_phase() -> bool:
    return os.environ.get("NULLLAB_PHASE") == "g7"


def model_for(role: str = "") -> str:
    """Model name: env NULLLAB_MODEL_<ROLE> (e.g. NULLLAB_MODEL_PLANNER), else NULLLAB_MODEL, else muse-spark-1.3."""
    if role and os.environ.get("NULLLAB_MODEL_" + role.upper()):
        return os.environ["NULLLAB_MODEL_" + role.upper()]
    return os.environ.get("NULLLAB_MODEL") or MODEL


def mode_label(role: str = "", model: str | None = None, suffix: str = "") -> str:
    """Honest mode label built from the model actually used, e.g. 'LIVE muse-spark-1.3 (retry)'."""
    return f"LIVE {model or model_for(role)}" + (f" ({suffix})" if suffix else "")


def prompt_key(system: str, user: str, model: str) -> str:
    return hashlib.sha256(json.dumps([model, system, user], ensure_ascii=False).encode("utf-8")).hexdigest()


def set_replay(path) -> int:
    """Serve replies from recorded traces (zero API calls, no spend). Returns the number of recorded replies loaded.
    A prompt recorded more than once is served in recorded order. path=None turns replay off."""
    if path is None:
        _REPLAY.update(queues=None, path=None)
        return 0
    q, n = {}, 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rec = json.loads(line)
            q.setdefault(rec["key"], []).append(rec["reply"])
            n += 1
    _REPLAY.update(queues=q, path=str(path))
    return n


def replaying() -> bool:
    return _REPLAY["queues"] is not None


def _trace(role, model, system, user, reply, usage, tag, temperature, finish):
    rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "role": role, "tag": tag, "model": model,
           "temperature": temperature, "system": system, "user": user, "reply": reply, "usage": usage,
           "finish_reason": finish, "key": prompt_key(system, user, model),
           "reply_sha256": hashlib.sha256((reply or "").encode("utf-8")).hexdigest()}
    tf = trace_file()
    tf.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, tf.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")  # the API key is never part of a record


def _calls_made() -> int:
    return sum(sum(1 for _ in p.open()) for p in (G5_LOG, SPIKE_LOG, g7_log(), g8_log()) if p.exists())


def _g7_calls() -> int:
    p = g7_log()
    return sum(1 for _ in p.open()) if p.exists() else 0


def live_complete(system: str, user: str, est_usd: float = 0.02, max_tokens: int = MIN_MAX_TOKENS, tag: str = "",
                  role: str = "", model: str | None = None, temperature: float = 0, response_format: dict | None = None) -> str:
    """Backward-compatible wrapper: the reply text only. See live_complete_ex for the usage tokens."""
    return live_complete_ex(system, user, est_usd, max_tokens, tag, role, model, temperature, response_format)[0]


def live_complete_ex(system: str, user: str, est_usd: float = 0.02, max_tokens: int = MIN_MAX_TOKENS, tag: str = "",
                     role: str = "", model: str | None = None, temperature: float = 0, response_format: dict | None = None):
    """Returns (reply text, usage dict; {} when replaying). response_format (OpenAI style, e.g. {"type": "json_schema", ...}) is
    passed through only when given; documented at dev.meta.ai/docs/structured-output but NOT live-tested here (UNVERIFIED).
    One live call. Refuses unless spend check passes and the phase call budget allows; logs spend afterwards.
    In G7 phase (NULLLAB_PHASE=g7) the attempt is counted in the G7 log against MAX_G7_CALLS. Every successful reply
    is appended to the traces file. With set_replay() active, serves the recorded reply and makes no API call."""
    model = model or model_for(role)
    if replaying():
        q = _REPLAY["queues"].get(prompt_key(system, user, model))
        if not q:
            raise LiveNotAllowed(f"replay miss: no recorded reply for this prompt (role={role!r}, model={model}, tag={tag!r})")
        return (q.pop(0) if len(q) > 1 else q[0]), {}
    with _LOCK:
        if g8_phase():
            n8 = sum(1 for _ in g8_log().open()) if g8_log().exists() else 0
            if n8 >= MAX_G8_CALLS:
                raise LiveNotAllowed(f"G8 live call budget ({MAX_G8_CALLS}) exhausted")
        elif g7_phase():
            if _g7_calls() >= MAX_G7_CALLS:
                raise LiveNotAllowed(f"G7 live call budget ({MAX_G7_CALLS}) exhausted")
        elif _calls_made() >= MAX_LIVE_CALLS:
            raise LiveNotAllowed(f"live call budget ({MAX_LIVE_CALLS}) exhausted")
        if not spend_ok(est_usd):
            raise LiveNotAllowed("bs.py spend check refused")
        rec = json.dumps({"model": model, "est_usd": est_usd, "tag": tag, "role": role, "temperature": temperature}) + "\n"
        if g7_phase() or g8_phase():  # count the attempt BEFORE the request (also if it fails)
            plog = g8_log() if g8_phase() else g7_log()
            plog.parent.mkdir(parents=True, exist_ok=True)
            with plog.open("a") as f:
                f.write(rec)
        else:
            CALL_LOG.parent.mkdir(exist_ok=True)
            for log in (CALL_LOG, SPIKE_LOG):
                with log.open("a") as f:
                    f.write(rec)
    max_tokens = max(max_tokens, MIN_MAX_TOKENS)
    payload = {"model": model, "max_tokens": max_tokens, "temperature": temperature, "reasoning_effort": "low",
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if response_format:
        payload["response_format"] = response_format
    body = json.dumps(payload).encode()
    req = urllib.request.Request(BASE_URL + "/chat/completions", data=body, method="POST",
                                 headers={"Authorization": "Bearer " + _key(), "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            data = json.loads(r.read())
    finally:  # log spend even if the request failed mid-way
        with _LOCK:
            subprocess.run([sys.executable, str(BS), "spend", "add", "meta", model, "1", str(est_usd), "nulllab"], capture_output=True)
    usage = data.get("usage") or {}
    finish = data["choices"][0].get("finish_reason")
    usage_log = (g8_log() if g8_phase() else g7_log() if g7_phase() else SPIKE_LOG).with_suffix(".usage.jsonl")
    with _LOCK, usage_log.open("a") as f:
        f.write(json.dumps({"tag": tag, "model": model, "est_usd": est_usd, "usage": usage, "finish_reason": finish}) + "\n")
    content = data["choices"][0]["message"].get("content")
    _trace(role, model, system, user, content or "", usage, tag, temperature, finish)
    if not content:
        raise LiveNotAllowed("live reply had empty content: finish_reason=%s usage=%s" % (finish, data.get("usage")))
    return content, usage


def parse_json(text: str):
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(t[t.find("{"): t.rfind("}") + 1])
