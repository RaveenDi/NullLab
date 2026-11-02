"""G9b runner tests. Offline: no API call, no spend. HTTP opener, spend gate, key, sandbox, guard and smoke are mocked; nothing is written under runs*/
(only read: runs_g9 is opened read-only by a few tests that check the real G9 state)."""
import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import factorial_g8 as g8, factorial_g9 as g9, factorial_g9b as b, llm, transport  # noqa: E402
from agent.factorial import agent_view  # noqa: E402

EHG_DIR = ROOT / "real" / g9.EHG_LEAKY


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("NULLLAB_G9_OUT", "NULLLAB_G9B_OUT", "NULLLAB_PHASE", "NULLLAB_G8_OUT", "NULLLAB_G8_LOG", "NULLLAB_TRACES"):
        monkeypatch.setenv(k, "x")                               # registers the variable so it is restored afterwards
    monkeypatch.setenv("NULLLAB_G9B_OUT", str(tmp_path / "g9b"))
    monkeypatch.setenv("NULLLAB_MODEL", "muse-spark-1.3-contributor")
    for obj, name in ((llm, "MAX_G8_CALLS"), (g9, "PLANNER_CALL_CAP"), (g9, "TOTAL_CALL_CAP"), (g9, "CEILING_USD"), (g8, "CEILING_USD")):
        monkeypatch.setattr(obj, name, getattr(obj, name))      # restored after the test
    monkeypatch.setattr(llm, "spend_ok", lambda est: True)
    monkeypatch.setattr(llm, "_key", lambda: "test-key-not-real")
    monkeypatch.setattr(transport, "_spend_add", lambda m, e: None)
    monkeypatch.setattr(transport, "_sleep", lambda d: None)
    monkeypatch.setattr(b, "G9_DIR", tmp_path / "g9_state")     # an empty G9 state unless a test fills it
    b.configure()
    yield tmp_path / "g9b"
    transport.uninstall()


# ---------------- constants, caps, isolation ----------------
def test_constants_and_units():
    assert len(b.UNITS) == 8 and len(b.G9_RECORDED) == 8 and not set(b.UNITS) & set(b.G9_RECORDED)
    assert sorted(set(b.UNITS) | set(b.G9_RECORDED)) == sorted(g9.units_for([1, 2, 3, 4, 5])) and len(g9.units_for([1, 2, 3, 4, 5])) == 16
    assert (b.PLANNER_CALL_CAP, b.TOTAL_CALL_CAP, b.CASE_CALL_CAP) == (40, 48, 5) and b.CEILING_USD == 4.0
    assert b.TEMPERATURE == 0.7 and b.DEFAULT_MODEL == "muse-spark-1.3-contributor" and b.EST == g9.EST
    assert len(b.UNITS) * b.CASE_CALL_CAP <= b.PLANNER_CALL_CAP
    assert sorted(b.UNITS) == sorted([(1, g9.CW_LEAKY), (2, g9.CW_LEAKY), (3, g9.CW_LEAKY), (4, g9.EHG_LEAKY), (5, g9.EHG_LEAKY),
                                      (4, g9.EHG_CLEAN), (5, g9.EHG_CLEAN), (3, g9.CW_CLEAN)])
    assert b.GUARD_G9_PRE.startswith("4a084a1c") and b.GUARD_G9B.startswith("983d2ffe")
    assert g9.ACCEPT == {"ehg": {"direction_min": 4, "false_alarm_max": 0, "magnitude_min": 3}, "civilwar": {"direction_min": 2, "false_alarm_max": 0}}


def test_configure_isolated_and_applies_caps(env):
    assert Path(llm.g8_log()).parent == env and Path(llm.g8_log()).name == "live_calls_g9b.jsonl" and Path(llm.trace_file()).parent == env
    assert Path(g9.out_dir()).resolve() == env.resolve() and llm.MAX_G8_CALLS == 48
    assert g9.PLANNER_CALL_CAP == 40 and g9.CEILING_USD == 4.0 and g8.CEILING_USD == 4.0
    assert Path(transport.transport_log()).parent == env


def test_configure_refuses_other_runs(env, monkeypatch):
    for name in ("runs_g9", "runs_g8", "runs_ehg", "runs_g7"):
        monkeypatch.setenv("NULLLAB_G9B_OUT", str(ROOT / name))
        with pytest.raises(SystemExit):
            b.configure()
        monkeypatch.setenv("NULLLAB_G9B_OUT", str(ROOT / name / "sub"))
        with pytest.raises(SystemExit):
            b.configure()


