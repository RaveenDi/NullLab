"""Tests for agent/ci_check.py. Offline: sandbox measurement is a mock; any model call fails the test."""
import os
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from agent import ci_check, hybrid, llm  # noqa: E402
from tests.test_hybrid import fake_rule_rec  # noqa: E402

LEAKY, CLEAN = ROOT / "corpus" / "leak_prescale", ROOT / "corpus" / "clean_control"
pytestmark = pytest.mark.skipif(not (LEAKY / "data.csv").exists() or not (CLEAN / "data.csv").exists(), reason="corpus not present")


@pytest.fixture(autouse=True)
def no_model(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("ci_check rules-only must never call a model")
    monkeypatch.setattr(llm, "live_complete", boom)


@pytest.fixture
def tree(tmp_path):
    shutil.copytree(LEAKY, tmp_path / "proj" / "bad")
    shutil.copytree(CLEAN, tmp_path / "proj" / "good")
    (tmp_path / "proj" / ".venv" / "lib").mkdir(parents=True)
    shutil.copytree(LEAKY, tmp_path / "proj" / ".venv" / "lib" / "ignored")
    return tmp_path / "proj"


def meas(drop):
    return lambda c: (fake_rule_rec(c, drop), "mock measurement")


def test_discovery_skips_venv_and_finds_cases(tree):
    assert [p.name for p in ci_check.discover_cases(tree)] == ["bad", "good"]
    assert [p.name for p in ci_check.discover_cases(tree / "bad")] == ["bad"]


def test_inflation_above_threshold_fails_with_clear_message(tree):
    # the clean case is measured too if a rule fires; here only "bad" fires R2
    out = ci_check.check_path(tree, threshold=0.05, measure=meas(0.16))
    assert out["exit_code"] == 1
    msg = [m for m in out["messages"] if m.startswith("bad:")][0]
    assert "inflated by +16.0 pp" in msg and "threshold of 5 pp" in msg and "95% interval above 0" in msg and "rules (no model)" in msg
    assert "## NullLab audit" in out["markdown"] and "**FAIL**" in out["markdown"] and "rules only (no model, $0, no secrets)" in out["markdown"]


def test_below_threshold_or_ci_spanning_zero_passes(tree):
    assert ci_check.check_path(tree / "bad", threshold=0.30, measure=meas(0.16))["exit_code"] == 0
    # drop large but interval spans 0 (half width 0.2 around 0.05): sign '0' -> rules and measurement disagree -> not a FAIL
    from tests import test_hybrid as th
    def wide(c):
        r = fake_rule_rec(c, 0.05)
        r["stats"] = th.fake_stats(0.05, half=0.2)
        return r, "mock"
    out = ci_check.check_path(tree / "bad", threshold=0.01, measure=wide)
    assert out["exit_code"] == 2 and out["rows"][0]["status"] == "UNRESOLVED"


def test_clean_case_no_rule_fired_is_not_reported_as_cleared(tree):
    out = ci_check.check_path(tree / "good", measure=meas(0.0))
    assert out["exit_code"] == 2 and out["rows"][0]["status"] == "NO_RULE_FIRED"
    assert ci_check.check_path(tree / "good", measure=meas(0.0), strict=False)["exit_code"] == 0
    assert "NOT CHECKED" in out["markdown"] and "Look-ahead features" in out["markdown"]
    assert out["rows"][0]["calls"] == 0 and out["rows"][0]["est_usd"] == 0.0


def test_no_case_found_exits_2(tmp_path):
    out = ci_check.check_path(tmp_path)
    assert out["exit_code"] == 2 and "no case found" in out["messages"][0]


def test_missing_information_cannot_pass_strict_ci(tree, monkeypatch):
    from agent import engine

    monkeypatch.setattr(engine, "run_audit", lambda c, *a, **kw: {"case": c.name, "mode": "live", "verdict": "NEEDS_INFORMATION", "summary": None, "ledger": {"calls": 0, "est_usd": 0}})
    out = ci_check.check_path(tree / "good")
    assert out["exit_code"] == 2
    assert out["rows"][0]["status"] == "UNRESOLVED"


def test_measurement_failure_is_not_a_pass_or_a_fail(tree):
    out = ci_check.check_path(tree / "bad", measure=lambda c: ({"status": "error", "stderr": "boom"}, "mock"))
    assert out["rows"][0]["status"] == "ERROR" and out["exit_code"] == 2
    assert "MEASUREMENT_FAILED" in out["messages"][0]


def test_main_writes_job_summary_and_exit_code(tree, tmp_path, monkeypatch, capsys):
    from agent import engine
    monkeypatch.setattr(engine, "run_audit", lambda c, *a, **kw: {"case":c.name,"mode":"rules","verdict":"INFLATED","summary":hybrid.summarize(fake_rule_rec(c,0.2)),"ledger":{"calls":0,"est_usd":0}})
    summ = tmp_path / "summary.md"
    code = ci_check.main([str(tree / "bad"), "--threshold", "0.05", "--summary", str(summ)])
    assert code == 1
    text = summ.read_text(encoding="utf-8")
    assert text.startswith("## NullLab audit") and "FAIL" in text
    assert "FAILED" in capsys.readouterr().err


def test_spark_flag_refused_without_live_and_key(tree, monkeypatch, capsys):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert ci_check.main([str(tree / "bad"), "--spark"]) == 2
    assert "MODEL_API_KEY" in capsys.readouterr().err


def test_workflow_file_is_rules_only_and_secret_free():
    wf = (ROOT / ".github" / "workflows" / "nulllab-audit.yml").read_text(encoding="utf-8")
    assert "agent.ci_check" in wf and "$GITHUB_STEP_SUMMARY" in wf
    assert "secrets." not in wf.replace("repository secret", "")   # no secret is referenced
    assert "--spark" not in [ln for ln in wf.splitlines() if not ln.lstrip().startswith("#")].__str__()
