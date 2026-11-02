"""EHG runner tests: case mapping, no truth in the agent view, isolation from runs_g8, LF-normalised freeze/verify, caps,
acceptance scoring, run stage with mocks. Offline: no API call, nothing is written under runs*/ (tmp dirs only)."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import factorial_ehg as ehg, factorial_g7 as g7, factorial_g8 as g8, llm  # noqa: E402
from agent.factorial import agent_view  # noqa: E402


@pytest.fixture
def env(monkeypatch, tmp_path):
    for k in ("NULLLAB_EHG_OUT", "NULLLAB_PHASE", "NULLLAB_G8_OUT", "NULLLAB_G8_LOG", "NULLLAB_TRACES"):
        monkeypatch.setenv(k, "x")
    monkeypatch.setenv("NULLLAB_EHG_OUT", str(tmp_path / "ehg"))
    monkeypatch.setenv("NULLLAB_MODEL", "muse-spark-1.3-contributor")
    monkeypatch.setattr(llm, "MAX_G8_CALLS", 70)
    monkeypatch.setattr(g8, "CEILING_USD", 5.0)
    return tmp_path / "ehg"


def test_case_mapping_and_constants():
    assert set(ehg.CASES) == {"ehg_disguised", "ehg_disguised_clean"}
    assert all((p / "train.py").exists() for p in ehg.CASES.values())
    assert ehg.N_REPEATS == 3 and ehg.TEMPERATURE == 0.7 and ehg.TOTAL_CALL_CAP == 40 and g8.CASE_CALL_CAP == 4
    assert g8.DEFAULT_MODEL == ehg.DEFAULT_MODEL == "muse-spark-1.3-contributor"
    assert 6 * (1 + g8.CASE_CALL_CAP) <= ehg.TOTAL_CALL_CAP


def test_truth_never_in_agent_view_or_prompts():
    blob = "\n".join(agent_view(d) + g8.factorial_g5.user_msg(d, "r") for d in ehg.CASES.values()) + g8.SYSTEM + g8.B3_SYSTEM
    for bad in ("0.430", "0.43 ", "0.494", "49.4", "SMOTE", "TPEHG", "Vandewiele", "preterm", "g8_truth"):
        assert bad not in blob, bad


def test_split_use_required_does_not_apply_to_this_pair():
    for d in ehg.CASES.values():
        assert g7.forecast_claim((d / "excerpt.md").read_text(encoding="utf-8")) == []
        assert g7.check_split_required((d / "train.py").read_text(encoding="utf-8"), (d / "excerpt.md").read_text(encoding="utf-8"), [], {}) == []


def test_truth_constants_match_truth_file():
    t = ehg.truth_check()
    assert t["range_ok"] and t["max_row_ok"] and t["stored_truth"] == 0.494
    ref = ROOT / "runs_g8_cases" / "reference.json"
    if ref.exists():
        r = json.loads(ref.read_text(encoding="utf-8"))
        a, c = r["roc_auc_by_case"]["ehg_apparent"], r["roc_auc_by_case"]["ehg_clean"]
        assert abs(sum(a) / len(a) - sum(c) / len(c) - ehg.REFERENCE_INFLATION) < 0.002


def test_configure_isolates_from_runs_g8(env):
    d = ehg.configure()
    assert d == env
    assert Path(llm.g8_log()).parent == env and Path(llm.trace_file()).parent == env and g8.out_dir() == env
    assert llm.MAX_G8_CALLS == 40 and g8.CEILING_USD == ehg.CEILING_USD


def test_configure_refuses_runs_g8(monkeypatch, env):
    monkeypatch.setenv("NULLLAB_EHG_OUT", str(ROOT / "runs_g8"))
    with pytest.raises(SystemExit):
        ehg.configure()


def test_projection_within_caps(env, capsys):
    pj = ehg.project()
    assert pj["within_total_cap"] and pj["max_live_calls_total"] == 30 and pj["worst_case_usd"] <= pj["ceiling_usd"]


# ---------------- hashing ----------------
def test_hash_is_lf_normalised(tmp_path):
    a, b = tmp_path / "a.txt", tmp_path / "b.txt"
    a.write_bytes(b"x = 1\r\ny = 2\r\n")
    b.write_bytes(b"x = 1\ny = 2\n")
    assert ehg.sha_file(a) == ehg.sha_file(b) == hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()


def _freeze_setup(monkeypatch, tmp_path, env):
    f, doc = tmp_path / "code.py", tmp_path / "doc.md"
    f.write_bytes(b"a = 1\r\n")
    doc.write_text("prereg\n", encoding="utf-8")
    monkeypatch.setattr(ehg, "CODE_FILES", (str(f),))
    monkeypatch.setattr(ehg, "DOC", str(doc))
    return f, doc


def test_freeze_log_equals_independent_recompute_and_detects_change(monkeypatch, tmp_path, env):
    f, doc = _freeze_setup(monkeypatch, tmp_path, env)
    ehg.freeze()
    recs = [json.loads(x) for x in (env / "prereg_log.jsonl").read_text().splitlines()]
    src = next(r for r in recs if r["kind"] == "ehg_source_hashes")
    # a verifier that knows only the stated rule gets the logged value
    assert src["payload"][str(f)] == hashlib.sha256(f.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    assert src["sha256"] == hashlib.sha256(json.dumps(src["payload"], sort_keys=True).encode()).hexdigest()
    assert ehg.verify_problems() == []
    # line endings alone do not break verification
    f.write_bytes(b"a = 1\n")
    assert ehg.verify_problems() == []
    f.write_bytes(b"a = 2\n")
    assert any("ehg_source_hashes" in p for p in ehg.verify_problems())
    f.write_bytes(b"a = 1\n")
    doc.write_text("edited\n", encoding="utf-8")
    assert any("prereg doc" in p for p in ehg.verify_problems())


def test_verify_fails_without_freeze(monkeypatch, tmp_path, env):
    _freeze_setup(monkeypatch, tmp_path, env)
    ehg.configure()
    assert any("no freeze record" in p for p in ehg.verify_problems())


def test_prompt_bundle_equals_g8_frozen_value():
    assert ehg.prompt_hashes()["bundle_sha256_g8_compatible"] == "40dc30fee676823fd090bea16586731a136f033b0ac845f8946ce32073d04bf9"


# ---------------- scoring ----------------
def _ok(infl, ci=(0.2, 0.6)):
    return {"status": "ok", "calls": [{"est_usd": 0.1, "real_total_tokens": 5}], "retries": 0,
            "stats": {s: {"full": {"drop": {"fix_both": infl}, "drop_ci": {"fix_both": list(ci)}}} for s in ("42", "43", "44")}}


def _nul():
    return _ok(0.0, (-0.05, 0.05))


def _inc(kind="guard"):
    return {"status": "INCONCLUSIVE", "harness_failure": kind, "label": f"INCONCLUSIVE (harness failure: {kind})", "reason": ["x"], "calls": [1, 2]}


def test_pass_case():
    s = ehg.score_cases({ehg.LEAKY: {"r1": _ok(0.43), "r2": _ok(0.5), "r3": _ok(0.30)}, ehg.CLEAN: {f"r{i}": _nul() for i in (1, 2, 3)}})
    a = s["acceptance"]
    assert a["PASS"] and a["a_direction_right"] == 3 and a["c_magnitude_within_0.15_of_0.43"] == 3 and a["harness_target_met"]


def test_magnitude_needs_two_of_three_and_boundary():
    clean = {f"r{i}": _nul() for i in (1, 2, 3)}
    assert ehg.score_cases({ehg.LEAKY: {"r1": _ok(0.43), "r2": _ok(0.58), "r3": _ok(0.9)}, ehg.CLEAN: clean})["acceptance"]["PASS"]
    s = ehg.score_cases({ehg.LEAKY: {"r1": _ok(0.43), "r2": _ok(0.9), "r3": _ok(0.1)}, ehg.CLEAN: clean})["acceptance"]
    assert s["c_magnitude_within_0.15_of_0.43"] == 1 and not s["PASS"]


def test_harness_inconclusive_is_denominator_not_false_alarm():
    s = ehg.score_cases({ehg.LEAKY: {"r1": _ok(0.43), "r2": _ok(0.43), "r3": _inc("crash")}, ehg.CLEAN: {"r1": _nul(), "r2": _nul(), "r3": _inc("bad_json")}})
    a = s["acceptance"]
    assert not a["PASS"] and a["a_direction_right"] == 2 and a["b_clean_false_alarms"] == 0 and a["harness_inconclusive"] == 2
    assert a["denominator_leaky"] == 3 and len(s["harness_failures"]) == 2
    assert s["cases"][ehg.LEAKY]["r3"]["label"] == "INCONCLUSIVE (harness failure: crash)"


def test_clean_false_alarm_and_wrong_direction_fail():
    leaky = {f"r{i}": _ok(0.43) for i in (1, 2, 3)}
    assert not ehg.score_cases({ehg.LEAKY: leaky, ehg.CLEAN: {"r1": _ok(0.2), "r2": _nul(), "r3": _nul()}})["acceptance"]["PASS"]
    assert not ehg.score_cases({ehg.LEAKY: dict(leaky, r3=_nul()), ehg.CLEAN: {f"r{i}": _nul() for i in (1, 2, 3)}})["acceptance"]["PASS"]


def test_missing_repeats_cannot_pass():
    assert not ehg.score_cases({ehg.LEAKY: {"r1": _ok(0.43), "r2": _ok(0.43)}, ehg.CLEAN: {"r1": _nul(), "r2": _nul()}})["acceptance"]["PASS"]


def test_b3_row():
    ok = lambda leak, fb: {"ans": {"leak": leak, "predicted_drop_pp": {"fix_both": fb}}}  # noqa: E731
    assert ehg.b3_row(ok(True, 40), ehg.LEAKY)["gets_it"] is True
    assert ehg.b3_row(ok(True, 10), ehg.LEAKY)["gets_it"] is False
    assert ehg.b3_row(ok(False, 40), ehg.LEAKY)["gets_it"] is False
    assert ehg.b3_row(ok(True, 5), ehg.CLEAN)["false_alarm"] is True
    assert "error" in ehg.b3_row({"error": "x"}, ehg.LEAKY)


# ---------------- run stage with mocks ----------------
def test_run_refuses_without_freeze(monkeypatch, env):
    monkeypatch.setattr(llm, "live_complete_ex", lambda *a, **k: pytest.fail("live call"))
    with pytest.raises(SystemExit):
        ehg.run(["1"])


def test_run_stage_mocked(monkeypatch, env):
    calls = []

    def fake_llm(system, user, **kw):
        calls.append(kw["tag"])
        return json.dumps({"leak": True, "A": "a", "B": "b", "predicted_drop_pp": {"fix_A": 1, "fix_B": 1, "fix_both": 40},
                           "culprit_ranking": ["A"], "confidence": 0.5, "reason": "r"}), {"total_tokens": 5}

    monkeypatch.setattr(ehg, "verify_problems", lambda: [])
    monkeypatch.setattr(llm, "live_complete_ex", fake_llm)
    monkeypatch.setattr(g8, "pipeline", lambda case_dir, rid, model=None, **k: dict(_ok(0.43), rid=rid, status="ok"))
    ehg.run(["1", "2", "3"])
    assert calls == ["ehg_b3"] * 6
    for r in (1, 2, 3):
        d = json.loads((env / f"r{r}.json").read_text())
        assert set(d["loop"]) == set(ehg.CASES) and set(d["b3"]) == set(ehg.CASES) and d["loop"][ehg.LEAKY]["rid"] == f"ehg-r{r}"
    out = ehg.score()
    assert out["acceptance"]["a_direction_right"] == 3 and out["acceptance"]["b3_gets_it_leaky"] == 3
    assert out["acceptance"]["b3_false_alarms_clean"] == 3 and out["acceptance"]["b_clean_false_alarms"] == 3  # mock returns +0.43 on clean too
    assert (env / "score.json").exists()


def test_run_rejects_bad_repeat(monkeypatch, env):
    monkeypatch.setattr(ehg, "verify_problems", lambda: [])
    with pytest.raises(SystemExit):
        ehg.run(["4"])


def test_total_call_cap_is_enforced_on_our_log(monkeypatch, env):
    """llm.live_complete_ex counts attempts in OUR log against llm.MAX_G8_CALLS (=40) before any network use."""
    ehg.configure()
    log = Path(llm.g8_log())
    log.write_text("".join(json.dumps({"est_usd": 0.01}) + "\n" for _ in range(40)))
    monkeypatch.setattr(llm, "spend_ok", lambda *a, **k: pytest.fail("reached the network path"))
    with pytest.raises(llm.LiveNotAllowed):
        llm.live_complete_ex("s", "u", tag="t", role="b3")
    # pipeline-level: a refused call is a harness failure (api_error), not a verdict
    rec = g8.pipeline(ehg.CASES[ehg.LEAKY], "ehg-r1", model="m")
    assert rec["status"] == "INCONCLUSIVE" and rec["harness_failure"] == "api_error"


def test_guard_on_ehg_plans_offline(monkeypatch, env):
    """Static guard only (no sandbox, no model): a two-step fit_scope fix A passes; a lone 'drop oversampling' edit is
    rejected as MODEL changed (documented risk: expect INCONCLUSIVE (guard) if the planner never finds the first form)."""
    d = ehg.CASES[ehg.LEAKY]
    ce = "def claimed_eval(df, seed):\n    X = df[feats(df)].to_numpy(dtype=float)\n    y = df[TARGET].to_numpy().astype(int)\n    return cv_scores(X, y, seed)\n"
    ft = "def fold_train_set(X_tr, y_tr, seed):\n    return oversample(X_tr, y_tr, seed)\n"
    base = {"A": "a", "B": "b", "predicted_drop_pp": {"fix_A": 1, "fix_B": 1, "fix_both": 40}, "culprit_ranking": ["A"], "reason": "r"}
    lone = dict(base, edits={"A": {"kind": "fit_scope", "steps": {"fold_train_set": ft}}, "B": {"kind": "fit_scope", "steps": {"claimed_eval": ce}}})
    _, probs, _ = g7.guard(d, lone)
    assert any("MODEL changed" in p for p in probs)
    cvs = "".join(l + "\n" for l in (
        "def cv_scores(X, y, seed):",
        "    ys, ps = [], []",
        "    for tr, te in StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed).split(X, y):",
        "        Xa, ya = fold_train_set(X[tr], y[tr], seed)",
        "        model = RandomForestClassifier(n_estimators=N_TREES, random_state=seed).fit(Xa, ya)",
        "        ys.append(y[te])",
        "        ps.append(model.predict_proba(X[te])[:, 1])",
        "    return np.concatenate(ys), np.concatenate(ps)"))
    two = dict(base, edits={"A": {"kind": "fit_scope", "steps": {"claimed_eval": ce, "fold_train_set": ft}},
                            "B": {"kind": "fit_scope", "steps": {"cv_scores": cvs}}})
    _, probs, _ = g7.guard(d, two)
    assert probs == []
