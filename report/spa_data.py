"""Builds the JSON payload of the demo page (report/index.html) from the run files.

Every number on the page comes from here, read from runs_live/, runs_g5/, runs_g6/, eval/g6_truth.json or copied
from docs/EVAL-3.md / EVAL-6.md (those are tagged with their source). Nothing is rounded up or invented: means are
computed from the per-seed values in the files, and every value carries `n` and a provenance badge.
Run files that are missing are skipped (the page shows an empty state)."""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent


def _j(p):
    p = ROOT / p
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _jl(p):
    p = ROOT / p
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


PHASE = (("Recover", "Recover"), ("Verify", "Verify"), ("Act", "Act"), ("Plan", "Plan"), ("Report", "Verify"))


def _phase(raw):
    for k, v in PHASE:
        if raw.startswith(k):
            return v
    return "Verify"



def _trace_fx(lr, src, plan_sha=None):
    """Trace of a factorial run (runs_g5/rK.json or runs_g6/rK.json, one case)."""
    lines, rec = [], []
    for e in lr.get("log", []):
        ph = _phase(e.get("phase", ""))
        raw = e.get("phase", "")
        bits = [raw[len(ph):].strip() if raw.startswith(ph) else raw]
        if e.get("verdict"):
            bits.append("-> " + e["verdict"])
        if e.get("status"):
            bits.append("-> " + e["status"])
        ch = e.get("changed")
        if ch:
            bits.append("; ".join(f"{k}: {', '.join(v['changed'])}" for k, v in ch.items()))
        if e.get("prereg_sha256"):
            bits.append("sha256 " + e["prereg_sha256"][:12])
        viol = (e.get("violations") or []) + (e.get("runtime_violations") or [])
        line = {"phase": ph, "text": " ".join(b for b in bits if b)}
        if viol:
            line["detail"] = viol[0][:420]
            if ph in ("Verify", "Act"):
                rec.append(viol[0][:420])
        lines.append(line)
    fp = lr.get("final_plan", {}) or {}
    edits = []
    for k in ("A", "B"):
        ed = (fp.get("edits") or {}).get(k) or {}
        for fn, code in (ed.get("steps") or {}).items():
            edits.append({"label": f"fix {k} ({ed.get('kind', '?')}): {fn}", "code": code[:1400]})
    used = any(_phase(e.get("phase", "")) == "Recover" for e in lr.get("log", []))
    return {
        "source": src,
        "lines": lines,
        "plan": {"suspects": [{"id": k, "text": fp.get(k, ""), "code_line": (fp.get(k + "_code_line") or "").strip()}
                              for k in ("A", "B") if fp.get(k)],
                 "pred": fp.get("predicted_drop_pp"), "sha": (fp.get("prereg_sha256") or plan_sha or ""),
                 "note": "Two suspect steps and predicted drops, hashed before execution"},
        "act": {"edits": edits, "note": "4 configs (original, fix A, fix B, fix both) x seeds 42/43/44 in the sandbox"},
        "verify": {"lines": [l["text"] for l in lines if l["phase"] == "Verify"],
                   "fidelity": [f"{k}: {v}" for k, v in (lr.get("fidelity") or {}).items()]},
        "recover": {"used": used, "lines": rec, "status": lr.get("status")},
    }


# ---------------------------------------------------------------- G5 factorial (SYNTHETIC)
G5_LABEL = {"g4_freight_delay": "cancellation", "g4_pump_inspection": "wrong culprit", "g4_crop_irrigation": "benign",
            "g4_assay_replicates": "interaction", "clean_control": "correct (control)",
            "clean_group_correct": "correct (groups)", "clean_wine_correct": "correct (wine)",
            "g4_visit_history_clean": "correct (visit history)"}


