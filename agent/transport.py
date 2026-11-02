"""Robust chat-completions transport (G9, EVAL-12 'Robustness'). WRAPS agent/llm.py, which is frozen and NOT edited.

Why: llm.live_complete_ex does urlopen(timeout=300) once. That is a per-socket-read timeout (no total deadline), there is no
retry, and a TimeoutError becomes OSError -> 'api_error' recorded as the case outcome (G8 r1 leaky died this way with no reply
ever observed). This module is a drop-in replacement for llm.live_complete_ex / llm.live_complete with the same signature and
the same spend-gate / call-log / usage-log / trace semantics (it imports and reuses the llm helpers), plus:

  * a TOTAL wall-clock deadline for one logical call and a HARD per-attempt deadline (the request runs in a daemon worker thread
    that the caller stops waiting for, so even a socket that trickles bytes forever cannot block the pipeline);
  * optional streaming (stream=True / NULLLAB_TRANSPORT_STREAM=1): the socket timeout then acts as an IDLE timeout between chunks, which suits
    a reasoning model that is silent for a long time before and during its reply. UNVERIFIED against api.meta.ai (not live-tested);
  * up to 2 retries with exponential backoff on timeout / connection reset / truncated body or stream / HTTP 5xx / HTTP 429
    (Retry-After honoured, capped). Other 4xx are not retried;
  * transport retries are logged SEPARATELY (<phase log>.transport.jsonl) and are NOT model repairs: no factorial_g8 repair budget
    is touched. Why this selects nothing: a call for which no reply was received yields no sample, so re-asking draws the
    first observed sample; a reply that WAS received is never re-rolled (empty content is a model outcome, same as llm.py);
  * idempotent resume: a transport failure writes no trace and no usage record; the exception is a TransportError (an OSError, so
    factorial_g8 files it as harness failure 'api_error', and only after the retries are exhausted). forget_transport_failures() removes such
    records from a run file so the next `run` stage re-runs the case (factorial_g8.run skips cases that have a record).

Use: `from agent import transport; transport.install()` in a NEW driver process (G9). Never call install() in the live G8 process:
it rebinds llm.live_complete_ex / llm.live_complete. The key is read by llm._key() at call time and is never printed or logged."""
import json
import queue
import threading
import time
import urllib.error
import urllib.request

from agent import llm

DEFAULTS = {
    "retries": 2,              # extra attempts after the first (3 attempts in all)
    "read_timeout": 300.0,     # socket timeout (per read; with stream=True this is the idle time between chunks)
    "attempt_deadline": 420.0, # hard wall-clock cap of one attempt, even if bytes keep trickling
    "total_deadline": 1500.0,  # hard wall-clock cap of the whole logical call, all attempts and backoffs included
    "backoff_base": 4.0,       # sleep before retry k: base * 3**(k-1) -> 4 s, 12 s
    "backoff_cap": 60.0,
    "stream": False,
}
RETRY_STATUS = (429, 500, 502, 503, 504)


class TransportError(OSError):
    """No usable reply after all attempts. An OSError on purpose: factorial_g8 files OSError as harness failure 'api_error'."""

    def __init__(self, kind, detail="", attempts=0):
        super().__init__(f"{kind}: {detail}"[:500])
        self.kind, self.detail, self.attempts = kind, detail, attempts


class _Retryable(Exception):
    def __init__(self, kind, detail="", maybe_billed=False, retry_after=None):
        super().__init__(detail)
        self.kind, self.detail, self.maybe_billed, self.retry_after = kind, detail, maybe_billed, retry_after


_LOCAL = threading.local()
_open = urllib.request.urlopen        # swapped by tests: callable(req, timeout=...) -> response with .read()/iteration/.close()
_sleep = time.sleep                   # swapped by tests
_clock = time.monotonic


def last_info() -> dict:
    """Transport info of the last call made on THIS thread: {'attempts': n, 'retries': [...]}."""
    return dict(getattr(_LOCAL, "info", {}) or {})


def transport_log():
    return llm.g8_log().with_suffix(".transport.jsonl") if llm.g8_phase() else \
        (llm.g7_log() if llm.g7_phase() else llm.SPIKE_LOG).with_suffix(".transport.jsonl")


def _spend_add(model, est_usd):
    import subprocess
    import sys
    subprocess.run([sys.executable, str(llm.BS), "spend", "add", "meta", model, "1", str(est_usd), "nulllab"], capture_output=True)


