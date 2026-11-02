"""G8 tests: separate repair budgets, honest labels, call cap, scoring denominators, llm backward compatibility.
Offline; model and sandbox are mocked; nothing is written under runs*/ (prereg log goes to tmp)."""
import inspect
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import factorial_g7 as g7, factorial_g8 as g8, fidelity, llm  # noqa: E402

CASE = g7.CASES[g7.LEAKY]
_R1 = json.loads((ROOT / "runs_g7" / "r1.json").read_text(encoding="utf-8"))
_R4 = json.loads((ROOT / "runs_g7" / "r4.json").read_text(encoding="utf-8"))
GOOD = _R1["loop"][g7.LEAKY]["final_plan"]           # accepted by guard + SPLIT-USE-REQUIRED in G7
BAD = _R4["plan"][g7.LEAKY]["plan"]                  # rejected by SPLIT-USE-REQUIRED in G7
STDERR = "Traceback (most recent call last):\n" + "\n".join(f"  line {i}" for i in range(60)) + "\nTypeError: boom"


class Harness:
    def __init__(self, monkeypatch, tmp_path, replies, execs):
        self.replies, self.execs, self.calls = list(replies), list(execs), []
        monkeypatch.setenv("NULLLAB_G8_OUT", str(tmp_path))
        monkeypatch.setattr(llm, "live_complete_ex", self.fake_llm)
        monkeypatch.setattr(g8, "_run_executor", self.fake_exec)
        monkeypatch.setattr(fidelity, "check_runtime", lambda *a, **k: [])
        import sandbox.factorial_stats as fs
        monkeypatch.setattr(fs, "all_seeds", lambda raw, n_boot=0: {"42": {"full": {"drop": {"fix_both": 0.3}, "drop_ci": {"fix_both": [0.2, 0.4]}}}})

    def fake_llm(self, system, user, **kw):
        self.calls.append((kw.get("tag"), user))
        r = self.replies.pop(0)
        return (r if isinstance(r, str) else json.dumps(r)), {"total_tokens": 7}

    def fake_exec(self, case_dir, patches):
        r = self.execs.pop(0)
        return {"status": "error", "stderr": STDERR} if r == "crash" else {"status": "ok", "result": {"metric": "pr_auc"}}


def run(h):
    return g8.pipeline(CASE, "t", model="m", temperature=0)


def test_clean_path_makes_one_call(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, [GOOD], ["ok"])
    rec = run(h)
    assert rec["status"] == "ok" and len(rec["calls"]) == 1 and rec["repairs_used"] == []


def test_crash_gets_one_repair_with_stderr_tail(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, [GOOD, GOOD], ["crash", "ok"])
    rec = run(h)
    assert rec["status"] == "ok" and rec["repairs_used"] == ["crash"]
    tag, user = h.calls[1]
    assert tag.endswith("crash_repair") and "TypeError: boom" in user and "line 0" not in user  # only the last lines


def test_second_crash_is_labelled_harness_failure(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, [GOOD, GOOD], ["crash", "crash"])
    rec = run(h)
    assert rec["status"] == "INCONCLUSIVE" and rec["harness_failure"] == "crash"
    assert rec["label"] == "INCONCLUSIVE (harness failure: crash)"
    assert len(rec["calls"]) == 2


def test_bad_json_first_plan_gets_one_json_repair(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, ['{"A": "x",', GOOD], ["ok"])
    rec = run(h)
    assert rec["status"] == "ok" and rec["repairs_used"] == ["bad_json"]
    assert '{"A": "x",' in h.calls[1][1]  # the bad reply is fed back


def test_bad_json_twice_is_harness_failure(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, ["nope", "still nope"], [])
    rec = run(h)
    assert rec["harness_failure"] == "bad_json" and len(rec["calls"]) == 2


def test_guard_rejection_then_recovery_and_budgets_are_separate(monkeypatch, tmp_path):
    # g7 r4 situation: rejected plan, retry reply is not JSON -> json repair (its own budget) -> accepted
    h = Harness(monkeypatch, tmp_path, [BAD, "{broken", GOOD], ["ok"])
    rec = run(h)
    assert rec["status"] == "ok" and rec["repairs_used"] == ["bad_json", "guard"] and len(rec["calls"]) == 3


def test_second_guard_rejection_is_harness_failure_guard(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, [BAD, BAD], [])
    rec = run(h)
    assert rec["harness_failure"] == "guard" and rec["label"] == "INCONCLUSIVE (harness failure: guard)"


def test_all_three_kinds_fit_exactly_in_the_cap(monkeypatch, tmp_path):
    # plan(bad json) -> json repair(BAD) -> guard repair(GOOD, crashes) -> crash repair(GOOD) = 4 calls
    h = Harness(monkeypatch, tmp_path, ["{x", BAD, GOOD, GOOD], ["crash", "ok"])
    rec = run(h)
    assert rec["status"] == "ok" and len(rec["calls"]) == g8.CASE_CALL_CAP == 4
    assert sorted(rec["repairs_used"]) == ["bad_json", "crash", "guard"]


