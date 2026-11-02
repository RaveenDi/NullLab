"""Builds the JSON payload of the demo page (report/index.html) from the run files.

Every number on the page comes from here, read from runs_live/, runs_g5/, runs_g6/, eval/g6_truth.json or copied
from docs/EVAL-3.md / EVAL-6.md (those are tagged with their source). Nothing is rounded up or invented: means are
computed from the per-seed values in the files, and every value carries `n` and a provenance badge.
Run files that are missing are skipped (the page shows an empty state)."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

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


def _tol():
    """Magnitude tolerance of the G6 rule, read from g6.py (TOL = ...)."""
    p = ROOT / "g6.py"
    m = re.search(r"^TOL\s*=\s*([0-9.]+)", p.read_text(encoding="utf-8"), re.M) if p.exists() else None
    return float(m.group(1)) if m else None


PHASE = (("Recover", "Recover"), ("Verify", "Verify"), ("Act", "Act"), ("Plan", "Plan"), ("Report", "Verify"))


def _phase(raw):
    for k, v in PHASE:
        if raw.startswith(k):
            return v
    return "Verify"


# ---------------------------------------------------------------- traces (Plan / Act / Verify / Recover)
def _trace_live(run, src):
    """Trace of a single-split live run (runs_live/<case>.json)."""
    lines = []
    for e in run.get("log", []):
        lines.append({"phase": e["phase"], "text": e["msg"]})
    hyp = run.get("hyp", {})
    return {
        "source": src,
        "lines": lines,
        "plan": {"hypotheses": [{"id": h["id"], "text": h["text"], "direction": h["direction"],
                                 "primary": h["id"] == hyp.get("primary")} for h in hyp.get("hypotheses", [])],
                 "sha": hyp.get("prereg_sha256", ""), "note": "3 competing hypotheses, hashed before any run"},
        "act": {"edits": [{"label": "controlled_eval (written by the model, run in the sandbox)",
                           "code": hyp.get("code_patch", "")}],
                "note": "Split key: " + str(hyp.get("split_key", ""))},
        "verify": {"lines": [l["text"] for l in lines if l["phase"] == "Verify"], "fidelity": []},
        "recover": {"used": any(r.get("attempt", 1) > 1 for r in run.get("runs", [])), "lines": []},
    }


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
            if ph == "Verify" or ph == "Act":
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


# ---------------------------------------------------------------- hero cases (claim bar collapse)
def _hero_live(case, label, why):
    run = _j(f"runs_live/{case}.json")
    if not run:
        return None, None
    seeds = run["seeds"]
    man = (_j("corpus/manifest.json") or {}).get(case, {})
    claimed = [s["claimed_acc"] for s in seeds.values()]
    ctrl = [s["controlled_acc"] for s in seeds.values()]
    cv = run["claim"].get("value")
    cv = cv / 100 if cv and cv > 1 else cv
    v = run["verdict"]["verdict"]
    n_ctrl = sorted({s["n_controlled"] for s in seeds.values()})
    hero = {
        "id": case, "label": label, "short": label.split(" (")[0],
        "provenance": [run["provenance"]], "prov_note": man.get("note", ""),
        "mode": run["mode"], "metric": "accuracy", "unit": "pct", "axis_max": 1.0,
        "claim_text": run["claim"]["claim"],
        "start": {"value": cv, "label": "claimed in the methods text"},
        "end": {"value": _mean(ctrl), "label": "controlled re-evaluation (mean of 3 seeds)"},
        "markers": [{"value": _mean(claimed), "label": "claim's own protocol, re-run"}],
        "seeds": [{"seed": k, "claimed": s["claimed_acc"], "controlled": s["controlled_acc"], "delta": s["delta"],
                   "ci": [s["ci_lo"], s["ci_hi"]], "n": s["n_controlled"]} for k, s in seeds.items()],
        "n_text": f"n = {'/'.join(map(str, n_ctrl))} test rows per seed, seeds 42/43/44",
        "verdict": v, "per_seed": list(run["verdict"]["per_seed"].values()),
        "why": why, "source": f"runs_live/{case}.json",
    }
    return hero, _trace_live(run, f"runs_live/{case}.json")


def _g6(rn):
    return _j(f"runs_g6/r{rn}.json")


def _hero_g6(case, label, d6, truth, why, prov):
    sc = d6["cases"].get(case, {})
    reps = [(r, x["loop"]) for r, x in sorted(sc.items())]
    meas = [(r, lo) for r, lo in reps if "controlled" in lo]
    pub = truth.get("published_numbers", {}) if truth else {}
    metric = truth.get("metric", "accuracy") if truth else "accuracy"
    r1 = _g6(1) or {}
    lr1 = (r1.get("loop") or {}).get(case, {})
    st = (lr1.get("stats") or {})
    n_fb = sorted({v["full"]["n"]["fix_both"] for v in st.values()}) if st else []
    if case == "civilwar_apparent":
        start = {"value": pub.get("procedure5_apparent_pr_auc"), "label": "published apparent PR-AUC (Procedure 5)"}
        markers = [{"value": pub.get("procedure6_out_of_sample_pr_auc"), "label": "published corrected (Procedure 6)"}]
    elif case == "esl_selection":
        start = {"value": pub.get("wrong_cv_accuracy"), "label": "book: wrong-way CV accuracy (3% error)"}
        markers = [{"value": pub.get("true_accuracy"), "label": "book: true accuracy"}]
    else:  # clean variant
        start = {"value": (truth or {}).get("published_numbers", {}).get("procedure6_out_of_sample_pr_auc"), "label": ""}
        markers = []
    if case == "civilwar_apparent":
        m = re.search(r"ROC-AUC ([0-9.]+)", (truth or {}).get("original_claim", ""))
        claim_text = (f"A random forest forecasts civil-war onset: ROC-AUC {m.group(1) if m else '?'}, reported as cross-validated. "
                      f"The reanalysis shows the score is in-sample: apparent PR-AUC {pub.get('procedure5_apparent_pr_auc')}.")
    elif case == "esl_selection":
        claim_text = (f"Screen 100 of 5,000 predictors on all samples, then 5-fold CV: CV error {pub.get('wrong_cv_error')} "
                      f"(accuracy {pub.get('wrong_cv_accuracy')}), as in the textbook example.")
    else:
        claim_text = (truth or {}).get("original_claim", "")
    clm = [x for _, lo in meas for x in lo["claimed"]]
    if clm:
        markers.append({"value": _mean(clm), "label": "claim's own protocol, re-run"})
    seeds = []
    for r, lo in meas:
        for i, sd in enumerate(("42", "43", "44")):
            seeds.append({"seed": f"{r}·{sd}", "claimed": lo["claimed"][i], "controlled": lo["controlled"][i],
                          "delta": lo["inflation_per_seed"][i], "ci": lo["inflation_ci"][i]})
    return {
        "id": case, "label": label, "short": label.split(" (")[0], "provenance": prov,
        "prov_note": ((truth or {}).get("data") or (truth or {}).get("published_numbers", {}).get("note") or "").split(" (the same file")[0], "mode": "LIVE muse-spark-1.3, 3 repeats",
        "metric": "PR-AUC" if metric == "pr_auc" else "accuracy", "unit": "abs" if metric == "pr_auc" else "pct",
        "axis_max": 0.5 if metric == "pr_auc" else 1.0,
        "claim_text": claim_text,
        "start": start,
        "end": {"value": _mean([x for _, lo in meas for x in lo["controlled"]]),
                "label": f"controlled re-evaluation (mean of {len(meas)} repeats x 3 seeds)"},
        "markers": markers, "seeds": seeds,
        "n_text": f"fix-both scored on n = {'/'.join(map(str, n_fb))} held-out rows per seed (repeat 1), seeds 42/43/44" if n_fb else "",
        "verdict": "FALSIFIED" if all(lo["sign"] == "+" for _, lo in reps) else "INCONCLUSIVE",
        "per_seed": [s for _, lo in meas for s in lo.get("per_seed", [])],
        "why": why, "source": "runs_g6/score.json",
    }


def _hero_g6_clean(d6, truth):
    sc = d6["cases"].get("civilwar_temporal_clean", {})
    r1 = sc.get("r1", {}).get("loop", {})
    r3 = sc.get("r3", {}).get("loop", {})
    reason = (r1.get("reason") or [""])[0]
    pub = (truth or {}).get("civilwar_apparent", {}).get("published_numbers", {})
    signs = [sc[r]["loop"]["sign"] for r in sorted(sc)]
    r3txt = f"{r3['inflation_mean']:+.3f}" if "inflation_mean" in r3 else "n/a"
    return {
        "id": "civilwar_temporal_clean", "label": "Corrected civil-war pipeline, repeat 1 (REAL-PINNED)",
        "short": "Corrected civil-war pipeline", "provenance": ["REAL-PINNED"],
        "prov_note": "the reanalysis' own fix: train 1945-1989, score 1990-2000",
        "mode": "LIVE muse-spark-1.3, repeat 1 of 3", "metric": "PR-AUC", "unit": "abs", "axis_max": 0.5,
        "claim_text": "Out-of-sample PR-AUC of the temporally held-out pipeline (correct by construction).",
        "start": {"value": pub.get("procedure6_out_of_sample_pr_auc"), "label": "published out-of-sample PR-AUC"},
        "end": None, "markers": [], "seeds": [], "n_text": "no measurement in this repeat",
        "verdict": "INCONCLUSIVE", "per_seed": [],
        "why": ("The guard rejected the planner's fix twice, so nothing was measured and nothing was claimed. "
                f"Guard message: “{reason[:170]}”. Repeats: {' / '.join(signs)}; repeat 3 measured {r3txt} "
                "(no inflation). Reading alone called this correct pipeline inflated in 3 of 3 repeats."),
        "source": "runs_g6/score.json",
    }


def _hero_g5(c, r, d5, runs5):
    sc = d5["cases"][c][f"r{r}"]
    lr = runs5[r]["loop"][c]
    st = lr["stats"]
    acc = {k: _mean([v["full"]["acc"][k] for v in st.values()]) for k in ("orig", "fix_both")}
    lo = sc["loop"]
    return {
        "id": f"{c}", "label": "Synthetic assay, interaction case (SYNTHETIC)", "short": "Synthetic assay",
        "provenance": ["SYNTHETIC"], "prov_note": "generated by us with two planted flaws that interact",
        "mode": f"LIVE muse-spark-1.3, repeat {r} of 3", "metric": "accuracy", "unit": "pct", "axis_max": 1.0,
        "claim_text": "Accuracy of the claimed protocol on new compounds (synthetic case).",
        "start": {"value": acc["orig"], "label": "claim's own protocol, re-run (mean of 3 seeds)"},
        "end": {"value": acc["fix_both"], "label": "both suspect steps fixed (mean of 3 seeds)"},
        "markers": [],
        "seeds": [{"seed": s, "claimed": v["full"]["acc"]["orig"], "controlled": v["full"]["acc"]["fix_both"],
                   "delta": v["full"]["drop"]["fix_both"], "ci": v["full"]["drop_ci"]["fix_both"],
                   "n": v["full"]["n"]["fix_both"]} for s, v in st.items()],
        "n_text": f"n = {'/'.join(map(str, sorted({v['full']['n']['fix_both'] for v in st.values()})))} test rows per seed",
        "verdict": "FALSIFIED" if lo["sign"] == "+" else ("SURVIVED" if lo["sign"] == "0" else "INCONCLUSIVE"),
        "per_seed": lo.get("per_seed", []),
        "why": (f"Two planted flaws: fixing one alone removes {lo['components_pp']['A']:+.1f} or "
                f"{lo['components_pp']['B']:+.1f} points; fixing both removes {lo['components_pp']['both']:+.1f}, "
                f"{lo['components_pp']['AxB']:+.1f} more than the two separately. A case we built, not a paper."),
        "source": f"runs_g5/r{r}.json, runs_g5/score.json",
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


# ---------------------------------------------------------------- G6 real + textbook
def _real(d6, truth, tol):
    cases = {}
    for c, lab in (("civilwar_apparent", "Civil-war onset (Muchlinski et al. 2016)"),
                   ("esl_selection", "Screening before cross-validation (ESL §7.10.2)")):
        t = truth.get(c, {})
        pub = t.get("published_numbers", {})
        reps = []
        for r, x in sorted(d6["cases"].get(c, {}).items()):
            lo, b3 = x["loop"], x["b3"]
            reps.append({"r": r, "sign": lo.get("sign"), "per_seed": lo.get("per_seed"),
                         "inflation": lo.get("inflation_mean"), "ci": lo.get("inflation_ci"),
                         "claimed": lo.get("claimed"), "controlled": lo.get("controlled"),
                         "magnitude_ok": lo.get("magnitude_ok"), "reproduces": lo.get("reproduces"),
                         "in_ci": lo.get("published_in_ci_seeds"), "fixA": lo.get("A"), "kindA": (lo.get("kinds") or {}).get("A"),
                         "b3_pp": b3.get("fix_both_pp"), "b3_gets": b3.get("gets_it")})
        if c == "civilwar_apparent":
            claimed, corrected, infl = pub.get("procedure5_apparent_pr_auc"), pub.get("procedure6_out_of_sample_pr_auc"), pub.get("inflation_pr_auc")
        else:
            claimed, corrected = pub.get("wrong_cv_accuracy"), pub.get("true_accuracy")
            infl = pub.get("inflation_accuracy", (round(claimed - corrected, 2) if claimed is not None and corrected is not None else None))
        cases[c] = {"label": lab, "provenance": t.get("provenance"), "metric": "PR-AUC" if t.get("metric") == "pr_auc" else "accuracy",
                    "flaw": t.get("flaw"), "original": t.get("original_paper") or t.get("source"),
                    "original_claim": t.get("original_claim"), "reanalysis": t.get("reanalysis") or t.get("source"),
                    "published": {"claimed": claimed, "corrected": corrected, "inflation": infl,
                                  "text": pub.get("source_text", "")},
                    "data": t.get("data"), "reps": reps}
    clean = {}
    for c in ("civilwar_temporal_clean", "esl_selection_clean"):
        rows = []
        for r, x in sorted(d6["cases"].get(c, {}).items()):
            lo, b3 = x["loop"], x["b3"]
            rows.append({"r": r, "sign": lo.get("sign"), "inflation": lo.get("inflation_mean"),
                         "b3_leak": b3.get("leak"), "b3_pp": b3.get("fix_both_pp")})
        clean[c] = rows
    probe = _j("runs_g6/probe.json") or {}
    return {"cases": cases, "clean": clean, "acceptance": d6["acceptance"], "rule_sha": d6.get("rule_sha256", ""),
            "tol": tol, "probe": probe, "source": "runs_g6/score.json, eval/g6_truth.json, runs_g6/probe.json"}


# ---------------------------------------------------------------- scoreboard (counts with n)
def _scoreboard(d5, d6, abl):
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


def _stats(d5, d6):
    out = []
    if d5:
        a = d5["acceptance"]
        out.append({"value": a["ii_hard_sign_correct"], "caption": "hard synthetic runs: direction measured right",
                     "sub": f"reading only: wrong in {a['iii_b3_wrong_hard']}", "badges": ["SYNTHETIC"],
                     "src": "runs_g5/score.json (ii, iii)"})
        out.append({"value": a["i_clean_false_alarms"], "caption": "false alarms on correct synthetic pipelines",
                     "sub": f"reading only: {a['b3_clean_false_alarms']}", "badges": ["SYNTHETIC"],
                     "src": "runs_g5/score.json (i)"})
    if d6:
        a = d6["acceptance"]
        cw = d6["cases"]["civilwar_apparent"]
        sign_right = sum(1 for x in cw.values() if x["loop"].get("sign") == "+")
        within = sum(1 for x in cw.values() if x["loop"].get("magnitude_ok"))
        out.append({"value": a["c_clean_false_alarms"], "caption": "false alarms on the corrected real and textbook pipelines",
                     "sub": f"{a['clean_inconclusive']} of them INCONCLUSIVE; reading only: {a['b3_clean_false_alarms']}",
                     "badges": ["REAL-PINNED", "TEXTBOOK"], "src": "runs_g6/score.json (c)"})
        out.append({"value": f"{sign_right}/{len(cw)}", "caption": "civil-war repeats: flaw direction found",
                     "sub": f"size within tolerance in only {within}/{len(cw)}", "badges": ["REAL-PINNED"],
                     "src": "runs_g6/score.json (a)"})
    return out


def build() -> dict:
    d5, d6 = _j("runs_g5/score.json"), _j("runs_g6/score.json")
    truth = _j("eval/g6_truth.json") or {}
    runs5 = {r: _j(f"runs_g5/r{r}.json") for r in (1, 2, 3)}
    runs5 = {r: v for r, v in runs5.items() if v}
    abl = _j("runs_live/ablation.json")
    tol = _tol()

    heroes, traces = [], {}
    h, t = _hero_live("hero_tabular", "Wine classifier, 96% claim (REAL-PINNED data)",
                      "Jittered copies of each wine sample were made before the random split, so near-copies sat on "
                      "both sides. Splitting by the original sample first, then augmenting, is the controlled run.")
    if h:
        heroes.append(h)
        traces[h["id"]] = t
    if d6:
        g6r = {r: _g6(r) for r in (1, 2, 3)}
        tr = truth.get("civilwar_apparent")
        cw = _hero_g6("civilwar_apparent", "Civil-war onset, published paper (REAL-PINNED)", d6, tr,
                      "The published score was the apparent error: the model was scored on the rows it was trained "
                      "on. NullLab re-scored it on held-out rows. It found the direction, but under-measured the size.",
                      ["REAL-PINNED"])
        heroes.append(cw)
        heroes.append(_hero_g6("esl_selection", "Screening before CV, textbook (TEXTBOOK)", d6, truth.get("esl_selection"),
                               "The 100 predictors were chosen using all 50 labels before cross-validation. Moving the "
                               "screen inside the folds removes the inflation.", ["TEXTBOOK"]))
        heroes.append(_hero_g6_clean(d6, truth))
        for c in ("civilwar_apparent", "esl_selection", "civilwar_temporal_clean"):
            lr = ((g6r.get(1) or {}).get("loop") or {}).get(c)
            if lr:
                traces[c] = _trace_fx(lr, "runs_g6/r1.json")
    if d5 and 1 in runs5:
        hh = _hero_g5("g4_assay_replicates", 1, d5, runs5)
        heroes.append(hh)
        traces[hh["id"]] = _trace_fx(runs5[1]["loop"]["g4_assay_replicates"], "runs_g5/r1.json")
    h, t = _hero_live("clean_control", "Digits classifier, correct pipeline (REAL-PINNED data)",
                      "Here the claim holds: the controlled split scores the same as the claim's own protocol, all "
                      "three per-seed intervals include 0. NullLab says so instead of crying wolf.")
    if h:
        heroes.append(h)
        traces[h["id"]] = t

    prereg5 = _jl("runs_g5/prereg_log.jsonl")
    prereg6 = _jl("runs_g6/prereg_log.jsonl")
    return {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "heroes": heroes, "traces": traces,
        "factorial": _factorial(d5, runs5) if d5 else {},
        "g5": {"acceptance": d5["acceptance"], "rule_sha": d5.get("rule_sha256", ""), "n_prereg": len(prereg5)} if d5 else None,
        "real": _real(d6, truth, tol) if d6 else None,
        "g6_prereg": len(prereg6),
        "scoreboard": _scoreboard(d5, d6, abl),
        "stats": _stats(d5, d6),
        "mock_cases": sorted(p.stem for p in (ROOT / "runs").glob("*.json") if p.stem not in ("ablation",)),
        "tests_doc": {"value": "77 passed", "src": "docs/EVAL-6.md §6 (2026-11-02)"},
    }


if __name__ == "__main__":
    d = build()
    print(json.dumps({k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in d.items()}, indent=1))
