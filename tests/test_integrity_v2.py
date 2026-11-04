"""Regression tests for the failure modes found by the architecture review."""

import json
from pathlib import Path
import shutil

import pytest

from agent import evidence, hybrid, transport, llm
from sandbox.factorial_stats import factorial_stats, CONFIGS

ROOT = Path(__file__).resolve().parents[1]


def test_evidence_refuses_changed_inputs_and_patch(tmp_path):
    case = tmp_path / "case"
    shutil.copytree(ROOT / "examples" / "secom_clean", case)
    rec = {"sources": {"fix": "source"}}
    rec["evidence"] = evidence.capture(case, sources=rec["sources"], context={"seeds": [42]})
    assert evidence.verify(case, rec)
    rec["sources"]["fix"] = "changed"
    with pytest.raises(evidence.EvidenceError, match="patch"):
        evidence.verify(case, rec)
    rec["sources"]["fix"] = "source"
    (case / "data.csv").write_text((case / "data.csv").read_text() + "\n")
    with pytest.raises(evidence.EvidenceError, match="input mismatch"):
        evidence.verify(case, rec)


@pytest.mark.parametrize("y,p", [([0, 1], [1]), ([[0], [1]], [0, 1]), ([0, 1], [0, float("nan")]), ([], [])])
def test_invalid_predictions_are_rejected(y, p):
    with pytest.raises(ValueError):
        factorial_stats({k: {"y": y, "p": p} for k in CONFIGS}, n_boot=10)


def test_mixed_evidence_is_inconclusive():
    assert hybrid._verdict_from({"sign": "mixed"}) == "INCONCLUSIVE"


def test_installed_legacy_transport_replay_does_not_recurse(tmp_path):
    p = tmp_path / "trace.jsonl"
    p.write_text(json.dumps({"key": llm.prompt_key("s", "u", llm.MODEL), "reply": "ok"}) + "\n")
    llm.set_replay(p)
    transport.install()
    try:
        assert llm.live_complete_ex("s", "u")[0] == "ok"
    finally:
        transport.uninstall()
        llm.set_replay(None)


def test_negated_forecasting_is_not_a_forecast():
    from agent.contract_g9 import forecast_claim

    assert not forecast_claim("Retrospective screening, not a forecast or a future use.")
    assert forecast_claim("Predict outcomes in the future period.")
    assert not forecast_claim("Independent records with no group or chronological structure.")
    assert not forecast_claim("The task does not use temporal or future information.")
    assert forecast_claim("Not a retrospective classifier, but forecast the future period.")
    assert forecast_claim("Not only forecasting but also retrospective analysis.")