def test_projection(env):
    pj = b.projected()
    assert pj["units"] == 8 and pj["within_planner_cap"] and pj["max_planner_calls_total"] == 40
    assert pj["floor_usd"] == round(8 * 0.12 + 8 * 0.08, 2)          # no G9 state in the fixture: 8 B3 calls
    assert pj["worst_case_usd"] == round(8 * 0.08 + 40 * 0.12, 2) and not pj["worst_case_within_ceiling"]


def test_no_truth_in_agent_views_or_prompts():
    blob = "\n".join(agent_view(d) + g9.user_msg(d, "g9-r1") for d in b.CASES.values()) + g9.SYSTEM + g9.B3_SYSTEM
    for bad in ("0.430", "0.43 ", "+0.43", "0.494", "49.4", "0.36", "SMOTE", "TPEHG", "Vandewiele", "preterm", "g8_truth", "g7_truth",
                "Hegre", "Fearon", "Laitin", "Sambanis", "published", "G9b", "runs_g9"):
        assert bad not in blob, bad


def test_module_respects_agent_invariants():
    t = (ROOT / "agent" / "factorial_g9b.py").read_text(encoding="utf-8")
    assert "ground_truth" not in t and not re.search(r"from\s+eval|import\s+eval", t)
    assert "write_text" not in t.replace("g9._save", "") and "open(\"w\"" not in t and ".open(\"a\"" not in t      # no direct writes of its own


# ---------------- the real G9 state, read-only ----------------
def test_real_g9_state_matches_expectation():
    state = {r: json.loads((ROOT / "runs_g9" / f"r{r}.json").read_text(encoding="utf-8")) for r in (1, 2, 3)}
    assert b.unit_problems(state) == []
    assert b.g9_recorded_units(state) == sorted(b.G9_RECORDED)
    assert [c for c in (g9.CW_LEAKY,) for r in (1, 2, 3) if b.b3_in_g9(r, c, state)] == [g9.CW_LEAKY] * 3      # B3 already observed for the 3 stalled leaky units
    assert not any(b.b3_in_g9(r, c, state) for r, c in b.UNITS if c != g9.CW_LEAKY)


def test_agent_views_and_prompts_equal_the_g9_freeze_and_only_the_guard_changed():
    h = b.all_hashes()
    assert b.crosscheck_g9(h) == []
    assert h["code"]["agent/guard_g9.py"] == b.GUARD_G9B
    g9log = [json.loads(x) for x in (ROOT / "runs_g9" / "prereg_log.jsonl").read_text(encoding="utf-8").splitlines()]
    for c in b.CASES:
        rec = [x for x in g9log if x["kind"] == "g9_agent_view_frozen" and x["case"] == c][-1]
        assert rec["payload"] == h["agent_views"][c]


def test_crosscheck_detects_unacknowledged_change(monkeypatch):
    h = b.all_hashes()
    h["code"]["agent/edit_dsl.py"] = "0" * 64
    assert any("edit_dsl.py" in p for p in b.crosscheck_g9(h))
    h = b.all_hashes()
    h["agent_views"][g9.EHG_LEAKY]["agent_view_text_sha256"] = "0" * 64
    assert any("agent view" in p for p in b.crosscheck_g9(h))


# ---------------- refuses units already recorded in G9 ----------------
def _g9_state_dir(path, recorded=b.G9_RECORDED, b3_for=()):
    path.mkdir(parents=True, exist_ok=True)
    for r in range(1, 6):
        d = {"repeat": f"g9-r{r}", "b3": {}, "loop": {}}
        for rr, c in recorded:
            if rr == r:
                d["loop"][c] = _ok(0.43) if c in (g9.EHG_LEAKY, g9.CW_LEAKY) else _nul()
        for rr, c in b3_for:
            if rr == r:
                d["b3"][c] = {"ans": {"leak": True, "predicted_drop_pp": {"fix_both": 40}}}
        if d["loop"] or d["b3"]:
            (path / f"r{r}.json").write_text(json.dumps(d), encoding="utf-8")
    return path


