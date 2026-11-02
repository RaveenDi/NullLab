"""Tests for report/ (the demo page): payload honesty, banned words, defensive G9 loader, and the number-vs-data check.
Offline, no model call. The node-based check is skipped when node is not installed."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from report import spa, spa_data

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "report" / "assets"


@pytest.fixture(scope="module")
def data():
    return spa_data.build()


def _walk(x, path=""):
    yield path, x
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _walk(v, f"{path}.{k}" if path else k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}.{i}")


def test_every_number_has_n_src_and_an_existing_file(data):
    items = [(p, v) for p, v in _walk(data) if isinstance(v, dict) and {"k", "src", "kind"} <= set(v)]
    assert len(items) > 40
    for p, v in items:
        assert v["k"] is not None, p
        assert v["src"], p
        f = v["src"].split(" ")[0]
        assert (ROOT / f).exists() or f.startswith("report/assets/recorded/"), (p, f)
        if v["kind"] == "count":
            assert v["n"] is not None, p


def test_g8_numbers_match_the_score_file(data):
    sc = json.loads((ROOT / "runs_g8" / "score.json").read_text(encoding="utf-8"))["acceptance"]
    g8 = data["g8"]
    assert (g8["direction"]["k"], g8["direction"]["n"]) == (sc["a_direction_right"], sc["n_leaky"])
    assert g8["false_alarms"]["k"] == sc["b_clean_false_alarms"]
    assert g8["inconclusive"]["k"] == sc["harness_inconclusive"]
    assert [x["k"] for x in data["readout"]["repeats"]] == [0.34, 0.339, 0.341, 0.328]
    assert data["g7"]["direction"]["k"] == 3 and data["g7"]["pass"] is False
    assert all(c["met"] for c in data["readout"]["clauses"])


def test_failed_repeat_is_an_empty_slot_not_a_number(data):
    r1 = data["g8"]["leaky"][0]
    assert r1["failed"] and "seeds" not in r1


def test_banned_words_topic_and_hash_never_in_payload(data):
    txt = json.dumps(data).lower()
    for w in spa_data.BANNED:
        assert not re.search(r"\b" + re.escape(w) + r"\b", txt), w
    for w in ("civil", "muchlinski", "neunhoeffer", "d1d7ffd0", "600a865e"):
        assert w not in txt, w


def test_page_has_no_external_requests_and_no_banned_text(data):
    html = spa.page(data)
    assert not re.search(r'(src|href)="https?://', html)
    low = html.lower()
    assert "civil" not in low and "d1d7ffd0" not in low
    assert "dotmatrix" not in low and "#e8501f" not in low
    assert "Measuring it is the work." in html


def test_g9_slot_is_defensive(tmp_path):
    assert spa_data._g9(tmp_path) is None                                   # no file: hidden
    (tmp_path / "runs_g9").mkdir()
    p = tmp_path / "runs_g9" / "score.json"
    p.write_text("{ not json", encoding="utf-8")
    assert spa_data._g9(tmp_path) is None                                   # partial write: hidden, no crash
    p.write_text("[1,2]", encoding="utf-8")
    assert spa_data._g9(tmp_path) is None
    p.write_text(json.dumps({"acceptance": {"a": "3/5", "PASS": False, "nested": {"x": 1}}}), encoding="utf-8")
    g = spa_data._g9(tmp_path)
    assert g and {"key": "a", "val": "3/5"} in g["rows"] and g["src"] == "runs_g9/score.json"
    p.write_text("{}", encoding="utf-8")
    assert spa_data._g9(tmp_path) is None


def test_scrub_renames_topic_in_keys_and_values():
    out = spa_data.scrub({"civilwar_x": ["Civil-war onset by Muchlinski"]})
    assert "civil" not in json.dumps(out).lower() and "muchlinski" not in json.dumps(out).lower()


NODE = shutil.which("node")
HARNESS = r"""
const fs = require('fs'); global.window = global; require(process.argv[2]);
const D = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const V = global.NLV; const out = [];
const chunks = [V.flow(D), V.gauge(D), V.readout(D).tiles, V.readout(D).clauses, V.intervals(D), V.rings(D).svg, V.rings(D).list];
const rx = /data-p="([^"]+)" data-f="([^"]+)">([^<]*)</g;
let n = 0, bad = [];
for (const c of chunks) { let m; while ((m = rx.exec(c))) { n++; const want = V.fmt(V.get(D, m[1]), m[2]); const got = m[3].replace(/&amp;/g, '&'); if (want !== got || want === 'n/a') bad.push([m[1], got, want]); } }
console.log(JSON.stringify({ n, bad }));
"""


@pytest.mark.skipif(not NODE, reason="node not installed")
def test_rendered_numbers_equal_spa_data(tmp_path, data):
    (tmp_path / "d.json").write_text(json.dumps(data), encoding="utf-8")
    (tmp_path / "h.js").write_text(HARNESS, encoding="utf-8")
    r = subprocess.run([NODE, str(tmp_path / "h.js"), str(ASSETS / "viz.js"), str(tmp_path / "d.json")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)
    assert res["n"] > 40 and res["bad"] == []