def _factorial(d5, runs5):
    out = {}
    for c, reps in d5["cases"].items():
        for rk, sc in reps.items():
            r = int(rk[1:])
            lr = (runs5.get(r) or {}).get("loop", {}).get(c)
            if lr is None:
                continue
            truth = d5["truth"].get(c, {})
            item = {"case": c, "repeat": r, "kind": G5_LABEL.get(c, c), "clean": c not in (
                "g4_freight_delay", "g4_pump_inspection", "g4_crop_irrigation", "g4_assay_replicates"),
                "status": lr["status"], "retries": lr.get("retries", 0),
                "truth": {"sign": truth.get("sign"), "verdict": truth.get("verdict"), "culprit": truth.get("culprit"),
                          "both": (truth.get("components_pp") or {}).get("both")},
                "b3": sc["b3"], "loop": sc["loop"], "source": f"runs_g5/r{r}.json"}
            if lr["status"] == "ok":
                st = lr["stats"]
                item["acc"] = {k: _mean([v["full"]["acc"][k] for v in st.values()])
                               for k in ("orig", "fix_A", "fix_B", "fix_both")}
                item["acc_seed"] = {s: v["full"]["acc"] for s, v in st.items()}
                item["n"] = sorted({v["full"]["n"]["orig"] for v in st.values()})
                item["fidelity"] = lr.get("fidelity") or {}
            fp = lr.get("final_plan") or {}
            item["A"], item["B"] = fp.get("A", ""), fp.get("B", "")
            item["reason"] = (sc["loop"].get("reason") or [""])[0][:300] if lr["status"] != "ok" else ""
            item["trace"] = _trace_fx(lr, f"runs_g5/r{r}.json")
            out[f"{c}.r{r}"] = item
    return out


# ---------------------------------------------------------------- scoreboard (counts with n)
def _scoreboard(d5, d6, abl, d7=None, rf=None, d8=None):
    rows = []
    if d5:
        a = d5["acceptance"]
        rows.append({"eval": "G5 hard cases (4 cases x 3 repeats)", "badges": ["SYNTHETIC"], "metric": "sign right",
                     "loop": a["ii_hard_sign_correct"], "b3": "wrong " + a["iii_b3_wrong_hard"],
                     "note": "loop miss = 1 INCONCLUSIVE", "src": "runs_g5/score.json"})
        rows.append({"eval": "G5 correct pipelines (4 x 3)", "badges": ["SYNTHETIC", "REAL-PINNED"],
                     "metric": "false alarms", "loop": a["i_clean_false_alarms"], "b3": a["b3_clean_false_alarms"],
                     "note": "real UCI data in 2 of the 4 correct cases; pipelines written by us", "src": "runs_g5/score.json"})
    if d6:
        a = d6["acceptance"]
        rows.append({"eval": "G6 leaky real + textbook (2 cases x 3)", "badges": ["REAL-PINNED", "TEXTBOOK"],
                     "metric": "matches published size (within tolerance)",
                     "loop": f"{int(a['a_civilwar_reproduces'].split('/')[0]) + int(a['b_esl_reproduces'].split('/')[0])}/6",
                     "b3": f"{sum(int(v.split('/')[0]) for v in a['b3_gets_it'].values())}/6",
                     "note": "reading wins here; both sources are recognised by the model", "src": "runs_g6/score.json"})
        rows.append({"eval": "G6 corrected versions (2 x 3)", "badges": ["REAL-PINNED", "TEXTBOOK"],
                     "metric": "false alarms", "loop": a["c_clean_false_alarms"], "b3": a["b3_clean_false_alarms"],
                     "note": f"{a['clean_inconclusive']} loop runs INCONCLUSIVE", "src": "runs_g6/score.json"})
    if d7:
        a = d7["acceptance"]
        rows.append({"eval": "G7 disguised real case (5 repeats)", "badges": ["REAL-PINNED"], "metric": "direction right on the leaky case",
                     "loop": f"{a['a_direction_right']}/{a['n_leaky_repeats']}", "b3": f"{a['b3_gets_it_leaky']}/{a['n_leaky_repeats']}",
                     "note": "preregistered acceptance FAILED (needed 4); reading detected more here", "src": "runs_g7/score.json"})
        rows.append({"eval": "G7 clean twin of the disguised case (5 repeats)", "badges": ["REAL-PINNED"], "metric": "false alarms",
                     "loop": f"{a['b_clean_false_alarms']}/{a['n_clean_repeats']}", "b3": f"{a['b3_false_alarms_clean']}/{a['n_clean_repeats']}",
                     "note": "the loop's one clear advantage in this study", "src": "runs_g7/score.json"})
    if d8:
        a = d8["acceptance"]
        rows.append({"eval": "G8 disguised real case, new labelled run (5 repeats)", "badges": ["REAL-PINNED"], "metric": "direction right on the leaky case",
                     "loop": f"{a['a_direction_right']}/{a['n_leaky']}", "b3": "not run",
                     "note": "clauses (a) to (c) met; harness target missed (1 of 10 INCONCLUSIVE)", "src": "runs_g8/score.json"})
        rows.append({"eval": "G8 clean twin (5 repeats)", "badges": ["REAL-PINNED"], "metric": "false alarms",
                     "loop": f"{a['b_clean_false_alarms']}/{a['n_clean']}", "b3": "not run", "note": "all five: no effect, interval spans 0", "src": "runs_g8/score.json"})
    if rf:
        sm = rf.get("summary", {})
        rows.append({"eval": "Fixed rules, no model (EVAL-8; 4 hard cases x3)", "badges": ["SYNTHETIC"], "metric": "hard-case sign right: rules vs loop",
                     "loop": sm.get("loop_hard_correct", ""), "b3": f"rules {sm.get('rules_hard_correct_x3', '')}",
                     "note": f"clean false alarms: rules {sm.get('rules_false_alarms_x3', '')}, loop {sm.get('loop_false_alarms', '')}; preregistered verdict {sm.get('result', '')}",
                     "src": "runs_rulefix/score.json"})
    if abl:
        rows.append({"eval": "EVAL-2 corpus (9 cases, 1 live run)", "badges": ["SYNTHETIC", "REAL-PINNED"],
                     "metric": "recall / false alarms",
                     "loop": f"{abl['NullLab']['recall']} / {abl['NullLab']['false_alarms']}",
                     "b3": f"{abl['B3']['recall']} / {abl['B3']['false_alarms']}",
                     "note": "flaws planted by us", "src": "runs_live/ablation.json"})
    tools = [  # copied from docs/EVAL-3.md (G1), same 9 blind inputs, data.csv only
        {"tool": "Deepchecks 0.19.1", "rule": "any failed condition", "recall": "4/6", "fa": "3/3"},
        {"tool": "Deepchecks 0.19.1", "rule": "leakage-relevant check failed", "recall": "4/6", "fa": "2/3"},
        {"tool": "Giskard 2.19.2", "rule": "any issue", "recall": "3/6", "fa": "2/3"},
        {"tool": "Giskard 2.19.2", "rule": "data-leakage or spurious-correlation issue", "recall": "1/6", "fa": "0/3"},
    ]
    return {"rows": rows, "tools": tools, "tools_src": "docs/EVAL-3.md (G1, 6 leaky + 3 clean blind inputs)"}


