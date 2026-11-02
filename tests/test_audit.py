"""Tests for agent/audit.py (the reviewer report). Offline and deterministic: fixtures are written to pytest temp dirs; the report is built
from them without any API call, and no existing runs*/ output is touched."""
import hashlib
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["NULLLAB_NO_DOCKER"] = "1"

from agent import audit, fidelity  # noqa: E402
from eval import g5_fixtures as fx  # noqa: E402

PUMP = ROOT / "factorial" / "g4_pump_inspection"
needs_pump = pytest.mark.skipif(not (PUMP / "train.py").exists(), reason="pump case not in the repository")


def _stats(sign="+"):
    """Hand-made, fixed numbers in the shape written by sandbox/factorial_stats.all_seeds."""
    out = {}
    for s, d in (("42", 0.16), ("43", 0.15), ("44", 0.17)):
        lo, hi = (d - 0.05, d + 0.05) if sign == "+" else (-0.04, 0.05)
        dd = d if sign == "+" else 0.005
        out[s] = {"full": {"acc": {"orig": 0.89, "fix_A": 0.89, "fix_B": 0.89 - dd, "fix_both": 0.89 - dd},
                           "n": {"orig": 780, "fix_A": 780, "fix_B": 780, "fix_both": 780},
                           "drop": {"fix_A": 0.0, "fix_B": dd, "fix_both": dd}, "drop_ci": {"fix_A": [-0.03, 0.03], "fix_B": [lo, hi], "fix_both": [lo, hi]},
                           "I": 0.0, "I_ci": [-0.03, 0.03], "I_excludes_0": False}}
    return out


def _loop_fixture(tmp_path, sign="+", probe=None):
    """A loop run of the pump case with the structured GOOD_PUMP edits, as a g5-style r1.json."""
    src = (PUMP / "train.py").read_text(encoding="utf-8")
    cfgs = fidelity.build_configs(src, fx.GOOD_PUMP)
    run = tmp_path / "runs_x"
    run.mkdir()
    rec = {"status": "ok", "retries": 0, "stats": _stats(sign), "metric": "accuracy",
           "final_plan": {"A": "SelectKBest ANOVA feature selection is fit on all rows before the split", "B": "shift(-1) lag looks ahead to the next inspection",
                          "edits": fx.GOOD_PUMP, "predicted_drop_pp": {"fix_A": 1, "fix_B": 12, "fix_both": 13}},
           "fidelity": {"fix_both": "only step(s) add_lag, select changed (fit_scope/feature)"},
           "sources": {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}, "log": []}
    (run / "r1.json").write_text(json.dumps({"repeat": "g5-r1", "loop": {"g4_pump_inspection": rec}}), encoding="utf-8")
    (run / "prereg_log.jsonl").write_text("\n".join(json.dumps(x) for x in (
        {"kind": "scoring_rule", "case": None, "repeat": None, "utc": "2026-11-01T07:33:46Z", "sha256": "a" * 64},
        {"kind": "loop_planner", "case": "g4_pump_inspection", "repeat": "g5-r1", "utc": "2026-11-01T07:35:41Z", "sha256": "b" * 64})) + "\n", encoding="utf-8")
    return run


def _build(run, **kw):
    return audit.build_finding(PUMP, run=run / "r1.json", **kw)


@needs_pump
def test_report_has_every_required_element(tmp_path):
    F = _build(_loop_fixture(tmp_path))
    out = audit.write_report(F, tmp_path / "rep.html").read_text(encoding="utf-8")
    for needle in ("Claim as stated", "Claimed vs controlled", "95% interval of drop", "UNPAIRED bootstrap", "Exact patch", "only add_lag, select changed",
                   "Fidelity check", "Preregistration", "b" * 64, "2026-11-01T07:35:41Z", "Rerun", "python -m agent.audit", "What we could not test",
                   "SYNTHETIC", "Kapoor and Narayanan", "arXiv:2207.07048", "Suggested note to the authors", "Copy as reviewer note"):
        assert needle in out, needle
    assert "seed" in out and "42" in out and "780" in out                       # seeds and n are shown
    assert "L1.3" in out                                                          # selection-before-split mapped
    assert 'class="diff"' in out and "<span class=\"add\">" in out                # the diff is rendered


@needs_pump
def test_report_is_deterministic_and_light_orange(tmp_path):
    run = _loop_fixture(tmp_path)
    a = audit.write_report(_build(run), tmp_path / "a.html").read_bytes()
    b = audit.write_report(_build(run), tmp_path / "b.html").read_bytes()
    assert a == b
    t = a.decode()
    assert "#F2EFEA" in t and "#E8501F" in t and "#111111" in t


