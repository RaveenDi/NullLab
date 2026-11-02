"""G9 runner tests. Offline: no API call, no spend. HTTP opener, spend gate, key, sandbox, guard and smoke are mocked; nothing is written under runs*/."""
import hashlib
import io
import json
import re
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import factorial_g8 as g8, factorial_g9 as g9, llm, transport  # noqa: E402
from agent.factorial import agent_view  # noqa: E402


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("NULLLAB_G9_OUT", "NULLLAB_PHASE", "NULLLAB_G8_OUT", "NULLLAB_G8_LOG", "NULLLAB_TRACES"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("NULLLAB_G9_OUT", str(tmp_path / "g9"))
    monkeypatch.setenv("NULLLAB_MODEL", "muse-spark-1.3-contributor")
    monkeypatch.setattr(llm, "MAX_G8_CALLS", 106)
    monkeypatch.setattr(llm, "spend_ok", lambda est: True)
    monkeypatch.setattr(llm, "_key", lambda: "test-key-not-real")
    monkeypatch.setattr(transport, "_spend_add", lambda m, e: None)
    monkeypatch.setattr(transport, "_sleep", lambda d: None)
    g9.configure()
    yield tmp_path / "g9"
    transport.uninstall()


# ---------------- constants, projection, isolation ----------------
def test_constants_and_caps():
    assert g9.N_CASES == 16 and g9.CASE_CALL_CAP == 5 and g9.PLANNER_CALL_CAP == 90 and g9.TOTAL_CALL_CAP == 106
    assert g9.TEMPERATURE == 0.7 and g9.DEFAULT_MODEL == "muse-spark-1.3-contributor" and g9.CEILING_USD == 12.0
    assert g9.N_CASES * g9.CASE_CALL_CAP <= g9.PLANNER_CALL_CAP
    assert (g9.SEEDS, g9.N_BOOT) == (g8.SEEDS, g8.N_BOOT)
    assert g9.B3_SYSTEM == g8.B3_SYSTEM


def test_projection_within_ceiling(env):
    pj = g9.projected()
    assert pj["within_ceiling"] and pj["within_planner_cap"] and pj["worst_case_usd"] <= 12.0 and pj["max_live_calls_total"] == 96


def test_units():
    assert len(g9.units_for([1, 2, 3, 4, 5])) == 16
    assert {c for r, c in g9.units_for([4, 5])} == {g9.EHG_LEAKY, g9.EHG_CLEAN}


def test_configure_isolated_and_refuses_other_runs(env, monkeypatch):
    assert Path(llm.g8_log()).parent == env and Path(llm.trace_file()).parent == env and llm.MAX_G8_CALLS == 106
    for name in ("runs_g8", "runs_ehg", "runs_g7"):
        monkeypatch.setenv("NULLLAB_G9_OUT", str(ROOT / name))
        with pytest.raises(SystemExit):
            g9.configure()


def test_no_truth_in_agent_views_or_prompts():
    blob = "\n".join(agent_view(d) + g9.user_msg(d, "r") for d in g9.CASES.values()) + g9.SYSTEM + g9.B3_SYSTEM
    for bad in ("0.430", "0.43 ", "+0.43", "0.494", "49.4", "0.36", "SMOTE", "TPEHG", "Vandewiele", "preterm", "g8_truth", "g7_truth",
                "Hegre", "Fearon", "Laitin", "Sambanis", "published"):
        assert bad not in blob, bad


def test_module_respects_agent_invariants():
    t = (ROOT / "agent" / "factorial_g9.py").read_text(encoding="utf-8")
    assert "ground_truth" not in t and not re.search(r"from\s+eval|import\s+eval", t)


def test_frozen_eval12_hashes_match_doc():
    doc = (ROOT / "docs" / "EVAL-12-G9-DSL.md").read_text(encoding="utf-8")
    found = dict(re.findall(r"FROZEN_FILE (\S+) `([0-9a-f]{64})`", doc))
    assert set(found) >= {"agent/edit_dsl.py", "agent/guard_g9.py", "agent/contract_g9.py"}
    acknowledged = {(c["path"], c["old_sha256"], c["new_sha256"])
                    for c in json.loads((ROOT / "docs" / "FROZEN-CHANGELOG.json").read_text(encoding="utf-8"))["changes"]}
    for f in ("agent/edit_dsl.py", "agent/guard_g9.py", "agent/contract_g9.py"):
        now = g9.sha_file(ROOT / f)
        # a post-freeze change passes only if the changelog records exactly this old hash (the one in the frozen doc) and this new hash
        assert now == found[f] or (f, found[f], now) in acknowledged, f
    assert g9.edit_dsl.spec_sha256() == g9.FROZEN_OPSPEC_SHA256 and g9.contract_g9.contract_sha256() == g9.FROZEN_CONTRACT_SHA256


# ---------------- hashing / freeze / verify ----------------
def _freeze_setup(monkeypatch, tmp_path):
    f, doc = tmp_path / "code.py", tmp_path / "doc.md"
    f.write_bytes(b"a = 1\r\n")
    doc.write_text("prereg\n", encoding="utf-8")
    monkeypatch.setattr(g9, "CODE_FILES", (str(f),))
    monkeypatch.setattr(g9, "DOC", str(doc))
    return f, doc


def test_freeze_verify_lf_and_change_detection(monkeypatch, tmp_path, env):
    f, doc = _freeze_setup(monkeypatch, tmp_path)
    g9.freeze()
    recs = [json.loads(x) for x in (env / "prereg_log.jsonl").read_text().splitlines()]
    src = next(r for r in recs if r["kind"] == "g9_source_hashes")
    assert src["payload"][str(f)] == hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert src["sha256"] == hashlib.sha256(json.dumps(src["payload"], sort_keys=True).encode()).hexdigest()
    assert g9.verify_problems() == []
    f.write_bytes(b"a = 1\n")
    assert g9.verify_problems() == []
    f.write_bytes(b"a = 2\n")
    assert any("g9_source_hashes" in p for p in g9.verify_problems())
    f.write_bytes(b"a = 1\n")
    doc.write_text("edited\n", encoding="utf-8")
    assert any("prereg doc" in p for p in g9.verify_problems())


def test_verify_fails_without_freeze(monkeypatch, tmp_path, env):
    _freeze_setup(monkeypatch, tmp_path)
    assert any("no freeze record" in p for p in g9.verify_problems())


def test_run_refuses_without_verify(env, monkeypatch):
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: pytest.fail("live call"))
    with pytest.raises(SystemExit):
        g9.run(["1"])