def test_hard_call_cap_is_enforced_before_the_call(monkeypatch, tmp_path):
    b = g8.CaseBudget(cap=2)
    h = Harness(monkeypatch, tmp_path, ["x", "y", "z"], [])
    b.call("plan", "s", "u", "t", "m", 0)
    b.call("guard", "s", "u", "t", "m", 0)
    with pytest.raises(g8.HarnessFailure) as e:
        b.call("crash", "s", "u", "t", "m", 0)
    assert e.value.kind == "call_cap" and len(h.calls) == 2


def test_api_error_is_a_harness_label_not_a_crash_of_the_driver(monkeypatch, tmp_path):
    h = Harness(monkeypatch, tmp_path, [], [])
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: (_ for _ in ()).throw(llm.LiveNotAllowed("empty content")))
    rec = run(h)
    assert rec["harness_failure"] == "api_error"


# ---------------- labels and scoring ----------------
def _ok(sign_ci, infl=0.3):
    return {"status": "ok", "calls": [1], "retries": 0,
            "stats": {s: {"full": {"drop": {"fix_both": infl}, "drop_ci": {"fix_both": sign_ci}}} for s in ("42", "43", "44")}}


def _hf(kind):
    return {"status": "INCONCLUSIVE", "harness_failure": kind, "label": g8.label("INCONCLUSIVE", kind), "reason": ["why"], "calls": []}


def test_labels_are_distinct():
    assert g8.outcome_label(_ok([-0.1, 0.1])) == "no effect (interval spans 0)"
    assert g8.outcome_label(_hf("crash")) == "INCONCLUSIVE (harness failure: crash)"
    assert g8.outcome_label(_ok([0.2, 0.4])).startswith("inflation found")


def test_score_counts_harness_failures_in_denominator_and_lists_them():
    leaky = {f"r{i}": _ok([0.2, 0.4], 0.31) for i in range(1, 5)}
    leaky["r5"] = _hf("crash")
    clean = {f"r{i}": _ok([-0.1, 0.1], 0.0) for i in range(1, 6)}
    s = g8.score_cases({g7.LEAKY: leaky, g7.CLEAN: clean})
    a = s["acceptance"]
    assert a["a_direction_right"] == 4 and a["denominator_leaky"] == 5 and a["harness_inconclusive"] == 1
    assert a["no_effect_clean"] == 5 and a["b_clean_false_alarms"] == 0
    assert s["harness_failures"][0]["failure"] == "crash" and a["PASS"] is True and a["harness_target_met"] is False


def test_harness_failure_never_counts_as_no_effect_or_false_alarm():
    clean = {f"r{i}": _hf("bad_json") for i in range(1, 6)}
    leaky = {f"r{i}": _ok([0.2, 0.4], 0.3) for i in range(1, 6)}
    a = g8.score_cases({g7.LEAKY: leaky, g7.CLEAN: clean})["acceptance"]
    assert a["no_effect_clean"] == 0 and a["b_clean_false_alarms"] == 0 and a["harness_inconclusive"] == 5


def test_acceptance_numbers_identical_to_g7():
    assert (g8.N_REPEATS, g8.TEMPERATURE, g8.PUBLISHED_INFLATION, g8.TOL) == (5, 0.7, 0.36, 0.15)
    assert g8.SYSTEM is g7.SYSTEM and g8.B3_SYSTEM == g7.B3_SYSTEM


def test_projection_matches_cap():
    p = g8.projected(10)
    assert p["worst_case_usd"] > p["expected_floor_usd"] and p["max_live_calls_total"] == 50


def test_native_schema_stays_off_and_is_unverified():
    assert g8.USE_NATIVE_SCHEMA is False


# ---------------- llm.py backward compatibility ----------------
def test_live_complete_signature_still_compatible():
    ps = list(inspect.signature(llm.live_complete).parameters)
    assert ps[:8] == ["system", "user", "est_usd", "max_tokens", "tag", "role", "model", "temperature"]


def test_live_complete_returns_str_and_ex_returns_pair_in_replay(tmp_path):
    k = llm.prompt_key("s", "u", "m")
    t = tmp_path / "t.jsonl"
    t.write_text(json.dumps({"key": k, "reply": "hello"}) + "\n", encoding="utf-8")
    llm.set_replay(t)
    try:
        assert llm.live_complete("s", "u", model="m") == "hello"
        assert llm.live_complete_ex("s", "u", model="m") == ("hello", {})
    finally:
        llm.set_replay(None)


def test_g8_phase_uses_own_log_and_traces(monkeypatch):
    monkeypatch.setenv("NULLLAB_PHASE", "g8")
    monkeypatch.delenv("NULLLAB_TRACES", raising=False)
    assert llm.g8_phase() and "runs_g8" in str(llm.trace_file()) and "runs_g8" in str(llm.g8_log())