@needs_pump
def test_no_external_requests(tmp_path):
    t = audit.write_report(_build(_loop_fixture(tmp_path)), tmp_path / "r.html").read_text(encoding="utf-8")
    assert not re.search(r"<(script|link|img|iframe)[^>]+(src|href)=", t, re.I)
    assert "@import" not in t and "url(" not in t and "http://" not in t and "https://" not in t
    assert "fetch(" not in t and "XMLHttpRequest" not in t


@needs_pump
def test_copy_note_is_about_150_words_and_has_no_markup(tmp_path):
    F = _build(_loop_fixture(tmp_path))
    n = len(F["note_short"].split())
    assert 110 <= n <= 190, n
    assert "<" not in F["note_short"] and "**" not in F["note_short"]
    assert "Kapoor and Narayanan" in F["note_short"] and "not the authors' full pipeline" in F["note_short"]


@needs_pump
def test_markdown_output(tmp_path):
    p = audit.write_report(_build(_loop_fixture(tmp_path)), tmp_path / "r.md")
    t = p.read_text(encoding="utf-8")
    assert t.startswith("# Audit: g4_pump_inspection") and "```diff" in t and "## 10. Copy as reviewer note" in t


@needs_pump
def test_a_null_finding_is_not_written_as_a_leak(tmp_path):
    F = _build(_loop_fixture(tmp_path, sign="0"))
    assert F["meas"]["sign"] == "0"
    txt = " ".join(F["note_paragraphs"]) + F["note_short"]
    assert "No evidence of inflation" in F["note_short"] and "may be inflated" not in txt and "not proof" in txt


@needs_pump
def test_reaudit_matches_and_detects_tampered_sources(tmp_path):
    run = _loop_fixture(tmp_path)
    F = _build(run)
    assert F["audit"]["problems"] == [] and all(F["audit"]["sources_match"].values())
    j = json.loads((run / "r1.json").read_text())
    j["loop"]["g4_pump_inspection"]["sources"]["fix_both"] += "\n# tampered\n"
    (run / "r1.json").write_text(json.dumps(j), encoding="utf-8")
    assert not _build(run)["audit"]["sources_match"]["fix_both"]


@needs_pump
def test_audit_does_not_modify_inputs(tmp_path):
    run = _loop_fixture(tmp_path)
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir()}
    audit.main([str(PUMP), "--run", str(run / "r1.json"), "--report", str(tmp_path / "o.html")])
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in run.iterdir()}
    assert (tmp_path / "o.html").exists()