# ---------------- scoring ----------------
def _ok(infl, ci=(0.2, 0.6)):
    return {"status": "ok", "verdict": "flaw", "calls": [{"est_usd": 0.1, "transport_retries": 0}], "retries": 0,
            "stats": {s: {"full": {"drop": {"fix_both": infl}, "drop_ci": {"fix_both": list(ci)}}} for s in ("42", "43", "44")}}


def _nul():
    return _ok(0.0, (-0.05, 0.05))


def _noflaw():
    return {"status": "ok", "verdict": "no_flaw", "calls": [{"est_usd": 0.1}], "retries": 0}


def _inc(kind="guard"):
    return {"status": "INCONCLUSIVE", "harness_failure": kind, "label": f"INCONCLUSIVE (harness failure: {kind})", "reason": ["x"], "calls": [{"est_usd": 0.1}, {"est_usd": 0.1}]}


def _recs(ehg_l, ehg_c, cw_l, cw_c):
    return {g9.EHG_LEAKY: {f"r{i + 1}": x for i, x in enumerate(ehg_l)}, g9.EHG_CLEAN: {f"r{i + 1}": x for i, x in enumerate(ehg_c)},
            g9.CW_LEAKY: {f"r{i + 1}": x for i, x in enumerate(cw_l)}, g9.CW_CLEAN: {f"r{i + 1}": x for i, x in enumerate(cw_c)}}


GOOD_CW = ([_ok(0.34)] * 3, [_nul()] * 3)


