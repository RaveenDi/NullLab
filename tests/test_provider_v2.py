"""Bounded isolated provider/security checks. No inference or real datasets."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import threading
import urllib.error

import pytest

from agent.provider import BudgetExceeded, Provider, ProviderConfig, ProviderError


def reply(text="ok"):
    return {"choices": [{"message": {"content": text}}], "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}}


def config(**kw):
    return ProviderConfig(base_url="http://127.0.0.1:8080/v1", reasoning_effort=None, **kw)


def test_literal_config_and_role_model(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text('MODEL_BASE_URL=http://localhost:8090/v1\nNULLLAB_MODEL=glimmer\nNULLLAB_MODEL_PLANNER=planner\nMODEL_API_KEY="literal$(ignored)"\n=x\n')
    monkeypatch.setenv("NULLLAB_MODEL", "override")
    c = ProviderConfig.from_env(f)
    assert c.model == "override" and c.role_models["planner"] == "planner"
    assert c.api_key == "literal$(ignored)" and c.reasoning_effort is None
    assert "literal" not in repr(c)


def test_remote_requires_https_and_credentials(tmp_path):
    with pytest.raises(ProviderError):
        ProviderConfig(base_url="http://example.com/v1")
    with pytest.raises(ProviderError):
        ProviderConfig(base_url="https://key@example.com/v1")
    p = Provider(ProviderConfig(), tmp_path)
    with pytest.raises(ProviderError, match="MODEL_API_KEY"):
        p.complete("s", "u")
    assert p.ledger()["calls"] == 0


def test_replay_identity_and_exhaustion(tmp_path):
    p = Provider(config(), tmp_path / "live", transport=lambda c, payload: reply())
    assert p.complete("s", "u") == "ok"
    trace = tmp_path / "live" / "provider-traces.jsonl"
    r = Provider(config(), tmp_path / "replay", replay_path=trace)
    assert r.complete("s", "u") == "ok"
    assert r.ledger()["calls"] == 0 and r.ledger()["replayed_calls"] == 1
    with pytest.raises(ProviderError, match="exhausted"):
        r.complete("s", "u")
    with pytest.raises(ProviderError):
        r.complete("s", "changed")


def test_failed_call_is_durable_and_not_free(tmp_path):
    def fail(c, payload):
        raise TimeoutError("sensitive provider body")
    c = ProviderConfig(api_key="test-key")
    p = Provider(c, tmp_path, max_calls=1, transport=fail)
    with pytest.raises(ProviderError) as caught:
        p.complete("s", "u")
    assert "sensitive" not in str(caught.value)
    led = p.ledger()
    assert led["calls"] == 1 and led["est_usd"] > 0
    assert led["detail"][0]["billing"] == "unknown"
    with pytest.raises(BudgetExceeded):
        Provider(c, tmp_path, max_calls=1, transport=fail).complete("s", "u")
    assert "test-key" not in (tmp_path / "provider-ledger.json").read_text()


def test_shared_job_budget_and_independent_instances(tmp_path):
    sent = []
    def fake(c, payload):
        sent.append(payload["model"])
        return reply()
    a = Provider(config(model="a"), tmp_path / "shared", max_calls=1, transport=fake)
    b = Provider(config(model="b"), tmp_path / "shared", max_calls=1, transport=fake)
    def call(p):
        try:
            return p.complete("s", "u")
        except BudgetExceeded:
            return "blocked"
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(call, [a, b])) == ["blocked", "ok"]
    assert len(sent) == 1
    other = Provider(config(model="other"), tmp_path / "other", transport=fake)
    assert other.complete("s", "u") == "ok" and sent[-1] == "other"
    assert a.ledger()["usage"]["total_tokens"] == 15


def test_deadline_preserves_unknown_reservation_without_retry(tmp_path):
    release = threading.Event()
    entered = []
    def fake(c, payload):
        entered.append(True)
        release.wait(1)
        return reply()
    p = Provider(config(timeout_s=0.02, retries=3), tmp_path, transport=fake)
    try:
        with pytest.raises(ProviderError, match="billing unknown"):
            p.complete("s", "u")
        assert len(entered) == 1 and p.ledger()["detail"][0]["status"] == "timeout"
    finally:
        release.set()


def test_http_retry_counts_every_attempt(tmp_path):
    calls = []
    def fake(c, payload):
        calls.append(True)
        if len(calls) == 1:
            raise urllib.error.HTTPError(c.base_url, 429, "limited", {}, None)
        assert payload["model"] == "critic"
        return reply()
    c = ProviderConfig(base_url="http://localhost:8080/v1", role_models={"referee": "critic"}, reasoning_effort=None)
    p = Provider(c, tmp_path, max_calls=2, transport=fake)
    assert p.complete("s", "u", role="referee") == "ok"
    assert p.ledger()["calls"] == 2
    assert [r["status"] for r in p.ledger()["detail"]] == ["failed", "completed"]


def test_sandbox_dependencies_readonly_and_workspace_mutable(tmp_path):
    # A fake installation prefix gives us a safe target. Never write to real Python.
    work, prefix = tmp_path / "work", tmp_path / "prefix"
    work.mkdir()
    prefix.mkdir()
    target = prefix / "sentinel.txt"
    target.write_text("keep")
    run = Path(__file__).resolve().parents[1] / "sandbox" / "run.py"
    code = f'''
import importlib.util, json, os, sys
s=importlib.util.spec_from_file_location("sandbox_run", {str(run)!r})
m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
sys.prefix={str(prefix)!r}
m._block_network()
results=[]
assert open({str(target)!r}).read()=="keep"
for action in (lambda: open({str(target)!r}, "w"), lambda: os.remove({str(target)!r})):
    try: action(); results.append(False)
    except PermissionError: results.append(True)
open("local.txt","w").write("ok")
os.remove("local.txt")
print(json.dumps(results))
'''
    p = subprocess.run([sys.executable, "-I", "-c", code], check=False, cwd=work, capture_output=True, text=True, timeout=10)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout) == [True, True]
    assert target.read_text() == "keep"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object failure")
def test_missing_resource_controls_fail_closed(monkeypatch):
    from sandbox import limits
    monkeypatch.setattr(limits, "_make_job", lambda *a: (_ for _ in ()).throw(OSError("unavailable")))
    monkeypatch.delenv("NULLLAB_SANDBOX_REQUIRE_LIMITS", raising=False)
    with pytest.raises(OSError, match="unavailable"):
        limits.run_limited([sys.executable, "-c", "print('must not launch')"])