def test_run_dir_with_several_cases_needs_a_case(tmp_path):
    run = tmp_path / "runs_y"
    run.mkdir()
    (run / "r1.json").write_text(json.dumps({"loop": {"a": {"status": "ok"}, "b": {"status": "ok"}}}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        audit.locate(run)
    assert "--case" in str(e.value)
    with pytest.raises(SystemExit):
        audit.main([str(tmp_path / "nope"), "--report", str(tmp_path / "x.html")])


def test_taxonomy_mapping_by_description_and_kind():
    meas = {"mean_A": 0.2, "mean_B": 0.0, "mean_drop": 0.2}

    def top(a, b="nothing relevant here", kinds=("split", "split")):
        rec = {"final_plan": {"A": a, "B": b, "edits": {"A": {"kind": kinds[0]}, "B": {"kind": kinds[1]}}}}
        return audit.classify(rec, "loop", "", meas)[0]["type"]
    assert top("split_rows returns train==test (in-sample scoring)") == "L1.1"
    assert top("StandardScaler and PCA are fit on all rows", kinds=("fit_scope", "split")) == "L1.2"
    assert top("screening with SelectKBest before the split") == "L1.3"
    assert top("duplicate rows sit on both sides") == "L1.4"
    assert top("a column is derived from the label", kinds=("feature", "split")) == "L2"
    assert top("forecast evaluated on a random split, future years leak") == "L3.1"
    assert top("the same patient appears in train and test") == "L3.2"
    assert audit.classify({"final_plan": {"A": "", "B": "", "edits": {}}}, "loop", "", meas) == []


def test_taxonomy_for_rule_records_and_taxonomy_is_complete():
    assert set(audit.TAXONOMY) == {"L1.1", "L1.2", "L1.3", "L1.4", "L2", "L3.1", "L3.2", "L3.3"}
    rec = {"configs": {"fix_A": {"rules_applied": ["R4", "R1"]}, "fix_B": {"rules_applied": ["R2"]}, "fix_both": {"rules_applied": ["R4", "R1", "R2"]}},
           "fired": {"R2": {"transformers": ["SelectKBest"]}}}
    t = audit.classify(rec, "rulefix", "", {"mean_A": 0.3, "mean_B": 0.0, "mean_drop": 0.3})
    assert [x["type"] for x in t] == ["L1.1", "L3.1", "L1.3"]                   # factor A (carries the drop) first, taxonomy order within it


def test_provenance_badges(tmp_path):
    cand = {"dir": Path("runs_g6"), "rec": {}}
    assert audit.provenance(ROOT / "real" / "civilwar_apparent", "civilwar_apparent", cand)[0] in ("REAL-PINNED", "SYNTHETIC")
    if (ROOT / "eval" / "g6_truth.json").exists():
        assert audit.provenance(ROOT / "real" / "civilwar_apparent", "civilwar_apparent", cand)[0] == "REAL-PINNED"
        assert audit.provenance(ROOT / "real" / "esl_selection", "esl_selection", cand)[0] == "TEXTBOOK"
    assert audit.provenance(PUMP, "g4_pump_inspection", cand)[0] == "SYNTHETIC"
    assert audit.provenance(PUMP, "g4_pump_inspection", {"dir": Path("runs_mock3"), "rec": {}})[0] == "MOCK"


def test_rulefix_record_report_and_remeasure_roundtrip(tmp_path):
    """A rule-baseline record (tiny scratch case) is auditable, and --remeasure reproduces the stored drop exactly."""
    from eval import run_rulefix as rr
    case = tmp_path / "factorial" / "scratch_case"
    case.mkdir(parents=True)
    rng = np.random.default_rng(0)
    df = pd.DataFrame(rng.normal(size=(200, 4)), columns=list("abcd"))
    df["y"] = rng.integers(0, 2, 200)
    df.to_csv(case / "data.csv", index=False)
    (case / "excerpt.md").write_text("## Methods (excerpt)\nWe fit a logistic model.\n## Results\nOur model reaches 80% accuracy.\n", encoding="utf-8")
    (case / "train.py").write_text(
        "import numpy as np\nimport pandas as pd\nfrom sklearn.linear_model import LogisticRegression\nTARGET = 'y'\n\n\n"
        "def load(path='data.csv'):\n    return pd.read_csv(path)\n\n\ndef feats(df):\n    return [c for c in df.columns if c != TARGET]\n\n\n"
        "def split_rows(df, seed):\n    idx = np.arange(len(df))\n    return idx, idx\n\n\n"
        "def claimed_eval(df, seed):\n    tr, te = split_rows(df, seed)\n    f = feats(df)\n"
        "    m = LogisticRegression(max_iter=300).fit(df[f].to_numpy()[tr], df[TARGET].to_numpy()[tr])\n"
        "    return df[TARGET].to_numpy()[te], m.predict(df[f].to_numpy()[te])\n", encoding="utf-8")
    runs = tmp_path / "runs_rf"
    runs.mkdir()
    rec = rr.run_case(case, seeds=(42, 43, 44), n_boot=60, timeout=600)
    assert rec["status"] == "ok", rec.get("stderr")
    (runs / "scratch_case.json").write_text(json.dumps(rec), encoding="utf-8")
    (runs / "PREREG.sha256").write_text("c" * 64 + "  PREREG.md\n", encoding="utf-8")
    rm = audit.remeasure(case, run=runs / "scratch_case.json", n_boot=60)
    assert rm["status"] == "ok" and rm["max_abs_delta_drop"] < 1e-12
    F = audit.build_finding(case, run=runs / "scratch_case.json", remeasure=rm)
    assert F["kind"] == "rulefix" and F["steps_changed"] == ["split_rows"] and F["prereg"]["prereg_md_sha256"] == "c" * 64
    assert F["types"][0]["type"] == "L1.1"
    t = audit.write_report(F, tmp_path / "rf.html").read_text(encoding="utf-8")
    assert "Re-measurement" in t and "RULEFIX RUN" in t


@pytest.mark.skipif(not (ROOT / "runs_g6" / "r1.json").exists() or not (ROOT / "real" / "civilwar_apparent" / "excerpt.md").exists(),
                    reason="no committed g6 run")
def test_real_run_sample_reports_build_from_existing_files(tmp_path):
    for case in ("civilwar_apparent", "esl_selection"):
        F = audit.build_finding(ROOT / "real" / case)
        t = audit.write_report(F, tmp_path / f"{case}.html").read_text(encoding="utf-8")
        assert F["provenance"] in ("REAL-PINNED", "TEXTBOOK") and F["meas"]["sign"] == "+"
        assert F["prereg"]["records"] and "Neunhoeffer" in t if case == "civilwar_apparent" else "Hastie" in t
        assert F["audit"]["problems"] == [] and all(F["audit"]["sources_match"].values())
