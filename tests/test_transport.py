"""Fault-injection tests for agent/transport.py. No network, no spend: the HTTP opener, the spend gate, the key and sleep are all mocked."""
import io
import json
import threading
import urllib.error
from email.message import Message
from pathlib import Path

import pytest

from agent import factorial_g8 as g8, llm, transport


class Resp:
    def __init__(self, body=b"", lines=None, read_exc=None):
        self.body, self.lines, self.read_exc, self.closed = body, lines, read_exc, False

    def read(self):
        if self.read_exc:
            raise self.read_exc
        return self.body

    def __iter__(self):
        for ln in self.lines or []:
            if isinstance(ln, Exception):
                raise ln
            yield ln

    def close(self):
        self.closed = True


def ok_body(text="hello", usage=None):
    return json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": usage or {"total_tokens": 7}}).encode()


def http_error(code, retry_after=None):
    h = Message()
    if retry_after is not None:
        h["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("https://x", code, "err", h, io.BytesIO(b""))


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLLAB_PHASE", "g8")
    monkeypatch.setenv("NULLLAB_G8_LOG", str(tmp_path / "live_calls_g8.jsonl"))
    monkeypatch.setenv("NULLLAB_TRACES", str(tmp_path / "traces.jsonl"))
    monkeypatch.delenv("NULLLAB_TRANSPORT_STREAM", raising=False)
    monkeypatch.setattr(llm, "spend_ok", lambda est: True)
    monkeypatch.setattr(llm, "_key", lambda: "test-key-not-real")
    spent, sleeps = [], []
    monkeypatch.setattr(transport, "_spend_add", lambda model, est: spent.append(est))
    monkeypatch.setattr(transport, "_sleep", lambda d: sleeps.append(d))

    class E:
        pass
    e = E()
    e.tmp, e.spent, e.sleeps = tmp_path, spent, sleeps

    def script(*steps):
        """steps: Resp | Exception | callable(req, timeout) ; consumed in order, one per HTTP attempt."""
        it, calls = iter(steps), []

        def opener(req, timeout=None):
            calls.append((req, timeout))
            s = next(it)
            if callable(s):
                return s(req, timeout)
            if isinstance(s, Exception):
                raise s
            return s
        monkeypatch.setattr(transport, "_open", opener)
        return calls
    e.script = script
    e.log = lambda name: [json.loads(x) for x in (tmp_path / name).read_text().splitlines()] if (tmp_path / name).exists() else []
    return e


def call(**kw):
    kw.setdefault("backoff_base", None)
    kw.pop("backoff_base")
    return transport.complete_ex("sys", "user", est_usd=0.1, tag="t", role="planner", model="m", temperature=0.7, **kw)


def test_success_first_try_matches_llm_semantics(env):
    calls = env.script(Resp(ok_body("hi")))
    text, usage = call()
    assert (text, usage) == ("hi", {"total_tokens": 7})
    assert len(calls) == 1 and calls[0][1] == transport.DEFAULTS["read_timeout"]
    # call log: one attempt record, same fields as llm.live_complete_ex
    rec = env.log("live_calls_g8.jsonl")
    assert rec == [{"model": "m", "est_usd": 0.1, "tag": "t", "role": "planner", "temperature": 0.7}]
    assert env.log("live_calls_g8.usage.jsonl")[0]["usage"] == {"total_tokens": 7}
    assert env.log("traces.jsonl")[0]["reply"] == "hi"
    assert env.log("live_calls_g8.transport.jsonl") == []
    assert env.spent == [0.1]
    # the key is only in the request header, never in any log
    assert "test-key-not-real" not in "".join(p.read_text() for p in env.tmp.iterdir())
    assert calls[0][0].headers["Authorization"] == "Bearer test-key-not-real"


def test_503_then_success_completes_and_logs_retry_apart(env):
    env.script(http_error(503), Resp(ok_body("done")))
    text, _ = call()
    assert text == "done"
    tl = env.log("live_calls_g8.transport.jsonl")
    assert len(tl) == 1 and tl[0]["kind"] == "http_503" and tl[0]["will_retry"] and tl[0]["counted_as_model_repair"] is False
    assert len(env.log("live_calls_g8.jsonl")) == 1          # a transport retry is NOT a second counted call
    assert len(env.log("traces.jsonl")) == 1                 # only the reply that was observed is traced
    assert env.sleeps == [transport.DEFAULTS["backoff_base"]]
    assert transport.last_info()["attempts"] == 2
    assert env.log("live_calls_g8.usage.jsonl")[0]["transport_attempts"] == 2
    assert env.spent == [0.1]                                # a 503 answered up front is not billed: charged once in all


def test_429_honours_retry_after_and_backs_off_exponentially(env):
    env.script(http_error(429, retry_after=7), http_error(502), Resp(ok_body("ok")))
    assert call()[0] == "ok"
    assert env.sleeps == [7.0, 12.0]                          # Retry-After, then base*3 for the 2nd retry
    assert [r["kind"] for r in env.log("live_calls_g8.transport.jsonl")] == ["http_429", "http_502"]


def test_hang_is_cut_by_the_hard_deadline_and_retried(env):
    release = threading.Event()
    env.script(lambda req, t: (release.wait(30), Resp(ok_body("late")))[1], Resp(ok_body("second")))
    try:
        text, _ = call(attempt_deadline=0.2)
    finally:
        release.set()
    assert text == "second"
    tl = env.log("live_calls_g8.transport.jsonl")
    assert tl[0]["kind"] == "hard_deadline"
    assert env.spent == [0.1, 0.1]                            # the abandoned attempt may have been billed: charged


def test_slow_trickle_cannot_exceed_total_deadline(env):
    """A socket that keeps trickling bytes (so the per-read timeout never fires) is still cut by the wall-clock deadlines."""
    stop = threading.Event()
    env.script(lambda req, t: (stop.wait(30), Resp(b""))[1], lambda req, t: (stop.wait(30), Resp(b""))[1], lambda req, t: (stop.wait(30), Resp(b""))[1])
    import time
    t0 = time.time()
    try:
        with pytest.raises(transport.TransportError) as ei:
            call(attempt_deadline=0.15, total_deadline=0.4)
    finally:
        stop.set()
    assert time.time() - t0 < 5
    assert isinstance(ei.value, OSError)


def test_retries_exhausted_gives_transport_error_and_no_records(env):
    env.script(http_error(503), http_error(503), http_error(503))
    with pytest.raises(transport.TransportError) as ei:
        call()
    assert ei.value.kind == "http_503" and ei.value.attempts == 3 and "retries exhausted" in str(ei.value)
    assert len(env.log("live_calls_g8.transport.jsonl")) == 3
    assert env.log("traces.jsonl") == [] and env.log("live_calls_g8.usage.jsonl") == []   # nothing recorded as a sample
    assert env.spent == [0.1]                                  # the failed call is estimated once, as llm.py does
    assert len(env.sleeps) == 2                                # exactly 2 retries


def test_non_retryable_4xx_fails_at_once(env):
    calls = env.script(http_error(400), Resp(ok_body("never")))
    with pytest.raises(transport.TransportError) as ei:
        call()
    assert ei.value.kind == "http_400" and len(calls) == 1


def test_timeout_on_read_and_truncated_body_are_retried(env):
    env.script(Resp(read_exc=TimeoutError("read timed out")), Resp(body=b'{"choices": [{"mess'), Resp(ok_body("third")))
    assert call()[0] == "third"
    assert [r["kind"] for r in env.log("live_calls_g8.transport.jsonl")] == ["read_timeout", "truncated_body"]
    assert env.spent == [0.1, 0.1, 0.1]                        # both failed attempts may have been billed


def test_connection_error_retried(env):
    env.script(ConnectionResetError("reset"), Resp(ok_body("ok")))
    assert call()[0] == "ok"


def sse(*chunks, done=True):
    out = [b"data: " + json.dumps(c).encode() + b"\n" for c in chunks]
    if done:
        out.append(b"data: [DONE]\n")
    return out


def delta(t, finish=None):
    return {"choices": [{"delta": {"content": t}, "finish_reason": finish}]}


def test_stream_assembles_reply_and_usage(env):
    calls = env.script(Resp(lines=sse(delta("he"), delta("llo", "stop"), {"choices": [], "usage": {"total_tokens": 9}})))
    text, usage = call(stream=True)
    assert text == "hello" and usage == {"total_tokens": 9}
    assert json.loads(calls[0][0].data)["stream"] is True


def test_partial_stream_is_retried_and_completes(env):
    env.script(Resp(lines=sse(delta("par"), done=False)), Resp(lines=sse(delta("full reply", "stop"))))
    text, _ = call(stream=True)
    assert text == "full reply"
    assert env.log("live_calls_g8.transport.jsonl")[0]["kind"] == "partial_stream"
    assert len(env.log("traces.jsonl")) == 1 and env.log("traces.jsonl")[0]["reply"] == "full reply"


def test_stream_connection_cut_mid_stream_retried(env):
    env.script(Resp(lines=[b"data: " + json.dumps(delta("x")).encode() + b"\n", ConnectionResetError("cut")]), Resp(lines=sse(delta("ok", "stop"))))
    assert call(stream=True)[0] == "ok"


def test_empty_content_is_a_model_outcome_not_retried(env):
    calls = env.script(Resp(ok_body("")), Resp(ok_body("never")))
    with pytest.raises(llm.LiveNotAllowed):
        call()
    assert len(calls) == 1 and len(env.log("traces.jsonl")) == 1   # same as llm.py: traced, then raised


def test_spend_gate_and_cap_are_kept(env, monkeypatch):
    env.script(Resp(ok_body("x")))
    monkeypatch.setattr(llm, "spend_ok", lambda est: False)
    with pytest.raises(llm.LiveNotAllowed, match="spend check"):
        call()
    assert env.log("live_calls_g8.jsonl") == []                # refused before anything was counted
    monkeypatch.setattr(llm, "spend_ok", lambda est: True)
    monkeypatch.setattr(llm, "MAX_G8_CALLS", 1)
    call()
    env.script(Resp(ok_body("y")))
    with pytest.raises(llm.LiveNotAllowed, match="budget"):
        call()


def test_gate_rechecked_before_a_retry(env, monkeypatch):
    env.script(http_error(503), Resp(ok_body("never")))
    seq = iter([True, False])
    monkeypatch.setattr(llm, "spend_ok", lambda est: next(seq))
    with pytest.raises(llm.LiveNotAllowed, match="before a transport retry"):
        call()


# ---------------- integration with the frozen G8 state machine (the loop code is not edited) ----------------
def test_install_routes_g8_calls_and_api_error_only_after_retries(env, monkeypatch):
    transport.install()
    try:
        assert llm.live_complete_ex is transport.complete_ex
        bud = g8.CaseBudget()
        env.script(http_error(503), Resp(ok_body('{"a": 1}')))
        assert bud.call("plan", "s", "m", "tag", "mod", 0.7) == '{"a": 1}'
        assert len(bud.calls) == 1                           # one planner-side call, the transport retry is invisible to the budget
        assert bud.used == set()                             # and spent no repair
        env.script(http_error(503), http_error(503), http_error(503))
        with pytest.raises(OSError):                         # factorial_g8.pipeline files OSError as harness failure api_error
            bud.call("guard", "s", "m", "tag", "mod", 0.7)
    finally:
        transport.uninstall()
    assert llm.live_complete_ex is not transport.complete_ex


def test_pipeline_records_api_error_only_after_exhaustion_and_resume_reruns(env, monkeypatch):
    transport.install()
    try:
        env.script(http_error(503), http_error(503), http_error(503))
        case = Path(__file__).resolve().parent.parent / "real" / "civilwar_disguised"
        rec = g8.pipeline(case, "g9-test", model="m", temperature=0.7)
    finally:
        transport.uninstall()
    assert rec["status"] == "INCONCLUSIVE" and rec["harness_failure"] == "api_error"
    assert transport.is_transport_failure(rec)
    run_json = env.tmp / "r1.json"
    run_json.write_text(json.dumps({"loop": {"civilwar_disguised": rec, "other": {"status": "ok"}}, "b3": {}}))
    assert transport.forget_transport_failures(run_json) == ["civilwar_disguised"]
    assert list(json.loads(run_json.read_text())["loop"]) == ["other"]       # the model-verdict record is untouched
    assert env.log("traces.jsonl") == []                                      # a transport failure left no trace of a sample


def test_g8_files_untouched_by_install():
    h = g8.llm.live_complete_ex
    transport.install()
    transport.uninstall()
    assert g8.llm.live_complete_ex is h