def _log_transport(rec):
    p = transport_log()
    p.parent.mkdir(parents=True, exist_ok=True)
    with llm._LOCK, p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")  # no key, no prompt text: only what is needed to audit the retries


# ---------------- one HTTP attempt (runs in a daemon worker) ----------------
def _http_once(body, headers, read_timeout, stream, holder):
    req = urllib.request.Request(llm.BASE_URL + "/chat/completions", data=body, method="POST", headers=headers)
    try:
        r = _open(req, timeout=read_timeout)
    except urllib.error.HTTPError as e:
        ra = None
        try:
            ra = float(e.headers.get("Retry-After")) if e.headers and e.headers.get("Retry-After") else None
        except (TypeError, ValueError):
            ra = None
        if e.code in RETRY_STATUS:
            raise _Retryable(f"http_{e.code}", f"HTTP {e.code}", maybe_billed=False, retry_after=ra)
        raise TransportError(f"http_{e.code}", f"HTTP {e.code} (not retried)")
    except (TimeoutError, ConnectionError, urllib.error.URLError, OSError) as e:  # connect/handshake problems
        raise _Retryable("connect_error", repr(e)[:200], maybe_billed=False)
    holder["resp"] = r
    try:
        if not stream:
            try:
                raw = r.read()
            except (TimeoutError, ConnectionError, OSError) as e:  # includes http.client.IncompleteRead (an HTTPException is wrapped below)
                raise _Retryable("read_timeout" if isinstance(e, TimeoutError) else "read_error", repr(e)[:200], maybe_billed=True)
            try:
                return json.loads(raw)
            except ValueError as e:
                raise _Retryable("truncated_body", f"body not JSON ({len(raw)} bytes): {e}"[:200], maybe_billed=True)
        return _read_stream(r)
    except _Retryable:
        raise
    except Exception as e:  # noqa: BLE001  (http.client.IncompleteRead etc.)
        raise _Retryable("read_error", repr(e)[:200], maybe_billed=True)
    finally:
        try:
            r.close()
        except Exception:  # noqa: BLE001
            pass


def _read_stream(r):
    """Assemble an OpenAI-style SSE stream into a non-stream style response dict. A stream that ends without [DONE] or a finish_reason is partial."""
    parts, finish, usage, done = [], None, {}, False
    for line in r:
        line = line.decode("utf-8", "replace").strip() if isinstance(line, (bytes, bytearray)) else str(line).strip()
        if not line or line.startswith(":") or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            done = True
            break
        try:
            ch = json.loads(payload)
        except ValueError:
            raise _Retryable("partial_stream", "unparseable stream chunk", maybe_billed=True)
        if isinstance(ch, dict) and ch.get("error"):
            raise _Retryable("stream_error", str(ch["error"])[:200], maybe_billed=True)
        for c in (ch.get("choices") or []):
            d = c.get("delta") or {}
            if d.get("content"):
                parts.append(d["content"])
            if c.get("finish_reason"):
                finish = c["finish_reason"]
        if ch.get("usage"):
            usage = ch["usage"]
    if not (done or finish):
        raise _Retryable("partial_stream", f"stream ended early after {sum(map(len, parts))} chars", maybe_billed=True)
    return {"choices": [{"message": {"content": "".join(parts)}, "finish_reason": finish}], "usage": usage}


def _attempt(body, headers, read_timeout, stream, hard):
    """Run one attempt in a daemon thread and give up waiting after `hard` seconds (the abandoned worker is closed best-effort)."""
    out, holder = queue.Queue(), {}

    def work():
        try:
            out.put(("ok", _http_once(body, headers, read_timeout, stream, holder)))
        except BaseException as e:  # noqa: BLE001
            out.put(("err", e))
    threading.Thread(target=work, daemon=True, name="nulllab-transport").start()
    try:
        kind, val = out.get(timeout=max(hard, 0.01))
    except queue.Empty:
        r = holder.get("resp")
        if r is not None:
            try:
                r.close()
            except Exception:  # noqa: BLE001
                pass
        raise _Retryable("hard_deadline", f"no complete reply within {hard:.0f}s", maybe_billed=True)
    if kind == "err":
        if isinstance(val, (_Retryable, TransportError)):
            raise val
        raise _Retryable("connect_error", repr(val)[:200], maybe_billed=False)  # e.g. http.client.BadStatusLine
    return val