def test_refuses_units_already_recorded_in_g9(env, monkeypatch, tmp_path):
    d = _g9_state_dir(tmp_path / "g9_state", recorded=list(b.G9_RECORDED) + [(1, g9.CW_LEAKY)])
    monkeypatch.setattr(b, "G9_DIR", d)
    with pytest.raises(SystemExit) as e:
        b.check_units_not_in_g9()
    assert unit_clash(e.value, "g9-r1:" + g9.CW_LEAKY)
    assert any("already has a record" in p for p in b.unit_problems())
    monkeypatch.setattr(b, "verify_problems", lambda: [])
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: pytest.fail("live call"))
    monkeypatch.setattr(b.g9, "pipeline", lambda *a, **k: pytest.fail("pipeline"))
    with pytest.raises(SystemExit):
        b.run([])
    assert not (env / "r1.json").exists()


def unit_clash(exc, needle):
    return needle in str(exc)


def test_unit_problems_when_g9_state_is_not_the_expected_8(env, monkeypatch, tmp_path):
    monkeypatch.setattr(b, "G9_DIR", _g9_state_dir(tmp_path / "s", recorded=b.G9_RECORDED[:5]))
    assert any("runs_g9 records" in p for p in b.unit_problems())
    monkeypatch.setattr(b, "G9_DIR", _g9_state_dir(tmp_path / "s2"))
    assert b.unit_problems() == []


def test_never_writes_into_g9_dir(env, monkeypatch, tmp_path):
    d = _g9_state_dir(tmp_path / "g9_state", b3_for=[(r, g9.CW_LEAKY) for r in (1, 2, 3)])
    before = {p.name: p.read_bytes() for p in d.iterdir()}
    monkeypatch.setattr(b, "G9_DIR", d)
    monkeypatch.setattr(b, "verify_problems", lambda: [])
    monkeypatch.setattr(g9, "install_instruments", lambda: None)
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: (json.dumps({"leak": True, "predicted_drop_pp": {"fix_both": 40}}), {}))
    monkeypatch.setattr(g9, "pipeline", lambda dd, rid, model=None, **k: dict(_ok(0.43), rid=rid))
    b.run([])
    b.score()
    assert {p.name: p.read_bytes() for p in d.iterdir()} == before


# ---------------- hashing / freeze / verify ----------------
def _freeze_setup(monkeypatch, tmp_path):
    f, doc = tmp_path / "code.py", tmp_path / "doc.md"
    f.write_bytes(b"a = 1\r\n")
    doc.write_text("prereg\n", encoding="utf-8")
    monkeypatch.setattr(b, "CODE_FILES", (str(f),))
    monkeypatch.setattr(b, "DOC", str(doc))
    monkeypatch.setattr(b, "crosscheck_g9", lambda h: [])
    monkeypatch.setattr(b, "unit_problems", lambda state=None: [])
    return f, doc


def test_freeze_verify_lf_and_change_detection(monkeypatch, tmp_path, env):
    f, doc = _freeze_setup(monkeypatch, tmp_path)
    b.freeze()
    recs = [json.loads(x) for x in (env / "prereg_log.jsonl").read_text().splitlines()]
    src = next(r for r in recs if r["kind"] == "g9b_source_hashes")
    assert src["payload"][str(f)] == hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert src["sha256"] == hashlib.sha256(json.dumps(src["payload"], sort_keys=True).encode()).hexdigest()
    rules = next(r for r in recs if r["kind"] == "g9b_rules")
    assert rules["sha256"] == hashlib.sha256(json.dumps(b.rules_payload(), sort_keys=True).encode()).hexdigest()
    assert {r["case"] for r in recs if r["kind"] == "g9b_agent_view_frozen"} == set(b.CASES)
    assert b.verify_problems() == []
    f.write_bytes(b"a = 1\n")
    assert b.verify_problems() == []                      # CRLF vs LF is not a change
    f.write_bytes(b"a = 2\n")
    assert any("g9b_source_hashes" in p for p in b.verify_problems())
    f.write_bytes(b"a = 1\n")
    doc.write_text("edited\n", encoding="utf-8")
    assert any("prereg doc" in p for p in b.verify_problems())


def test_verify_fails_without_freeze_and_run_refuses(monkeypatch, tmp_path, env):
    _freeze_setup(monkeypatch, tmp_path)
    assert any("no freeze record" in p for p in b.verify_problems())
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: pytest.fail("live call"))
    with pytest.raises(SystemExit):
        b.run([])