# ---------------------------------------------------------------- rules first, Spark where rules fail (EVAL-8)
RULE_NAMES = {"g4_freight_delay": "freight (cancellation)", "g4_pump_inspection": "pump (look-ahead feature)",
              "g4_crop_irrigation": "crop (benign)", "g4_assay_replicates": "assay (interaction)"}


def _rules(rf, d6):
    if not rf:
        return None
    rows = []
    for c, lab in RULE_NAMES.items():
        x = rf["cases"].get(c)
        if not x:
            continue
        lp = x.get("loop") or {}
        signs = [lp[k]["sign"] for k in sorted(lp)]
        both = [lp[k].get("both_pp") for k in sorted(lp)]
        ok = sum(1 for s in signs if s == x.get("truth_sign"))
        rows.append({"case": lab, "id": c, "truth": x.get("truth_sign"), "truth_pp": x.get("truth_both_pp"),
                     "rule_sign": x.get("sign"), "rule_pp": x.get("inflation"), "rule_ok": bool(x.get("correct")),
                     "fired": x.get("fired"), "loop_signs": signs, "loop_pp": both, "loop_ok": ok, "n_rep": len(signs),
                     "spark": (not x.get("correct")) and ok == len(signs)})
    real = []
    for c, lab, unit in (("civilwar_apparent", "Real case, not disguised (G6)", "PR-AUC"), ("esl_selection", "Textbook (ESL 7.10.2)", "pp")):
        x = rf["cases"].get(c)
        sc = (d6 or {}).get("cases", {}).get(c, {})
        if not x:
            continue
        real.append({"case": lab, "unit": unit, "rule": x.get("inflation"), "rule_ok": x.get("reproduces"),
                     "loop": [v["loop"].get("inflation_mean") for _, v in sorted(sc.items())],
                     "loop_ok": sum(1 for v in sc.values() if v["loop"].get("reproduces")), "n_rep": len(sc)})
    return {"rows": rows, "real": real, "summary": rf.get("summary", {}), "rules_sha": rf.get("rules_spec_sha256", ""),
            "prereg_sha": rf.get("prereg_sha256_file", ""), "source": "runs_rulefix/score.json, docs/EVAL-8-RULEBASED.md"}