def test_ehg_pass_and_overall():
    s = g9.score_cases(_recs([_ok(0.43)] * 5, [_nul()] * 5, *GOOD_CW))
    assert s["ehg"]["PASS"] and s["civilwar"]["PASS"] and s["overall"]["harness_target_met"] and s["ehg"]["within_published_range"] == 5


def test_ehg_thresholds():
    clean = [_nul()] * 5
    assert g9.score_cases(_recs([_ok(0.43)] * 4 + [_nul()], clean, *GOOD_CW))["ehg"]["PASS"]
    assert not g9.score_cases(_recs([_ok(0.43)] * 3 + [_nul()] * 2, clean, *GOOD_CW))["ehg"]["PASS"]
    # direction 5/5 but magnitude only 2/5
    assert not g9.score_cases(_recs([_ok(0.43)] * 2 + [_ok(0.9)] * 3, clean, *GOOD_CW))["ehg"]["PASS"]
    assert g9.score_cases(_recs([_ok(0.43)] * 3 + [_ok(0.9)] * 2, clean, *GOOD_CW))["ehg"]["PASS"]
    assert not g9.score_cases(_recs([_ok(0.43)] * 5, [_ok(0.2)] + [_nul()] * 4, *GOOD_CW))["ehg"]["PASS"]
    assert not g9.score_cases({g9.EHG_LEAKY: {"r1": _ok(0.43)}, g9.EHG_CLEAN: {"r1": _nul()}})["ehg"]["PASS"]


def test_harness_inconclusive_in_denominator_never_false_alarm():
    s = g9.score_cases(_recs([_ok(0.43)] * 3 + [_inc("crash"), _inc("guard")], [_nul()] * 4 + [_inc("bad_json")], *GOOD_CW))
    e = s["ehg"]
    assert not e["PASS"] and e["direction_right"] == 3 and e["clean_false_alarms"] == 0 and e["harness_inconclusive"] == 3
    assert e["guard_harness_failures"] == 1 and s["overall"]["harness_inconclusive"] == 3 and not s["overall"]["harness_target_met"]
    assert s["cases"][g9.EHG_LEAKY]["r4"]["label"] == "INCONCLUSIVE (harness failure: crash)"


def test_no_flaw_semantics():
    s = g9.score_cases(_recs([_ok(0.43)] * 4 + [_noflaw()], [_noflaw()] * 5, *GOOD_CW))
    assert s["ehg"]["PASS"] and s["ehg"]["no_effect_or_no_flaw_leaky"] == 1 and s["ehg"]["no_effect_or_no_flaw_clean"] == 5
    assert s["cases"][g9.EHG_LEAKY]["r5"]["label"].startswith("no flaw reported")


def test_civilwar_regression_rule():
    base = ([_ok(0.43)] * 5, [_nul()] * 5)
    assert g9.score_cases(_recs(*base, [_ok(0.3), _ok(0.3), _nul()], [_nul()] * 3))["civilwar"]["PASS"]
    assert not g9.score_cases(_recs(*base, [_ok(0.3), _nul(), _nul()], [_nul()] * 3))["civilwar"]["PASS"]
    assert not g9.score_cases(_recs(*base, [_ok(0.3)] * 3, [_ok(0.1), _nul(), _nul()]))["civilwar"]["PASS"]
    assert not g9.score_cases(_recs(*base, [_ok(0.3), _ok(0.3), _inc()], [_nul()] * 3))["overall"]["harness_target_met"]


def test_b3_row():
    ok = lambda leak, fb: {"ans": {"leak": leak, "predicted_drop_pp": {"fix_both": fb}}}  # noqa: E731
    assert g9.b3_row(ok(True, 40), g9.EHG_LEAKY)["gets_it"] is True
    assert g9.b3_row(ok(True, 10), g9.EHG_LEAKY)["gets_it"] is False
    assert g9.b3_row(ok(True, 36), g9.CW_LEAKY)["gets_it"] is True
    assert g9.b3_row(ok(True, 5), g9.CW_CLEAN)["false_alarm"] is True
    assert "error" in g9.b3_row({"error": "x"}, g9.EHG_LEAKY)


