"""G7 tests: swappable model, mode label, call log + cap, traces, zero-call replay, planner schema + one schema retry.
Offline: the HTTP layer, the spend check and the key are mocked; everything is written to pytest temp dirs."""
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import factorial_g7 as g7  # noqa: E402
from agent import llm  # noqa: E402

SECRET = "sk-test-SECRET-do-not-leak"


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def api(tmp_path, monkeypatch):
    """Mock the Meta API: records request bodies, returns a canned chat completion."""
    calls = []

    def fake_urlopen(req, timeout=0):
        body = json.loads(req.data)
        calls.append(body)
        reply = {"choices": [{"message": {"content": json.dumps({"echo": body["model"], "n": len(calls)})}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 11, "completion_tokens": 7}}
        return FakeResp(json.dumps(reply).encode())

    class FakeRun:
        returncode, stdout = 0, "ok"

    monkeypatch.setattr(llm.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(llm, "spend_ok", lambda est: True)
    monkeypatch.setattr(llm.subprocess, "run", lambda *a, **k: FakeRun())
    monkeypatch.setattr(llm, "_key", lambda: SECRET)
    monkeypatch.setenv("NULLLAB_PHASE", "g7")
    monkeypatch.setenv("NULLLAB_G7_LOG", str(tmp_path / "calls.jsonl"))
    monkeypatch.setenv("NULLLAB_TRACES", str(tmp_path / "traces.jsonl"))
    monkeypatch.setenv("NULLLAB_G7_OUT", str(tmp_path / "out"))
    for k in ("NULLLAB_MODEL", "NULLLAB_MODEL_PLANNER", "NULLLAB_MODEL_B3"):
        monkeypatch.delenv(k, raising=False)
    yield calls
    llm.set_replay(None)


def test_default_model_and_label(api):
    assert llm.model_for() == "muse-spark-1.3"
    assert llm.mode_label("planner") == "LIVE muse-spark-1.3"
    llm.live_complete("s", "u", role="planner")
    assert api[0]["model"] == "muse-spark-1.3"
    assert api[0]["temperature"] == 0 and api[0]["max_tokens"] >= 12000 and api[0]["reasoning_effort"] == "low"


def test_env_model_and_per_role_override(api, monkeypatch):
    monkeypatch.setenv("NULLLAB_MODEL", "muse-x-1")
    monkeypatch.setenv("NULLLAB_MODEL_PLANNER", "muse-wonder-1.0")
    assert llm.model_for() == "muse-x-1" and llm.model_for("b3") == "muse-x-1"
    assert llm.model_for("planner") == "muse-wonder-1.0"
    assert llm.mode_label("planner", suffix="retry") == "LIVE muse-wonder-1.0 (retry)"
    llm.live_complete("s", "u", role="planner")
    llm.live_complete("s", "u", role="b3")
    llm.live_complete("s", "u", role="b3", model="explicit-m", temperature=0.7)
    assert [c["model"] for c in api] == ["muse-wonder-1.0", "muse-x-1", "explicit-m"]
    assert api[2]["temperature"] == 0.7


def test_trace_record_complete_and_no_key(api, tmp_path):
    out = llm.live_complete("SYS", "USER", tag="t1", role="planner", temperature=0.7)
    recs = [json.loads(l) for l in (tmp_path / "traces.jsonl").read_text().splitlines()]
    assert len(recs) == 1
    r = recs[0]
    for k in ("role", "model", "system", "user", "reply", "usage", "key", "reply_sha256", "tag", "temperature", "finish_reason"):
        assert k in r
    assert (r["role"], r["model"], r["system"], r["user"], r["reply"]) == ("planner", "muse-spark-1.3", "SYS", "USER", out)
    assert r["usage"] == {"prompt_tokens": 11, "completion_tokens": 7}
    import hashlib
    assert r["reply_sha256"] == hashlib.sha256(out.encode()).hexdigest()
    for f in (tmp_path / "traces.jsonl", tmp_path / "calls.jsonl"):
        assert SECRET not in f.read_text()


def test_g7_call_log_counted_and_capped(api, tmp_path, monkeypatch):
    llm.live_complete("s", "u")
    llm.live_complete("s", "u2")
    assert llm._g7_calls() == 2
    assert llm._calls_made() >= 2  # the G7 log is part of the phase total
    assert len((tmp_path / "calls.jsonl").read_text().splitlines()) == 2
    monkeypatch.setattr(llm, "MAX_G7_CALLS", 2)
    with pytest.raises(llm.LiveNotAllowed):
        llm.live_complete("s", "u3")
    assert len(api) == 2  # the refused call never reached the API


def test_spend_check_failure_stops_call(api, monkeypatch):
    monkeypatch.setattr(llm, "spend_ok", lambda est: False)
    with pytest.raises(llm.LiveNotAllowed):
        llm.live_complete("s", "u")
    assert api == []


def test_replay_serves_traces_with_zero_api_calls(api, tmp_path, monkeypatch):
    a = llm.live_complete("S", "U1", role="planner")
    b = llm.live_complete("S", "U2", role="planner")
    assert len(api) == 2
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(AssertionError("API called in replay")))
    monkeypatch.setattr(llm, "spend_ok", lambda est: (_ for _ in ()).throw(AssertionError("spend check in replay")))
    assert llm.set_replay(tmp_path / "traces.jsonl") == 2
    assert llm.replaying()
    assert llm.live_complete("S", "U2", role="planner") == b
    assert llm.live_complete("S", "U1", role="planner") == a
    with pytest.raises(llm.LiveNotAllowed, match="replay miss"):
        llm.live_complete("S", "never recorded")
    assert llm._g7_calls() == 2  # replay adds nothing to the call log


def test_replay_is_model_specific(api, tmp_path, monkeypatch):
    llm.live_complete("S", "U", model="m1")
    llm.set_replay(tmp_path / "traces.jsonl")
    llm.live_complete("S", "U", model="m1")
    with pytest.raises(llm.LiveNotAllowed):
        llm.live_complete("S", "U", model="m2")


def test_cli_replay_requires_out_dir():
    with pytest.raises(SystemExit):
        g7.main(["--replay", "x.jsonl", "spark5"])


# ---------------- planner schema ----------------
GOOD = {"A": "a", "B": "b", "A_code_line": "x", "B_code_line": "y", "reason": "r",
        "edits": {"A": {"kind": "split", "steps": {"f": "def f(): pass"}}, "B": {"kind": "fit_scope", "steps": {"g": "def g(): pass"}}},
        "predicted_drop_pp": {"fix_A": 1, "fix_B": 2.5, "fix_both": 3}, "culprit_ranking": ["A", "AxB"]}


def test_validate_plan_accepts_good_and_saved_plans():
    assert g7.validate_plan(GOOD) == []
    d = json.loads((ROOT / "runs_g6" / "r1.json").read_text(encoding="utf-8"))
    for c, rec in d["plan"].items():
        assert g7.validate_plan(rec["plan"]) == [], c


@pytest.mark.parametrize("mut", [
    lambda p: p.pop("edits"),
    lambda p: p["edits"]["A"].update(kind="rewrite"),
    lambda p: p["edits"]["B"].update(steps={}),
    lambda p: p["edits"]["B"].update(steps={"g": 7}),
    lambda p: p.update(predicted_drop_pp={"fix_A": 1}),
    lambda p: p["predicted_drop_pp"].update(fix_both="3"),
    lambda p: p.update(culprit_ranking=["C"]),
    lambda p: p.update(A=""),
    lambda p: p["edits"].update(both_overrides=["x"]),
])
def test_validate_plan_rejects_malformed(mut):
    p = json.loads(json.dumps(GOOD))
    mut(p)
    assert g7.validate_plan(p)
    assert g7.validate_plan("not a dict")


CASE = ROOT / "corpus" / "clean_control"


def _stub_replies(monkeypatch, replies):
    seen = []

    def fake(system, user, **kw):
        seen.append((kw.get("tag"), kw.get("role"), kw.get("model"), kw.get("temperature"), user))
        return replies[len(seen) - 1]
    monkeypatch.setattr(llm, "live_complete", fake)
    monkeypatch.setattr(g7, "budget_ok", lambda *a, **k: True)
    return seen


@pytest.mark.skipif(not (CASE / "data.csv").exists(), reason="corpus case missing")
def test_schema_invalid_then_valid_uses_one_retry(monkeypatch):
    seen = _stub_replies(monkeypatch, [json.dumps({"A": "only"}), json.dumps(GOOD)])
    p, raw, info = g7.plan(CASE, "rid", model="m-test", temperature=0.7)
    assert info["schema_valid_first"] is False and info["schema_retry"] is True
    assert len(seen) == 2 and "NOT VALID" in seen[1][4]
    assert p["mode"] == "LIVE m-test" and seen[0][2] == "m-test" and seen[0][3] == 0.7
    assert g7.validate_plan(p) == []


@pytest.mark.skipif(not (CASE / "data.csv").exists(), reason="corpus case missing")
def test_schema_invalid_twice_raises_and_valid_first_uses_one_call(monkeypatch):
    _stub_replies(monkeypatch, ["not json at all", json.dumps({"A": "x"})])
    with pytest.raises(g7.PlanInvalid):
        g7.plan(CASE, "rid")
    seen = _stub_replies(monkeypatch, [json.dumps(GOOD)])
    _, _, info = g7.plan(CASE, "rid")
    assert len(seen) == 1 and info["schema_retry"] is False


@pytest.mark.skipif(not (CASE / "data.csv").exists(), reason="corpus case missing")
def test_schema_checked_before_fidelity_guard(monkeypatch, tmp_path):
    """loop_case never reaches the guard / sandbox with a schema-invalid retry reply."""
    _stub_replies(monkeypatch, [json.dumps({"A": "x"}), json.dumps({"A": "x"})])
    bad_plan = json.loads(json.dumps(GOOD))
    bad_plan["edits"]["A"]["steps"] = {"nonexistent_step": "def nonexistent_step(): pass"}
    monkeypatch.setattr(g7, "_execute", lambda *a: (_ for _ in ()).throw(AssertionError("executed")))
    monkeypatch.setenv("NULLLAB_G7_OUT", str(tmp_path))
    rec = g7.loop_case(CASE, "rid", {"plan": bad_plan}, rules=())
    assert rec["status"] == "INCONCLUSIVE" and rec["retries"] in (0, 1)
