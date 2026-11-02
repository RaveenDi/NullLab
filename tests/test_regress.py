"""eval/regress.py: zero unexplained verdict flips on saved G5/G6/G7 plans; G7 failures recover in replay. Offline, read-only."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval import regress  # noqa: E402


def test_zero_unexplained_flips_on_saved_plans():
    rows, unexplained, now, known = regress.replay_saved()
    assert len(rows) >= 60
    assert unexplained == [], unexplained
    for f in now + known:
        assert f["cause"]  # every flip carries a cause


def test_split_use_flips_are_exactly_the_known_civilwar_apparent_plans():
    _, _, now, _ = regress.replay_saved()
    sp = [f for f in now if "split_required" in f["cause"]]
    assert {(f["gen"], f["case"]) for f in sp} == {("g6", "civilwar_apparent")} and len(sp) == 3


def test_g7_failures_recover_in_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("NULLLAB_G8_OUT", str(tmp_path))
    out = regress.replay_g7_failures()
    assert out["label"] == "replay, not a result"
    c = out["cases"]
    assert c["r3_crash"]["recovered_past_failure"] and c["r3_crash"]["stderr_fed_back"]
    assert c["r3_crash"]["repaired_split_runs_on_real_data"]["test_epochs_all_later"]
    assert c["r4_bad_json"]["recovered_past_failure"] and c["r4_bad_json"]["bad_reply_fed_back"]
    assert c["bad_json_twice"]["g8_label"] == "INCONCLUSIVE (harness failure: bad_json)"
    assert c["r3_crash"]["planner_side_calls"] <= 4 and c["r4_bad_json"]["planner_side_calls"] <= 4