# ---------------------------------------------------------------- cost ledger (estimates from the docs and the call logs)
def _count(p):
    return len(_jl(p))


def _ledger(d7, d8=None):
    g8usd = ((d8 or {}).get("usage") or {}).get("estimated_usd")
    ph = [("G4", 2.43, _count("runs/live_calls_g4.jsonl"), "docs/EVAL-4.md"),
          ("G5", 4.72, _count("runs/live_calls_g5.jsonl"), "docs/EVAL-5.md"),
          ("G6", 2.84, _count("runs/live_calls_g6.jsonl"), "docs/EVAL-6.md"),
          ("G7", (d7 or {}).get("spend_estimate_usd"), _count("runs_g7/live_calls_g7.jsonl"), "runs_g7/score.json"),
          ("G8", g8usd, _count("runs_g8/live_calls_g8.jsonl"), "runs_g8/score.json"),
          ("Rules baseline", 0.0, 0, "docs/EVAL-8-RULEBASED.md")]
    ph = [p for p in ph if p[1] is not None]
    return {"phases": [{"name": n, "usd": u, "calls": c, "src": s} for n, u, c, s in ph],
            "total_usd": round(sum(p[1] for p in ph), 2), "total_calls": sum(p[2] for p in ph),
            "note": "Estimated credits at per-call estimates, not invoiced prices (real per-token price UNVERIFIED). Earlier phases (G0 to G3) are not in the sum. This page makes no model call.",
            "source": "docs/EVAL-4.md, EVAL-5.md, EVAL-6.md, runs_g7/score.json, runs/live_calls_g*.jsonl"}


def _scalar(v):
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (int, str)):
        return str(v)[:90]
    if isinstance(v, (list, dict)):
        return f"{len(v)} items"
    return None


# ================================================================ v2 payload: every number as {k, n, src, badge}
# k is a count (kind "count": rendered k/n) or a measured value (kind "value"); n is the denominator or the number of
# measurements behind it; src is the file the number comes from. The page renders numbers only from these objects.
from datetime import timedelta, UTC  # noqa: E402

BANNED = ("first", "beats reading", "reproduces published", "proves", "found it anyway", "combined")
_SCRUB = ((re.compile(r"civil[ -]?war", re.I), "famous"), (re.compile(r"Muchlinski|Neunhoeffer|Sternberg|Kapoor|Narayanan"), "the authors"),
          (re.compile(r"conflict onset|war onset|onset", re.I), "event"))


def scrub(x: Any) -> Any:
    """The page never names the real study's topic or its authors (hackathon anti-project list). Applied to keys and values."""
    if isinstance(x, str):
        for rx, rep in _SCRUB:
            x = rx.sub(rep, x)
        return x
    if isinstance(x, list):
        return [scrub(i) for i in x]
    if isinstance(x, dict):
        return {scrub(k): scrub(v) for k, v in x.items()}
    return x


def N(k: Any, n: Any = None, src: str = "", badge: str = "REAL-PINNED", kind: str = "count", **extra: Any) -> dict:
    """A counted number with its n, source file and badge."""
    d = {"k": k, "n": n, "src": src, "badge": badge, "kind": kind}
    d.update(extra)
    return d


def V(v: Any, n: Any = None, src: str = "", badge: str = "REAL-PINNED", **extra: Any) -> dict:
    """A non-count value with its source file and badge."""
    return N(v, n, src, badge, "value", **extra)