def test_rules_payload_is_json_stable():
    p = b.rules_payload()
    assert json.loads(json.dumps(p)) == p
    assert p["planner_call_cap"] == 40 and p["ceiling_usd"] == 4.0 and p["acceptance"] == g9.ACCEPT


# ---------------- scoring: union of G9 and G9b ----------------
def _ok(infl, ci=(0.2, 0.6)):
    return {"status": "ok", "verdict": "flaw", "calls": [{"est_usd": 0.1, "transport_retries": 0}], "retries": 0,
            "stats": {s: {"full": {"drop": {"fix_both": infl}, "drop_ci": {"fix_both": list(ci)}}} for s in ("42", "43", "44")}}


def _nul():
    return _ok(0.0, (-0.05, 0.05))


def _noflaw():
    return {"status": "ok", "verdict": "no_flaw", "calls": [{"est_usd": 0.1}], "retries": 0}


def _inc(kind="guard"):
    return {"status": "INCONCLUSIVE", "harness_failure": kind, "label": f"INCONCLUSIVE (harness failure: {kind})", "reason": ["x"], "calls": [{"est_usd": 0.1}]}


def _split(vals):
    """vals(unit) -> record; returns (g9_loop, g9b_loop)."""
    g9l, g9bl = {c: {} for c in b.CASES}, {c: {} for c in b.CASES}
    for r, c in b.G9_RECORDED:
        g9l[c][f"r{r}"] = vals(r, c)
    for r, c in b.UNITS:
        g9bl[c][f"r{r}"] = vals(r, c)
    return g9l, g9bl


def _default(r, c):
    return _ok(0.43) if c in (g9.EHG_LEAKY, g9.CW_LEAKY) else _nul()


def test_union_complete_pass_with_labels():
    s = b.union_score(*_split(_default))
    assert s["complete"] and s["units_present"] == 16 and s["units_present_g9"] == 8 and s["units_present_g9b"] == 8 and s["missing"] == []
    assert s["union_result"] == {"EHG": "PASS", "CIVILWAR_REGRESSION": "PASS", "harness_target_met": True}
    assert s["union"]["ehg"]["direction_right"] == 5 and s["union"]["ehg"]["n_leaky"] == 5 and s["union"]["ehg"]["n_clean"] == 5
    assert s["union"]["civilwar"]["n_leaky"] == 3 and s["union"]["civilwar"]["n_clean"] == 3
    by = {u["unit"]: u for u in s["per_unit"]}
    assert len(by) == 16
    assert by["g9-r1:" + g9.EHG_LEAKY]["source"] == "g9" and by["g9-r1:" + g9.EHG_LEAKY]["guard_sha256"] == b.GUARD_G9_PRE
    assert by["g9-r4:" + g9.EHG_LEAKY]["source"] == "g9b" and by["g9-r4:" + g9.EHG_LEAKY]["guard_sha256"] == b.GUARD_G9B
    assert "15:28-15:58" in by["g9-r1:" + g9.EHG_LEAKY]["ran"]
    assert s["by_source"]["g9"]["ehg"]["direction_right"] == 3 and s["by_source"]["g9b"]["ehg"]["direction_right"] == 2
    assert s["by_source"]["g9"]["civilwar"]["clean_units"] == 2 and s["by_source"]["g9b"]["civilwar"]["leaky_units"] == 3
    assert "EVAL-14" in s["label_note"] and set(s["guard_versions"]) == {"g9", "g9b"}


