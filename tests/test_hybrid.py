"""Tests for agent/hybrid.py: rules-first routing, cost ledger, referee veto. Offline: every model call and every sandbox run is a mock.
Numbers in the fake records are hand-made fixtures, never measurements."""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from agent import hybrid, llm  # noqa: E402
from baselines import rulefix  # noqa: E402

LEAKY = ROOT / "corpus" / "leak_prescale"      # rule R2 fires (runs_rulefix/leak_prescale.json)
NO_RULE = ROOT / "corpus" / "leak_group"       # no rule fires (the rule library misses it: runs_rulefix/leak_group.json)
pytestmark = pytest.mark.skipif(not (LEAKY / "data.csv").exists() or not (NO_RULE / "data.csv").exists(), reason="corpus not present")


def fake_stats(drop, half=0.04):
    """Hand-made stats in the shape of sandbox/factorial_stats.all_seeds. drop = fix_both drop; half = CI half width."""
    out = {}
    for s, d in (("42", drop), ("43", drop + 0.01), ("44", drop - 0.01)):
        ci = [d - half, d + half]
        full = {"acc": {"orig": 0.9, "fix_A": 0.9, "fix_B": round(0.9 - d, 4), "fix_both": round(0.9 - d, 4)},
                "n": {"orig": 100, "fix_A": 100, "fix_B": 100, "fix_both": 100},
                "drop": {"fix_A": 0.0, "fix_B": d, "fix_both": d}, "drop_ci": {"fix_A": [-0.05, 0.05], "fix_B": ci, "fix_both": ci},
                "I": 0.0, "I_ci": [-0.1, 0.1], "I_excludes_0": False}
        out[s] = {"full": full, "same_n": full}
    return out


def fake_rule_rec(case_dir, drop):
    b = rulefix.build_configs(case_dir)
    return {"case": Path(case_dir).name, "tool": "rulefix (no LLM)", "seeds": [42, 43, 44], "n_boot": 1000, "bootstrap": "unpaired",
            "fired": b["det"]["fired"], "not_applied": b["det"]["not_applied"], "split_fn": b["det"]["split_fn"],
            "configs": {k: {"rules_applied": v["rules_applied"], "steps": v["steps"], "notes": v["notes"],
                            "src_sha256": hashlib.sha256(v["src"].encode()).hexdigest()} for k, v in b["configs"].items()},
            "sources": {k: b["configs"][k]["src"] for k in ("fix_A", "fix_B", "fix_both")}, "status": "ok",
            "stats": fake_stats(drop), "metric": "accuracy"}


def fake_loop_rec(case_dir, drop):
    b = rulefix.build_configs(case_dir)
    return {"retries": 0, "status": "ok", "stats": fake_stats(drop), "metric": "accuracy",
            "final_plan": {"mode": "MOCK spark (test fixture)", "A": "mock A", "B": "mock B"}, "log": [],
            "fidelity": {"fix_both": "only step(s) prep_full changed (fit_scope)"},
            "sources": {k: b["configs"][k]["src"] for k in ("fix_A", "fix_B", "fix_both")}}


@pytest.fixture
def leaky(tmp_path):
    d = tmp_path / "leak_prescale"
    shutil.copytree(LEAKY, d)
    return d


@pytest.fixture
def norule(tmp_path):
    d = tmp_path / "leak_group"
    shutil.copytree(NO_RULE, d)
    return d


def boom(*a, **k):
    raise AssertionError("the model path must not be used")


def test_rules_fire_and_confirm_no_model(leaky, monkeypatch):
    monkeypatch.setattr(llm, "live_complete", boom)
    res = hybrid.run_hybrid(leaky, measure=lambda c: (fake_rule_rec(c, 0.16), "mock measurement"), spark_runner=boom, allow_recorded=False)
    assert res["verdict"] == "INFLATED" and res["source"] == hybrid.TAG_RULES
    assert res["ledger"]["calls"] == 0 and res["ledger"]["est_usd"] == 0.0
    assert res["rules_applicable"] == ["R2"]
    assert all(x["by"] != hybrid.TAG_SPARK for x in res["steps"])
    assert res["summary"]["sign"] == "+" and res["summary"]["inflation"] == pytest.approx(16.0)


def test_disagreement_calls_spark_and_ledger_counts(leaky, tmp_path):
    calls = []

    def spark(c, ledger, live):
        calls.append(c)
        ledger.add("planner", "muse-spark-1.3", "mock", 4000, 1500, 0.10)
        return fake_loop_rec(c, 0.12)

    res = hybrid.run_hybrid(leaky, measure=lambda c: (fake_rule_rec(c, 0.0), "mock"), spark_runner=spark, allow_recorded=False, out_dir=tmp_path / "o")
    assert len(calls) == 1
    assert res["verdict"] == "INFLATED" and res["source"].startswith("Spark")
    assert "injected runner" in res["source"]   # a mock is never labelled as a plain live Spark call
    lg = res["ledger"]
    assert lg["calls"] == 1 and lg["est_usd"] == pytest.approx(0.10) and lg["by_model"]["muse-spark-1.3"]["tokens_in_est"] == 4000
    assert any("DISAGREE" in x["detail"] for x in res["steps"])
    assert Path(res["record_file"]).name == "r1.json"
    text = hybrid.render_report(res, leaky)
    assert "Cost ledger" in text and "Who did what" in text and "muse-spark-1.3" in text and "ESTIMATE" in text