def will_retry_probe(err, attempt, cfg, t0):
    return attempt <= cfg["retries"] and err.kind != "total_deadline" and (cfg["total_deadline"] - (_clock() - t0)) > 0


# ---------------- the drop-in call ----------------
def complete_ex(system, user, est_usd=0.02, max_tokens=llm.MIN_MAX_TOKENS, tag="", role="", model=None, temperature=0,
                response_format=None, *, retries=None, read_timeout=None, attempt_deadline=None, total_deadline=None, stream=None):
    """Same contract as llm.live_complete_ex: returns (reply text, usage dict). Raises llm.LiveNotAllowed (gate/cap/empty content)
    or TransportError (OSError) once the retries are exhausted. See the module docstring."""
    import os
    cfg = dict(DEFAULTS)
    cfg["stream"] = os.environ.get("NULLLAB_TRANSPORT_STREAM") == "1" if stream is None else stream
    for k, v in (("retries", retries), ("read_timeout", read_timeout), ("attempt_deadline", attempt_deadline), ("total_deadline", total_deadline)):
        if v is not None:
            cfg[k] = v
    model = model or llm.model_for(role)
    if llm.replaying():
        return llm.live_complete_ex(system, user, est_usd, max_tokens, tag, role, model, temperature, response_format)
    with llm._LOCK:  # identical gate to llm.live_complete_ex: cap, then spend check, then count the attempt BEFORE the request
        if llm.g8_phase():
            n8 = sum(1 for _ in llm.g8_log().open()) if llm.g8_log().exists() else 0
            if n8 >= llm.MAX_G8_CALLS:
                raise llm.LiveNotAllowed(f"G8 live call budget ({llm.MAX_G8_CALLS}) exhausted")
        elif llm.g7_phase():
            if llm._g7_calls() >= llm.MAX_G7_CALLS:
                raise llm.LiveNotAllowed(f"G7 live call budget ({llm.MAX_G7_CALLS}) exhausted")
        elif llm._calls_made() >= llm.MAX_LIVE_CALLS:
            raise llm.LiveNotAllowed(f"live call budget ({llm.MAX_LIVE_CALLS}) exhausted")
        if not llm.spend_ok(est_usd):
            raise llm.LiveNotAllowed("bs.py spend check refused")
        rec = json.dumps({"model": model, "est_usd": est_usd, "tag": tag, "role": role, "temperature": temperature}) + "\n"
        if llm.g7_phase() or llm.g8_phase():
            plog = llm.g8_log() if llm.g8_phase() else llm.g7_log()
            plog.parent.mkdir(parents=True, exist_ok=True)
            with plog.open("a") as f:
                f.write(rec)
        else:
            llm.CALL_LOG.parent.mkdir(exist_ok=True)
            for log in (llm.CALL_LOG, llm.SPIKE_LOG):
                with log.open("a") as f:
                    f.write(rec)
    payload = {"model": model, "max_tokens": max(max_tokens, llm.MIN_MAX_TOKENS), "temperature": temperature, "reasoning_effort": "low",
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if response_format:
        payload["response_format"] = response_format
    if cfg["stream"]:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}
    body = json.dumps(payload).encode()
    headers = {"Authorization": "Bearer " + llm._key(), "Content-Type": "application/json"}
    t0, retry_log, data, attempt = _clock(), [], None, 0
    _LOCAL.info = {"attempts": 0, "retries": retry_log}
    charged = 0
    while True:
        attempt += 1
        _LOCAL.info["attempts"] = attempt
        remaining = cfg["total_deadline"] - (_clock() - t0)
        err = None
        try:
            if remaining <= 0:
                raise _Retryable("total_deadline", f"total deadline {cfg['total_deadline']:.0f}s used up", maybe_billed=False)
            data = _attempt(body, headers, cfg["read_timeout"], cfg["stream"], min(cfg["attempt_deadline"], remaining))
        except _Retryable as e:
            err = e
        except TransportError as e:
            err = e
        # spend: charged like llm.py (an attempt is always estimated, also if it failed), but once per attempt that may have been billed
        # (success, timeout, truncated body/stream); a 429/5xx answered up front is not billed
        if err is None or getattr(err, "maybe_billed", False):
            _spend_add(model, est_usd)
            charged += 1
        if err is None:
            break
        if charged == 0 and not (isinstance(err, _Retryable) and will_retry_probe(err, attempt, cfg, t0)):
            _spend_add(model, est_usd)  # a failed call is still estimated once, as llm.py does
            charged = 1
        if isinstance(err, TransportError):  # non-retryable 4xx
            _log_transport({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tag": tag, "role": role, "model": model, "attempt": attempt,
                            "kind": err.kind, "detail": err.detail, "will_retry": False, "final": True})
            raise err
        will_retry = will_retry_probe(err, attempt, cfg, t0)
        rec = {"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tag": tag, "role": role, "model": model, "attempt": attempt,
               "kind": err.kind, "detail": err.detail, "elapsed_s": round(_clock() - t0, 1), "will_retry": will_retry,
               "counted_as_model_repair": False}
        retry_log.append(rec)
        _log_transport(rec)
        if not will_retry:
            raise TransportError(err.kind, f"{err.detail}; {attempt} attempt(s) made, retries exhausted", attempts=attempt)
        delay = min(cfg["backoff_cap"], err.retry_after if err.retry_after is not None else cfg["backoff_base"] * 3 ** (attempt - 1))
        delay = max(0.0, min(delay, cfg["total_deadline"] - (_clock() - t0)))
        _sleep(delay)
        with llm._LOCK:
            ok = llm.spend_ok(est_usd)  # the gate is re-checked before every retry
        if not ok:
            raise llm.LiveNotAllowed("bs.py spend check refused (before a transport retry)")
    # ---- a reply was received: from here on identical to llm.live_complete_ex ----
    usage = data.get("usage") or {}
    finish = data["choices"][0].get("finish_reason")
    usage_log = (llm.g8_log() if llm.g8_phase() else llm.g7_log() if llm.g7_phase() else llm.SPIKE_LOG).with_suffix(".usage.jsonl")
    with llm._LOCK, usage_log.open("a") as f:
        f.write(json.dumps({"tag": tag, "model": model, "est_usd": est_usd, "usage": usage, "finish_reason": finish,
                            "transport_attempts": attempt}) + "\n")
    content = data["choices"][0]["message"].get("content")
    llm._trace(role, model, system, user, content or "", usage, tag, temperature, finish)
    if not content:
        raise llm.LiveNotAllowed("live reply had empty content: finish_reason=%s usage=%s" % (finish, data.get("usage")))
    return content, usage