def _frac(s):
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", str(s or ""))
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def _fn(s, src, badge="REAL-PINNED", **extra):
    k, n = _frac(s)
    return N(k, n, src, badge, **extra) if k is not None else None


def _needed(doc_text, row):
    """Preregistered thresholds are not in score.json; read them from the 'Needed' column of docs/EVAL-9-G8-RESULT.md."""
    m = re.search(r"\|\s*" + re.escape(row) + r"[^|]*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", doc_text or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _runs(dirname, ids=range(1, 6)):
    return {r: _j(f"{dirname}/r{r}.json") for r in ids}


def _case_rows(dirname, runs, case, score_cases):
    """One row per repeat with the per-seed 95% intervals of the fix-both drop (PR-AUC), read from runs_*/rK.json."""
    rows = []
    for rk, sc in sorted(score_cases.items()):
        sc = sc.get("loop", sc) if isinstance(sc, dict) else {}   # G7 nests the loop result; G8 is flat
        r = int(rk[1:])
        lp = (((runs.get(r) or {}).get("loop") or {}).get(case)) or {}
        st = lp.get("stats") or {}
        row = {"r": rk, "sign": sc.get("sign"), "src": f"{dirname}/r{r}.json"}
        if st and sc.get("sign") != "INCONCLUSIVE":
            seeds = []
            for sd, v in sorted(st.items()):
                f = v.get("full") or {}
                ci = (f.get("drop_ci") or {}).get("fix_both")
                if ci:
                    seeds.append({"seed": sd, "lo": ci[0], "hi": ci[1], "d": (f.get("drop") or {}).get("fix_both"),
                                  "claimed": (f.get("acc") or {}).get("orig"), "controlled": (f.get("acc") or {}).get("fix_both"),
                                  "n": (f.get("n") or {}).get("fix_both")})
            row["seeds"] = seeds
            row["mean"] = sc.get("inflation_mean")
            if sc.get("inflation_mean") is not None:
                row["m"] = V(sc.get("inflation_mean"), None, f"{dirname}/r{r}.json")
        else:
            row["failed"] = True
            row["reason"] = (lp.get("reason") or [""])[0] if lp else ""
            row["harness_failure"] = lp.get("harness_failure") or sc.get("label")
        rows.append(row)
    return rows


def _guard_rejects(runs, case):
    k = n = 0
    for r in runs.values():
        lg = (((r or {}).get("loop") or {}).get(case) or {}).get("log") or []
        vs = [(e.get("verdict"), " ".join(e.get("violations") or [])) for e in lg if e.get("verdict")]
        if vs:
            n += 1
            if vs[0][0] == "REJECT" and "SPLIT-USE-REQUIRED" in vs[0][1] and any(v[0] == "ACCEPT" for v in vs[1:]):
                k += 1
    return k, n


def _mean_stat(rows, key):
    xs = [s[key] for r in rows for s in r.get("seeds", []) if s.get(key) is not None]
    return _mean(xs), len(xs)


def _gblock(tag, d, dirname, src):
    """G7 and G8 are built by the same function so they get the same fields and the same weight."""
    if not d:
        return None
    a = d["acceptance"]
    case = "civilwar_disguised"
    nL = a.get("n_leaky_repeats", a.get("n_leaky"))
    nC = a.get("n_clean_repeats", a.get("n_clean"))
    runs = _runs(dirname)
    leaky = _case_rows(dirname, runs, case, d["cases"][case])
    clean = _case_rows(dirname, runs, case + "_clean", d["cases"][case + "_clean"])
    ok = [r for r in leaky if not r.get("failed")]
    inc = a.get("harness_inconclusive", a.get("leaky_inconclusive", 0) + a.get("clean_inconclusive", 0))
    claimed, _ = _mean_stat(ok, "claimed")
    ctrl, ns = _mean_stat(ok, "controlled")
    rj_k, rj_n = _guard_rejects(runs, case)
    return {
        "tag": tag, "src": src, "dir": dirname,
        "direction": N(a["a_direction_right"], nL, src), "false_alarms": N(a["b_clean_false_alarms"], nC, src),
        "magnitude": N(a.get("c_magnitude_within_0.15"), nL, src),
        "inconclusive": N(inc, (nL or 0) + (nC or 0), src),
        "reading_dir": N(a.get("b3_gets_it_leaky"), nL, src) if "b3_gets_it_leaky" in a else None,
        "reading_fa": N(a.get("b3_false_alarms_clean"), nC, src) if "b3_false_alarms_clean" in a else None,
        "pass": bool(a.get("PASS")), "harness_met": a.get("harness_target_met"),
        "leaky": leaky, "clean": clean,
        "claimed": V(claimed, len(ok), src) if claimed is not None else None,
        "controlled": V(ctrl, len(ok), src) if ctrl is not None else None,
        "n_scored": sorted({s["n"] for r in ok for s in r.get("seeds", []) if s.get("n")}),
        "inflation": [V(r["mean"], None, r["src"]) for r in ok if r.get("mean") is not None],
        "guard_rejects": N(rj_k, rj_n, src),
        "usage": d.get("usage"),
    }


def _g9_structured(j):
    """Readable rows for the known G9 score layout; None for any other layout (the caller falls back to generic rows)."""
    ov, eh = j.get("overall"), j.get("ehg")
    if not (isinstance(ov, dict) and isinstance(eh, dict)):
        return None
    done, planned = ov.get("cases_scored"), ov.get("cases_planned")
    if not (isinstance(done, int) and isinstance(planned, int)):
        return None
    incomplete = done < planned
    rows = []
    per = (j.get("cases") or {}).get("ehg_disguised") or {}
    infl = [r.get("inflation_mean") for r in per.values() if isinstance(r, dict) and isinstance(r.get("inflation_mean"), (int, float))]
    if isinstance(eh.get("n_leaky"), int):
        rows.append({"key": "EHG leaky: inflation found", "val": f"{eh.get('direction_right')} of {eh['n_leaky']} recorded repeats ({eh.get('denominator_each')} planned)"})
    if infl:
        rows.append({"key": "EHG leaky: measured inflation", "val": ", ".join(f"{v:+.3f}" for v in infl) + "  (offline reference +0.430)"})
    if isinstance(eh.get("n_clean"), int):
        rows.append({"key": "EHG clean twin: false alarms", "val": f"{eh.get('clean_false_alarms')} of {eh['n_clean']} recorded repeats"})
    if isinstance(eh.get("b3_gets_it_leaky"), int):
        rows.append({"key": "Reading only on EHG", "val": f"found the leaky case {eh['b3_gets_it_leaky']} of {eh.get('n_leaky')}; false alarms on clean {eh.get('b3_false_alarms_clean')} of {eh.get('n_clean')}"})
    if isinstance(ov.get("harness_inconclusive"), int):
        rows.append({"key": "Harness failures", "val": f"{ov['harness_inconclusive']} of {done} recorded units"})
    status = (f"INCOMPLETE: {done} of {planned} units recorded; the run was stopped (guard too slow on the large case). "
              "The preregistered bar cannot be evaluated." if incomplete else f"complete: {done} of {planned} units")
    return {"rows": rows, "src": "runs_g9/score.json", "badge": "REAL-PINNED, disguised", "status": status}


def _g9(root=None):
    """Defensive: the G9 file may not exist yet or may be partial/garbled. Returns None (slot stays hidden) unless it parses."""
    try:
        p = Path(root or ROOT) / "runs_g9" / "score.json"
        if not p.is_file():
            return None
        j = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(j, dict):
            return None
        structured = _g9_structured(j)
        if structured:
            return structured
        rows = []
        for key in ("acceptance", "summary"):
            blk = j.get(key)
            if isinstance(blk, dict):
                rows += [{"key": str(k), "val": _scalar(v)} for k, v in blk.items() if _scalar(v) is not None]
        if not rows:
            rows = [{"key": str(k), "val": _scalar(v)} for k, v in list(j.items())[:16] if _scalar(v) is not None]
        if not rows:
            return None
        return {"rows": rows[:24], "src": "runs_g9/score.json", "badge": "LOADED FROM FILE", "status": None}
    except Exception:
        return None


def _recorded():
    out = []
    d = Path(__file__).resolve().parent / "assets" / "recorded"
    for f in sorted(d.glob("hybrid_*.json")) if d.is_dir() else []:
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
            t = datetime.strptime(r["recorded_utc"], "%Y-%m-%dT%H:%M:%SZ")
            et = timedelta(hours=-5) if t >= datetime(2026, 11, 1, 6) else timedelta(hours=-4)
            r["recorded_slt"] = (t + timedelta(hours=5, minutes=30)).strftime("%Y-%m-%d %H:%M") + " SLT"
            r["recorded_et"] = (t + et).strftime("%H:%M") + (" EST" if et.total_seconds() == -18000 else " EDT")
            sm, src = r.get("summary") or {}, r.get("source_file", "")
            nn = (sm.get("n_controlled") or [None])[0]
            r["ba"] = {"claimed": V(sm.get("claimed"), nn, src, "SYNTHETIC"), "controlled": V(sm.get("controlled"), nn, src, "SYNTHETIC"),
                       "inflation": V(sm.get("inflation"), nn, src, "SYNTHETIC"), "n": N(nn, nn, src, "SYNTHETIC")}
            out.append(r)
        except Exception:
            continue
    return out


def _fx_compact(d5, runs5):
    F = _factorial(d5, runs5) if d5 else {}
    it = F.get("g4_assay_replicates.r1")
    if not it or it.get("status") != "ok":
        return None
    c = it["loop"].get("components_pp") or {}
    n0 = it["n"][0] if it.get("n") else None
    return {"acc": {k: V(v, n0, it["source"], "SYNTHETIC") for k, v in it["acc"].items()},
            "components": {k: V(v, None, it["source"], "SYNTHETIC") for k, v in c.items()}, "n": it["n"], "src": it["source"],
            "sign": it["loop"].get("sign")}


def _clauses(g8, doc):
    out = []
    if not g8:
        return out
    for cid, row, got, rule, lab in (("a", "(a) direction right", g8["direction"], "ge", "direction right"),
                                      ("b", "(b) clean false alarms", g8["false_alarms"], "le", "clean false alarms"),
                                      ("c", "(c) inflation within 0.15", g8["magnitude"], "ge", "inflation within 0.15 of the published +0.36")):
        need_txt, _ = _needed(doc, row)
        nk, nn = (None, None)
        if need_txt:
            t = re.sub(r"at least\s*", "", need_txt).replace(" of ", "/").strip()
            nk, nn = _frac(t)
            if nk is None and t.isdigit():
                nk = int(t)
        met = None
        if nk is not None and got.get("k") is not None:
            met = got["k"] >= nk if rule == "ge" else got["k"] <= nk
        out.append({"id": cid, "label": lab, "rule": rule, "needed": N(nk, nn or got["n"], "docs/EVAL-9-G8-RESULT.md"), "got": got, "met": met})
    return out


def build() -> dict:
    """Everything the demo page shows, read from the run files."""
    d5, d6, d7, d8, rf = (_j("runs_g5/score.json"), _j("runs_g6/score.json"), _j("runs_g7/score.json"),
                          _j("runs_g8/score.json"), _j("runs_rulefix/score.json"))
    truth = _j("eval/g6_truth.json") or {}
    pubn = (truth.get("civilwar_apparent") or {}).get("published_numbers") or {}
    runs5 = {r: v for r, v in {r: _j(f"runs_g5/r{r}.json") for r in (1, 2, 3)}.items() if v}
    abl = _j("runs_live/ablation.json")
    t = "eval/g6_truth.json"
    pub = {"claimed": V(pubn.get("procedure5_apparent_pr_auc", 0.43), None, t), "corrected": V(pubn.get("procedure6_out_of_sample_pr_auc", 0.07), None, t),
           "inflation": V(pubn.get("inflation_pr_auc", 0.36), None, t)}
    e7 = (ROOT / "docs/EVAL-7.md").read_text(encoding="utf-8") if (ROOT / "docs/EVAL-7.md").exists() else ""
    m = re.search(r"inflation \*\*\+(0\.\d+)\*\*", e7)
    pub["reference"] = V(float(m.group(1)) if m else None, None, "docs/EVAL-7.md")
    g7, g8 = _gblock("G7", d7, "runs_g7", "runs_g7/score.json"), _gblock("G8", d8, "runs_g8", "runs_g8/score.json")

    doc = (ROOT / "docs/EVAL-9-G8-RESULT.md").read_text(encoding="utf-8") if (ROOT / "docs/EVAL-9-G8-RESULT.md").exists() else ""
    readout = {"measured": V(_mean([x["k"] for x in g8["inflation"]]), len(g8["inflation"]), "runs_g8/score.json") if g8 and g8["inflation"] else None,
               "repeats": g8["inflation"] if g8 else [], "clean_fa": g8["false_alarms"] if g8 else None,
               "harness": ({"got": g8["inconclusive"], "target": N(d8["acceptance"].get("harness_inconclusive_target"), g8["inconclusive"]["n"], "runs_g8/score.json")}
                           if g8 else None),
               "clauses": _clauses(g8, doc),
               "clean_inflation": [V(r.get("mean"), None, r["src"]) for r in (g8["clean"] if g8 else []) if r.get("mean") is not None]}

    rings = None
    if d6 and d5 and rf and g7 and g8:
        a6, a5, sm = d6["acceptance"], d5["acceptance"], rf.get("summary", {})
        und = (d6.get("cases") or {}).get("civilwar_apparent") or {}
        dirk = sum(1 for x in und.values() if (x.get("loop") or {}).get("sign") == "+")
        rings = {"core": {"g7": g7, "g8": g8},
                 "mid": {"textbook": _fn(a6["b_esl_reproduces"], "runs_g6/score.json", "TEXTBOOK"),
                         "undisguised_dir": N(dirk, len(und), "runs_g6/score.json"), "undisguised_size": _fn(a6["a_civilwar_reproduces"], "runs_g6/score.json")},
                 "outer": {"loop_sign": _fn(a5["ii_hard_sign_correct"], "runs_g5/score.json", "SYNTHETIC"), "loop_fa": _fn(a5["i_clean_false_alarms"], "runs_g5/score.json", "SYNTHETIC"),
                           "rules_sign": _fn(sm.get("rules_hard_correct_x3"), "runs_rulefix/score.json", "SYNTHETIC"),
                           "rules_fa": _fn(sm.get("rules_false_alarms_x3"), "runs_rulefix/score.json", "SYNTHETIC")},
                 "ghost": {"reading_dir": g7["reading_dir"], "reading_fa": g7["reading_fa"], "note": "reading-only baseline on the G7 case: one prompt, no execution"}}

    tr = None
    for r in (2, 3, 4, 5):
        lr = (((_j(f"runs_g8/r{r}.json") or {}).get("loop") or {}).get("civilwar_disguised"))
        if lr and lr.get("status") == "ok":
            tr = _trace_fx(lr, f"runs_g8/r{r}.json")
            tr["lines"] = [{**l, "text": re.sub(r"\s*sha256 [0-9a-f]+", "", l.get("text", ""))} for l in tr["lines"]]
            tr["plan"].pop("sha", None)
            break

    def ex(a, b):
        return N(a, b, "docs/EVAL-7.md", "SYNTHETIC")  # copied from the doc, tagged with it

    out = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        "pub": pub, "g7": g7, "g8": g8, "readout": readout, "rings": rings, "g9": _g9(), "recorded": _recorded(),
        "guard": g8["guard_rejects"] if g8 else None,
        "trace": tr, "factorial": _fx_compact(d5, runs5),
        "scoreboard": _scoreboard(d5, d6, abl, d7, rf, d8), "rules": _rules(rf, d6), "ledger": _ledger(d7, d8),
        "wonder": {"plans": ex(8, 8), "hard_sign": ex(4, 4), "clean_fa": ex(0, 4),
                   "note": "8 synthetic cases x 1 repeat, temperature 0; a small sample, not evidence that Wonder is better."},
        "mock_cases": sorted(p.stem for p in (ROOT / "runs").glob("*.json") if p.stem not in ("ablation",)),
        "tests_doc": {"value": "77 passed at G6", "src": "docs/EVAL-6.md section 6; later phases add tests not counted here"},
    }
    return scrub(out)


if __name__ == "__main__":
    d = build()
    print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in d.items()}, indent=1))