# ---------------- pipeline with mocks ----------------
PLAN = {"verdict": "flaw", "factors": [{"id": "A", "flaw": "oversampling before CV", "evidence_line": "X, y = oversample(X, y, seed)",
                                          "ops": [{"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}]}],
        "predicted_drop_pp": {"fix_all": 40}, "culprit_ranking": ["A"], "reason": "r"}
OK_CHK = {"ok": True, "problems": [], "layout": "single", "configs": ["fix_all"], "notes": [], "runtime": {"decision": "ACCEPT", "configs": {"fix_all": {"decision": "ACCEPT"}}}}
BAD_CHK = {"ok": False, "problems": ["R-NOOP: nothing to fix"], "layout": None, "configs": [], "notes": [], "runtime": None}
EHG_DIR = ROOT / "real" / g9.EHG_LEAKY


class Rig:
    def __init__(self, monkeypatch, replies, checks=(OK_CHK,), smokes=({"ok": True},), execs=None):
        self.replies, self.checks, self.smokes = list(replies), list(checks), list(smokes)
        self.execs = list(execs or [{"status": "ok", "result": {"metric": "roc_auc", "seeds": {}}}])
        self.calls, self.patches = [], []
        monkeypatch.setattr(llm, "live_complete_ex", self.llm)
        monkeypatch.setattr(g9, "_guard", lambda p, d: self.checks.pop(0) if len(self.checks) > 1 else self.checks[0])
        monkeypatch.setattr(g9, "_smoke", lambda d, p: self.smokes.pop(0) if len(self.smokes) > 1 else self.smokes[0])
        monkeypatch.setattr(g9, "_run_executor", self.exe)
        import sandbox.factorial_stats as fs
        monkeypatch.setattr(fs, "all_seeds", lambda raw, n_boot=0: {s: {"full": {"drop": {"fix_both": 0.4}, "drop_ci": {"fix_both": [0.3, 0.5]}}} for s in ("42", "43", "44")})

    def llm(self, system, user, **kw):
        self.calls.append((kw["tag"], user))
        r = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(r, Exception):
            raise r
        return (r if isinstance(r, str) else json.dumps(r)), {"total_tokens": 5}

    def exe(self, case_dir, patches):
        self.patches.append(patches)
        return self.execs.pop(0) if len(self.execs) > 1 else self.execs[0]


def test_happy_path_k1(monkeypatch, env):
    rig = Rig(monkeypatch, [PLAN])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "ok" and rec["verdict"] == "flaw" and len(rec["calls"]) == 1 and rec["retries"] == 0 and rec["layout"] == "single"
    assert g9.sign_of(rec) == "+" and rec["first_plan_guard"]["decision"] == "ACCEPT"
    p = rig.patches[0]
    assert p["fix_A"] == p["fix_B"] == p["fix_both"] and "_g9" in p["fix_both"] or "oversample" in p["fix_both"]
    assert rig.calls[0][0] == "g9_planner"


def test_k2_patches_differ_and_k3_use_fix_all():
    plan2 = json.loads(json.dumps(PLAN))
    plan2["factors"].append({"id": "B", "flaw": "x", "evidence_line": "y", "ops": [{"op": "replace_split", "step": "cv_scores", "kind": "random"}]})
    comp = g9.edit_dsl.compile_plan((EHG_DIR / "train.py").read_text(encoding="utf-8"), plan2)
    p = g9.sandbox_patches(comp)
    if all(c["src"] for c in comp["configs"].values()):
        assert p["fix_A"] != p["fix_both"]
    fake3 = {"layout": "factorial", "configs": {"fix_A": {"src": "a"}, "fix_B": {"src": "b"}, "fix_C": {"src": "c"}, "fix_all": {"src": "all"}}}
    assert g9.sandbox_patches(fake3) == {"fix_A": "all", "fix_B": "all", "fix_both": "all"}


def test_guard_repair_once_then_ok(monkeypatch, env):
    rig = Rig(monkeypatch, [PLAN], checks=[BAD_CHK, OK_CHK])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "ok" and rec["repairs_used"] == ["guard"] and len(rec["calls"]) == 2 and rec["first_plan_guard"]["decision"] == "REJECT"
    assert "R-NOOP: nothing to fix" in rig.calls[1][1] and "no_flaw" in rig.calls[1][1]


def test_guard_twice_is_harness_failure(monkeypatch, env):
    Rig(monkeypatch, [PLAN], checks=[BAD_CHK])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "INCONCLUSIVE" and rec["harness_failure"] == "guard" and g9.sign_of(rec) == "INCONCLUSIVE" and len(rec["calls"]) == 2


def test_no_flaw_runs_nothing(monkeypatch, env):
    nf = {"verdict": "no_flaw", "factors": [], "reason": "clean"}
    rig = Rig(monkeypatch, [nf], checks=[{"ok": True, "problems": [], "notes": ["no_flaw"], "runtime": None}], execs=[{"status": "error"}])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "ok" and rec["verdict"] == "no_flaw" and rig.patches == [] and g9.sign_of(rec) == "0"


def test_smoke_definitive_repair_and_nondefinitive_warn(monkeypatch, env):
    bad = {"ok": False, "stage": "smoke", "kind": "TypeError", "message": "m", "definitive": True, "repair_text": "PRE-FLIGHT FAILED (smoke) in fix_A"}
    rig = Rig(monkeypatch, [PLAN], smokes=[bad, {"ok": True}])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "ok" and rec["repairs_used"] == ["smoke"] and "PRE-FLIGHT FAILED (smoke) in fix_A" in rig.calls[1][1]
    rig2 = Rig(monkeypatch, [PLAN], smokes=[dict(bad, definitive=False)])
    rec2 = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec2["status"] == "ok" and rec2["repairs_used"] == [] and len(rig2.calls) == 1
    Rig(monkeypatch, [PLAN], smokes=[bad])
    assert g9.pipeline(EHG_DIR, "g9-r1")["harness_failure"] == "smoke"


def test_crash_repair_and_bad_json_repair(monkeypatch, env):
    crash = {"status": "error", "stderr": "Traceback\nValueError: boom"}
    rig = Rig(monkeypatch, [PLAN], execs=[crash, {"status": "ok", "result": {"metric": "roc_auc", "seeds": {}}}])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "ok" and rec["repairs_used"] == ["crash"] and "ValueError: boom" in rig.calls[1][1]
    Rig(monkeypatch, [PLAN], execs=[crash])
    assert g9.pipeline(EHG_DIR, "g9-r1")["harness_failure"] == "crash"
    rig3 = Rig(monkeypatch, ["not json at all", PLAN])
    rec3 = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec3["status"] == "ok" and rec3["repairs_used"] == ["bad_json"] and len(rig3.calls) == 2
    Rig(monkeypatch, ["nope"])
    assert g9.pipeline(EHG_DIR, "g9-r1")["harness_failure"] == "bad_json"


def test_case_cap_and_internal_error(monkeypatch, env):
    Rig(monkeypatch, ["nope", PLAN], checks=[BAD_CHK], smokes=[{"ok": False, "definitive": True, "repair_text": "x"}])
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "INCONCLUSIVE" and len(rec["calls"]) <= g9.CASE_CALL_CAP
    Rig(monkeypatch, [PLAN])

    def boom(p, d):
        raise RuntimeError("guard bug")
    monkeypatch.setattr(g9, "_guard", boom)
    assert g9.pipeline(EHG_DIR, "g9-r1")["harness_failure"] == "internal_error"


def test_run_wide_planner_cap_and_ceiling(monkeypatch, env):
    Rig(monkeypatch, [PLAN])
    log = llm.g8_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps({"est_usd": 0.0, "role": "planner", "tag": "t"}) + "\n" for _ in range(90)), encoding="utf-8")
    assert g9.pipeline(EHG_DIR, "g9-r1")["harness_failure"] == "call_cap"
    log.write_text(json.dumps({"est_usd": 11.95, "role": "b3"}) + "\n", encoding="utf-8")
    assert g9.pipeline(EHG_DIR, "g9-r1")["harness_failure"] == "budget"


# ---------------- fault injection: a transport timeout is retried, not a harness failure ----------------
class Resp:
    def __init__(self, body):
        self.body = body

    def read(self):
        return self.body

    def close(self):
        pass


def ok_body(text):
    return json.dumps({"choices": [{"message": {"content": text}, "finish_reason": "stop"}], "usage": {"total_tokens": 9}}).encode()


def _script(monkeypatch, steps):
    it = iter(steps)

    def opener(req, timeout=None):
        s = next(it)
        if isinstance(s, Exception):
            raise s
        return s
    monkeypatch.setattr(transport, "_open", opener)


def test_mocked_timeout_is_retried_and_case_completes(monkeypatch, env):
    Rig(monkeypatch, [PLAN])           # guard / smoke / sandbox mocked; the LLM goes through the REAL transport below
    monkeypatch.undo() if False else None
    g9.install_instruments()
    _script(monkeypatch, [TimeoutError("read timed out"), Resp(ok_body(json.dumps(PLAN)))])
    monkeypatch.setattr(g9, "_guard", lambda p, d: OK_CHK)
    monkeypatch.setattr(g9, "_smoke", lambda d, p: {"ok": True})
    monkeypatch.setattr(g9, "_run_executor", lambda d, p: {"status": "ok", "result": {"metric": "roc_auc", "seeds": {}}})
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "ok" and rec["repairs_used"] == [] and len(rec["calls"]) == 1
    assert rec["calls"][0]["transport_attempts"] == 2 and rec["calls"][0]["transport_retries"] == 1
    tl = [json.loads(x) for x in transport.transport_log().read_text().splitlines()]
    assert len(tl) == 1 and tl[0]["counted_as_model_repair"] is False and tl[0]["will_retry"]
    assert len(g9._read_jsonl(llm.g8_log())) == 1                       # one counted call, the retry is not a second one
    assert g9.my_spent() > g9.EST["plan"]                                # but the gate's spend estimate includes the retry


def test_exhausted_transport_is_api_error_and_run_resumes(monkeypatch, env):
    g9.install_instruments()
    _script(monkeypatch, [TimeoutError("t")] * 3)
    monkeypatch.setattr(g9, "_guard", lambda p, d: OK_CHK)
    rec = g9.pipeline(EHG_DIR, "g9-r1")
    assert rec["status"] == "INCONCLUSIVE" and rec["harness_failure"] == "api_error"
    assert transport.is_transport_failure(rec) or "TransportError" in rec["reason"][0]


# ---------------- run stage with mocks ----------------
def test_run_stage_mocked_and_score(monkeypatch, env):
    seen = []

    def fake_llm(system, user, **kw):
        seen.append(kw["tag"])
        return json.dumps({"leak": True, "predicted_drop_pp": {"fix_both": 40}}), {"total_tokens": 5}
    monkeypatch.setattr(g9, "verify_problems", lambda: [])
    monkeypatch.setattr(g9, "install_instruments", lambda: None)
    monkeypatch.setattr(llm, "live_complete_ex", fake_llm)
    monkeypatch.setattr(g9, "pipeline", lambda d, rid, model=None, **k: dict(_ok(0.43), rid=rid))
    g9.run(["1", "2", "3", "4", "5"])
    assert seen == ["g9_b3"] * 16
    sizes = [len(json.loads((env / f"r{r}.json").read_text())["loop"]) for r in range(1, 6)]
    assert sizes == [4, 4, 4, 2, 2]
    out = g9.score()
    assert out["ehg"]["direction_right"] == 5 and out["civilwar"]["direction_right"] == 3 and out["ehg"]["b3_gets_it_leaky"] == 5
    seen.clear()
    g9.run(["1"])                                   # nothing left to do: no new call
    assert seen == []


def test_run_rejects_bad_repeat(monkeypatch, env):
    monkeypatch.setattr(g9, "verify_problems", lambda: [])
    with pytest.raises(SystemExit):
        g9.run(["6"])