def complete(system, user, est_usd=0.02, max_tokens=llm.MIN_MAX_TOKENS, tag="", role="", model=None, temperature=0, response_format=None):
    return complete_ex(system, user, est_usd, max_tokens, tag, role, model, temperature, response_format)[0]


_ORIG = {}


def install():
    """Rebind llm.live_complete_ex / llm.live_complete to this transport (process-wide; for NEW drivers only, never the live G8 process)."""
    if not _ORIG:
        _ORIG.update(ex=llm.live_complete_ex, plain=llm.live_complete)
    llm.live_complete_ex, llm.live_complete = complete_ex, complete


def uninstall():
    if _ORIG:
        llm.live_complete_ex, llm.live_complete = _ORIG["ex"], _ORIG["plain"]
        _ORIG.clear()


# ---------------- idempotent resume ----------------
def is_transport_failure(rec) -> bool:
    """A case record that only exists because no reply could be obtained (harness api_error from a TransportError / OSError)."""
    if not isinstance(rec, dict) or rec.get("harness_failure") != "api_error":
        return False
    txt = " ".join(map(str, rec.get("reason") or []))
    return any(k in txt for k in ("TransportError", "TimeoutError", "ConnectionError", "URLError", "OSError", "timed out"))


def forget_transport_failures(run_json_path, write=True):
    """Drop transport-failure loop records (and failed B3 records) from a r<k>.json so factorial_g8.run re-runs those cases. Returns the list removed.
    Safe because no reply was ever observed for them: re-running selects nothing. Model-verdict records are never touched."""
    from pathlib import Path
    p = Path(run_json_path)
    d = json.loads(p.read_text(encoding="utf-8"))
    removed = []
    for c in list(d.get("loop", {})):
        if is_transport_failure(d["loop"][c]):
            removed.append(c)
            del d["loop"][c]
    if write and removed:
        p.write_text(json.dumps(d, indent=1), encoding="utf-8")
    return removed