def test_union_clause_edges_use_the_union_not_one_run():
    # 3 right in G9 (all recorded EHG leaky) and 1 right + 1 no-flaw in G9b: 4/5 passes; 3/5 does not
    def vals(n_g9b_right):
        seen = []

        def f(r, c):
            if c == g9.EHG_LEAKY and r >= 4:
                seen.append(r)
                return _ok(0.43) if len(seen) <= n_g9b_right else _noflaw()
            return _default(r, c)
        return f
    assert b.union_score(*_split(vals(1)))["union_result"]["EHG"] == "PASS"
    assert b.union_score(*_split(vals(0)))["union_result"]["EHG"] == "FAIL"
    # magnitude: G9 units 0.43 x3, G9b 0.9 x2 -> within 0.15 in 3/5 still passes; with G9 units off it fails
    assert b.union_score(*_split(lambda r, c: _ok(0.9) if (c == g9.EHG_LEAKY and r >= 4) else _default(r, c)))["union_result"]["EHG"] == "PASS"
    assert b.union_score(*_split(lambda r, c: _ok(0.9) if (c == g9.EHG_LEAKY and r >= 3) else _default(r, c)))["union_result"]["EHG"] == "FAIL"
    # a clean false alarm in G9b fails the union
    assert b.union_score(*_split(lambda r, c: _ok(0.3) if (c == b.EHG_C and r == 5) else _default(r, c)))["union_result"]["EHG"] == "FAIL"
    # civil war: direction >= 2/3 and 0/3 false alarms over G9b leaky units + G9/G9b clean units
    assert b.union_score(*_split(lambda r, c: _noflaw() if (c == b.CW_L and r == 3) else _default(r, c)))["union_result"]["CIVILWAR_REGRESSION"] == "PASS"
    assert b.union_score(*_split(lambda r, c: _noflaw() if (c == b.CW_L and r >= 2) else _default(r, c)))["union_result"]["CIVILWAR_REGRESSION"] == "FAIL"
    assert b.union_score(*_split(lambda r, c: _ok(0.3) if (c == b.CW_C and r == 3) else _default(r, c)))["union_result"]["CIVILWAR_REGRESSION"] == "FAIL"


def test_union_harness_inconclusive_in_denominator_and_labelled():
    s = b.union_score(*_split(lambda r, c: _inc("guard") if (c == g9.EHG_LEAKY and r == 4) else _inc("api_error") if (c == b.CW_L and r == 1) else _default(r, c)))
    assert s["complete"] and s["union_result"]["harness_target_met"] is False and len(s["harness_failures"]) == 2
    assert s["union"]["ehg"]["direction_right"] == 4 and s["union"]["ehg"]["clean_false_alarms"] == 0 and s["union"]["ehg"]["harness_inconclusive"] == 1
    assert s["union_result"]["EHG"] == "PASS"          # 4/5 direction, 4/5 magnitude, 0 false alarms: the clauses are met even with a harness failure listed
    assert s["by_source"]["g9b"]["ehg"]["harness_inconclusive"] == 1 and s["by_source"]["g9"]["ehg"]["harness_inconclusive"] == 0
    assert s["union"]["civilwar"]["direction_right"] == 2 and s["union_result"]["CIVILWAR_REGRESSION"] == "PASS"
    assert s["union"]["civilwar"]["guard_harness_failures"] == 0
    row = next(u for u in s["per_unit"] if u["unit"] == "g9-r4:" + g9.EHG_LEAKY)
    assert row["outcome"] == "INCONCLUSIVE (harness failure: guard)" and row["source"] == "g9b"


def test_union_incomplete_is_not_complete_and_not_evaluable():
    g9l, g9bl = _split(_default)
    del g9bl[b.CW_C]["r3"]
    s = b.union_score(g9l, g9bl)
    assert not s["complete"] and s["units_present"] == 15 and s["missing"] == ["g9-r3:" + b.CW_C]
    assert s["union_result"]["CIVILWAR_REGRESSION"].startswith("NOT EVALUABLE") and s["union_result"]["EHG"].startswith("NOT EVALUABLE")
    assert not s["union"]["civilwar"]["PASS"]                                        # a missing unit can never pass
    only_g9 = b.union_score(g9l, {c: {} for c in b.CASES})
    assert not only_g9["complete"] and only_g9["units_present"] == 8 and len(only_g9["missing"]) == 8


def test_union_rejects_a_unit_recorded_twice():
    g9l, g9bl = _split(_default)
    g9bl[g9.EHG_LEAKY]["r1"] = _ok(0.4)
    with pytest.raises(ValueError):
        b.union_score(g9l, g9bl)


def test_union_b3_uses_g9_answer_for_stalled_units():
    g9l, g9bl = _split(_default)
    stalled = {g9.CW_LEAKY: {f"r{r}": {"leak": True, "fix_both_pp": 36.0, "gets_it": True} for r in (1, 2, 3)}}
    own = {g9.EHG_LEAKY: {"r4": {"leak": True, "fix_both_pp": 40.0, "gets_it": True}}}
    s = b.union_score(g9l, g9bl, {}, own, stalled)
    by = {u["unit"]: u for u in s["per_unit"]}
    assert by["g9-r1:" + g9.CW_LEAKY]["b3_from"] == "g9" and by["g9-r4:" + g9.EHG_LEAKY]["b3_from"] == "g9b"
    assert s["union"]["civilwar"]["b3_gets_it_leaky"] == 3 and s["union"]["ehg"]["b3_gets_it_leaky"] == 1