def test_no_rule_fires_offline_is_needs_model_not_clean(norule, monkeypatch):
    monkeypatch.setattr(llm, "live_complete", boom)
    res = hybrid.run_hybrid(norule, allow_recorded=False)
    assert res["verdict"] == "NEEDS_MODEL" and res["needs_model"] and res["rules_fired"] == []
    assert res["ledger"]["calls"] == 0
    assert "NOT a clean bill of health" in res["route"]
    assert "not a statement that the pipeline is clean" in hybrid.render_report(res, norule, detail=False)


def test_recorded_run_served_without_call(tmp_path, monkeypatch):
    monkeypatch.setattr(llm, "live_complete", boom)
    root = tmp_path / "repo"
    case = root / "corpus" / "leak_group"
    shutil.copytree(NO_RULE, case)
    (root / "runs_g9").mkdir()
    (root / "runs_g9" / "r1.json").write_text(json.dumps({"loop": {"leak_group": fake_loop_rec(case, 0.1)}}), encoding="utf-8")
    res = hybrid.run_hybrid(case, root=root)
    assert res["source"] == hybrid.TAG_SPARK_REC and res["verdict"] == "INFLATED" and res["ledger"]["calls"] == 0


def test_recorded_run_never_used_for_a_case_outside_the_repo(tmp_path):
    root = tmp_path / "repo"
    (root / "runs_g9").mkdir(parents=True)
    other = tmp_path / "elsewhere" / "leak_group"
    shutil.copytree(NO_RULE, other)
    (root / "runs_g9" / "r1.json").write_text(json.dumps({"loop": {"leak_group": fake_loop_rec(other, 0.1)}}), encoding="utf-8")
    assert hybrid.find_recorded_spark(other, root) is None


def test_referee_off_by_default_and_veto_only(leaky):
    called = []

    def ref(c, ledger, live, finding):
        called.append(1)
        return {"veto": True, "reason": "mock: change alters the task", "called": True}

    meas = lambda c: (fake_rule_rec(c, 0.16), "mock")  # noqa: E731
    r0 = hybrid.run_hybrid(leaky, measure=meas, referee_fn=ref, allow_recorded=False)
    assert not called and r0["verdict"] == "INFLATED" and r0["referee"] is None
    r1 = hybrid.run_hybrid(leaky, measure=meas, referee=True, referee_fn=ref, allow_recorded=False)
    assert called and r1["verdict"] == "DISPUTED" and "Wonder" in r1["source"] and any(x["by"] == "Wonder" for x in r1["steps"])
    # veto only: a referee is never consulted on, and can never create, an inflation finding
    r2 = hybrid.run_hybrid(leaky, measure=lambda c: (fake_rule_rec(c, 0.0), "mock"), referee=True, referee_fn=ref,
                           spark_runner=lambda c, led, lv: fake_loop_rec(c, 0.0), allow_recorded=False)
    assert r2["verdict"] == "NOT INFLATED" and r2["referee"] is None and len(called) == 1


def test_ledger_caps_and_replay_costs_zero():
    led = hybrid.Ledger(max_spark=2, max_referee=10)
    for _ in range(10):
        led.check("referee")
        led.add("referee", "muse-wonder-1.0", "t", 100, 10, 0.1)
    with pytest.raises(hybrid.BudgetExceeded):
        led.check("referee")
    led.add("planner", "muse-spark-1.3", "t", 100, 10, 0.1, replayed=True)
    t = led.totals()
    assert t["calls"] == 10 and t["replayed_calls"] == 1 and t["est_usd"] == pytest.approx(1.0)
    assert hybrid.MAX_REFEREE_CALLS == 10


def test_recording_proxy_refuses_real_call_without_live_and_counts(monkeypatch):
    seen = []
    fake = lambda *a, **k: (seen.append(1), "reply")[1]  # noqa: E731
    monkeypatch.setattr(llm, "live_complete", fake)
    monkeypatch.setattr(llm, "replaying", lambda: False)
    led = hybrid.Ledger(max_spark=1)
    with hybrid.recording_llm(led, "planner", live=False):
        with pytest.raises(hybrid.NeedsModel):
            llm.live_complete("s", "u")
    assert not seen
    with hybrid.recording_llm(led, "planner", live=True):
        assert llm.live_complete("sys", "usr", est_usd=0.1, tag="x") == "reply"
        with pytest.raises(hybrid.BudgetExceeded):
            llm.live_complete("sys", "usr")
    assert led.totals()["calls"] == 1 and len(seen) == 1
    assert llm.live_complete is fake   # restored


def test_replay_mode_books_zero_dollars(monkeypatch):
    monkeypatch.setattr(llm, "live_complete", lambda *a, **k: "recorded")
    monkeypatch.setattr(llm, "replaying", lambda: True)
    led = hybrid.Ledger()
    with hybrid.recording_llm(led, "planner", live=False):
        assert llm.live_complete("s", "u", est_usd=0.1) == "recorded"
    assert led.totals()["est_usd"] == 0.0 and led.totals()["replayed_calls"] == 1


def test_cli_offline_default_makes_no_model_call(leaky, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(llm, "live_complete", boom)
    monkeypatch.setattr(hybrid, "default_measure", lambda c, fresh=False, root=ROOT: (fake_rule_rec(c, 0.2), "mock"))
    rep = tmp_path / "r.md"
    assert hybrid.main([str(leaky), "--out", str(tmp_path / "o"), "--report", str(rep), "--no-recorded"]) == 0
    out = capsys.readouterr().out
    assert "INFLATED" in out and "rules (no model)" in out and "est $0.00" in out
    assert rep.exists() and "Full audit report" in rep.read_text(encoding="utf-8")