# ---------------- pipeline with mocks: fault injection ----------------
PLAN = {"verdict": "flaw", "factors": [{"id": "A", "flaw": "oversampling before CV", "evidence_line": "X, y = oversample(X, y, seed)",
                                          "ops": [{"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}]}],
        "predicted_drop_pp": {"fix_all": 40}, "culprit_ranking": ["A"], "reason": "r"}
OK_CHK = {"ok": True, "problems": [], "layout": "single", "configs": ["fix_all"], "notes": [], "runtime": {"decision": "ACCEPT", "configs": {"fix_all": {"decision": "ACCEPT"}}}}


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


def _stub_pipeline_parts(monkeypatch):
    import sandbox.factorial_stats as fs
    monkeypatch.setattr(g9, "_guard", lambda p, d: OK_CHK)
    monkeypatch.setattr(g9, "_smoke", lambda d, p: {"ok": True})
    monkeypatch.setattr(g9, "_run_executor", lambda d, p: {"status": "ok", "result": {"metric": "roc_auc", "seeds": {}}})
    monkeypatch.setattr(fs, "all_seeds", lambda raw, n_boot=0: {s: {"full": {"drop": {"fix_both": 0.4}, "drop_ci": {"fix_both": [0.3, 0.5]}}} for s in ("42", "43", "44")})


def test_timeout_is_retried_not_a_harness_failure(monkeypatch, env):
    g9.install_instruments()
    _stub_pipeline_parts(monkeypatch)
    _script(monkeypatch, [TimeoutError("read timed out"), Resp(ok_body(json.dumps(PLAN)))])
    rec = g9.pipeline(EHG_DIR, "g9-r4")
    assert rec["status"] == "ok" and rec["repairs_used"] == [] and len(rec["calls"]) == 1
    assert rec["calls"][0]["transport_attempts"] == 2 and rec["calls"][0]["transport_retries"] == 1
    tl = [json.loads(x) for x in transport.transport_log().read_text().splitlines()]
    assert len(tl) == 1 and tl[0]["counted_as_model_repair"] is False and tl[0]["will_retry"] and transport.transport_log().parent == env
    assert len(g9._read_jsonl(llm.g8_log())) == 1 and llm.g8_log().name == "live_calls_g9b.jsonl"
    assert g9.my_spent() > g9.EST["plan"]


def test_exhausted_transport_is_recorded_not_rerolled(monkeypatch, env, tmp_path):
    g9.install_instruments()
    _stub_pipeline_parts(monkeypatch)
    _script(monkeypatch, [TimeoutError("t")] * 3)
    rec = g9.pipeline(EHG_DIR, "g9-r4")
    assert rec["status"] == "INCONCLUSIVE" and rec["harness_failure"] == "api_error"
    # a second run does not re-run a unit whose harness failure is recorded (G9's 'forget transport failures' rule is not used by G9b)
    d = _g9_state_dir(tmp_path / "g9_state")
    monkeypatch.setattr(b, "G9_DIR", d)
    monkeypatch.setattr(b, "verify_problems", lambda: [])
    monkeypatch.setattr(g9, "install_instruments", lambda: None)
    (env / "r4.json").write_text(json.dumps({"repeat": "g9-r4", "b3": {}, "loop": {g9.EHG_LEAKY: rec}}), encoding="utf-8")
    ran = []
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: (json.dumps({"leak": False, "predicted_drop_pp": {"fix_both": 0}}), {}))
    monkeypatch.setattr(g9, "pipeline", lambda dd, rid, model=None, **k: ran.append((dd.name, rid)) or dict(_nul(), rid=rid))
    b.run(["4"])
    assert (g9.EHG_LEAKY, "g9-r4") not in ran and ran == [(b.EHG_C, "g9-r4")]
    assert json.loads((env / "r4.json").read_text())["loop"][g9.EHG_LEAKY]["harness_failure"] == "api_error"


# ---------------- run stage with mocks ----------------
def _fake_llm(seen, replies=None):
    def f(system, user, **kw):
        seen.append((kw["tag"], user))
        return json.dumps({"leak": True, "predicted_drop_pp": {"fix_both": 40}}), {"total_tokens": 5}
    return f


def test_run_stage_mocked_then_score_complete(monkeypatch, env, tmp_path):
    d = _g9_state_dir(tmp_path / "g9_state", b3_for=[(r, g9.CW_LEAKY) for r in (1, 2, 3)])
    monkeypatch.setattr(b, "G9_DIR", d)
    seen, rids = [], []
    monkeypatch.setattr(b, "verify_problems", lambda: [])
    monkeypatch.setattr(g9, "install_instruments", lambda: None)
    monkeypatch.setattr(llm, "live_complete_ex", _fake_llm(seen))
    monkeypatch.setattr(g9, "pipeline", lambda dd, rid, model=None, **k: rids.append((rid, dd.name)) or dict(_default(int(rid[-1]), dd.name), rid=rid))
    b.run([])
    # B3 asked for 5 units; the 3 whose G9 B3 answer exists are not asked again; repeat ids are the G9 ones
    assert [t for t, u in seen] == ["g9b_b3"] * 5 and all("[repeat id: g9-r" in u for t, u in seen)
    assert {(r, c) for r, c in ((int(x[0][-1]), x[1]) for x in rids)} == set(b.UNITS) and len(rids) == 8
    sizes = {r: len(json.loads((env / f"r{r}.json").read_text())["loop"]) for r in (1, 2, 3, 4, 5)}
    assert sizes == {1: 1, 2: 1, 3: 2, 4: 2, 5: 2}
    assert all(json.loads((env / f"r{r}.json").read_text())["instrument"] == "g9b" for r in sizes)
    out = b.score()
    assert out["complete"] and out["units_present_g9"] == 8 and out["units_present_g9b"] == 8
    assert out["union"]["ehg"]["direction_right"] == 5 and out["union_result"]["EHG"] == "PASS" and out["union_result"]["CIVILWAR_REGRESSION"] == "PASS"
    assert json.loads((env / "score.json").read_text())["complete"] is True
    seen.clear()
    b.run([])                                                  # everything recorded: nothing to do, no call
    assert seen == [] and len(rids) == 8


def test_score_incomplete_writes_complete_false(monkeypatch, env, tmp_path):
    monkeypatch.setattr(b, "G9_DIR", _g9_state_dir(tmp_path / "g9_state"))
    out = b.score()
    assert out["complete"] is False and out["units_present"] == 8 and json.loads((env / "score.json").read_text())["complete"] is False


def test_admission_leaves_units_unstarted_not_failed(monkeypatch, env, tmp_path):
    monkeypatch.setattr(b, "G9_DIR", _g9_state_dir(tmp_path / "g9_state"))
    monkeypatch.setattr(b, "verify_problems", lambda: [])
    monkeypatch.setattr(g9, "install_instruments", lambda: None)
    monkeypatch.setattr(b, "CEILING_USD", 0.5)                  # a unit needs 0.68 + margin: none fits
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: pytest.fail("live call"))
    monkeypatch.setattr(g9, "pipeline", lambda *a, **k: pytest.fail("pipeline"))
    b.run([])
    assert not list(env.glob("r*.json")) or all(not json.loads(p.read_text())["loop"] for p in env.glob("r*.json"))


def test_admission_reserves_in_flight_worst_case(env):
    a = b.Admission()
    need = b.EST["b3"] + 5 * b.EST["plan"] + b.RETRY_MARGIN_USD
    n = 0
    while a.admit(need) and n < 20:
        n += 1
    assert n == int(b.CEILING_USD // need) or n == int((b.CEILING_USD + 1e-9) // need)
    a.release(need)
    assert a.admit(need)


def test_planner_cap_and_ceiling_enforced_on_own_log(monkeypatch, env):
    _stub_pipeline_parts(monkeypatch)
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: (json.dumps(PLAN), {}))
    log = llm.g8_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("".join(json.dumps({"est_usd": 0.0, "role": "planner", "tag": "t"}) + "\n" for _ in range(40)), encoding="utf-8")
    assert g9.pipeline(EHG_DIR, "g9-r4")["harness_failure"] == "call_cap"
    log.write_text(json.dumps({"est_usd": 3.95, "role": "b3"}) + "\n", encoding="utf-8")
    assert g9.pipeline(EHG_DIR, "g9-r4")["harness_failure"] == "budget"
