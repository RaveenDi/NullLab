"""G6 driver: does NullLab reproduce a PUBLISHED correction on real / textbook-documented cases? Outputs in runs_g6/.
Cases (real/): civilwar_apparent (REAL-PINNED, leaky), civilwar_temporal_clean (REAL-PINNED, correct),
               esl_selection (TEXTBOOK, leaky), esl_selection_clean (TEXTBOOK, correct).
Stages (.venv\\Scripts\\python g6.py <stage> ...):
  ref       OFFLINE builder reference: the published correction as a patch, measured in the sandbox  -> runs_g6/ref.json
  replay    OFFLINE: tightened guard on every G5 plan + the G6 reference patches                     -> runs_g6/replay.json
  rule      hash + log published numbers, acceptance rule, sources, prompts, agent views            -> prereg_log.jsonl
  probe     live memorisation probes (excerpt-only, as in agent/extract.py; and full agent view)    -> runs_g6/probe.json
  run <r>   repeat r (1..3): B3 x 4 (logged), planner x 4 (logged), then the guarded loop x 4       -> runs_g6/r<r>.json
  score     preregistered acceptance                                                              -> runs_g6/score.json
The loop machinery is G5's (g5.py: sandbox execution, recover-once, INCONCLUSIVE); G6 adds the justification guard."""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "runs_g6"
sys.path.insert(0, str(ROOT))
import g4  # noqa: E402
import g5  # noqa: E402
from agent import factorial_g6, fidelity, llm  # noqa: E402

CASES = {c: ROOT / "real" / c for c in ("civilwar_apparent", "civilwar_temporal_clean", "esl_selection", "esl_selection_clean")}
LEAKY, CLEAN = ["civilwar_apparent", "esl_selection"], ["civilwar_temporal_clean", "esl_selection_clean"]
SEEDS, N_BOOT = (42, 43, 44), 1000
START_SPEND = 17.8227          # bs.py meta spent_usd before any G6 call (2026-11-01)
CEILING_USD = START_SPEND + 3.50
EST = {"b3": 0.08, "plan": 0.10, "retry": 0.10, "probe": 0.03}

# G5 machinery points at our cases, output dir and ceiling (g5 functions read these module globals at call time)
g5.CASES, g5.OUT, g5.CEILING_USD = CASES, OUT, CEILING_USD

PUBLISHED = {  # copied from eval/g6_truth.json (host-only); the rule hash below fixes them before any live call
    "civilwar_apparent": {"metric": "pr_auc", "claimed": 0.43, "corrected": 0.07, "inflation": 0.36,
                          "source": "Neunhoeffer & Sternberg 2019, Political Analysis 27(1):101-106, Sec. 4 + App. C.2"},
    "esl_selection": {"metric": "accuracy", "claimed": 0.97, "corrected": 0.50, "inflation": 0.47,
                      "source": "Hastie, Tibshirani, Friedman, ESL 2nd ed. (12th printing) Sec. 7.10.2"},
}
TOL = 0.15

SCORING_RULE = """G6 scoring rule (fixed before any G6 live call).
Cases: civilwar_apparent (REAL-PINNED; published correction: Neunhoeffer & Sternberg 2019 report PR-AUC 0.43 for the
apparent-error protocol of Muchlinski et al. 2016 vs 0.07 out of sample => inflation +0.36 PR-AUC, sign +),
esl_selection (TEXTBOOK; ESL 7.10.2: CV error 3% vs true 50% => inflation +0.47 accuracy, sign +), and their correct
variants civilwar_temporal_clean and esl_selection_clean (truth sign 0). 3 repeats r1..r3 per case; the only difference
between repeats is '[repeat id: g6-rK]' in the user message (temperature 0). Per repeat: B3 x 4 first (hashed, logged),
then the loop planner x 4 (hashed, logged), then execution.
LOOP = agent/factorial_g6.py planner (G5 planner + one paragraph on the G6 rules) + agent/fidelity.py guard
(check_static: LOCALITY, MODEL, FEATURES, SPLIT; check_runtime: SAMPLE SIZE; check_justification: FEATURE-REASON,
SPLIT-USE). Recover: one live retry on any rejection or execution error; still failing => INCONCLUSIVE (never FALSIFIED).
Measurement: 4 configs x seeds 42/43/44, n_boot=1000, UNPAIRED bootstrap; metric = train.METRIC (PR-AUC = average
precision for civil war; accuracy for ESL). MEASURED INFLATION = claimed (orig) - controlled (fix_both).
SIGN per seed: '+' if the 95% CI of the inflation > 0, '-' if < 0, '0' if it spans 0; case-repeat sign = category of
>= 2 of 3 seeds, else 'mixed'.
Leaky case-repeat REPRODUCES the published correction iff loop sign == '+' (same sign as published) AND
|mean over seeds of measured inflation - published inflation| <= 0.15 (metric units). Reported alongside: whether the
published inflation lies inside the seed CIs, the controlled value vs the published corrected value, and the planner's
predicted drop.
Clean case-repeat FALSE ALARM iff loop sign == '+'.
ACCEPTANCE (G6 PASS) iff (a) civilwar_apparent reproduces in >= 2 of 3 repeats AND (b) esl_selection reproduces in
>= 2 of 3 repeats AND (c) 0 false alarms over the 6 clean case-repeats. INCONCLUSIVE counts as not reproduced and is
reported for clean cases (not a false alarm).
B3 (one live call, reading only): B3 GETS IT on a leaky case iff leak == true AND predicted fix_both drop >= +2 points
AND |predicted fix_both drop / 100 - published inflation| <= 0.15. B3 false alarm on a clean case iff leak == true.
Budget: stop if projected Meta spend passes START + $3.50."""


def _save(name, obj):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1))


def _load(name, default=None):
    p = OUT / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else default


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _case_files(c):
    d = CASES[c]
    return ((d / "train.py").read_text(encoding="utf-8"), (d / "excerpt.md").read_text(encoding="utf-8"),
            (d / "data.csv").open(encoding="utf-8").readline().strip().split(","))


# ---------------- guard (G5 static + runtime, plus G6 justification) ----------------
def guard(case, plan):
    cfgs, problems, reports = g5._guard(case, (plan or {}).get("edits"))
    src, exc, hdr = _case_files(case)
    problems += [f"plan: {x}" for x in fidelity.check_justification(src, exc, hdr, plan)]
    return cfgs, problems, reports


def loop_case(case, rid, plan_rec):
    """Plan -> Verify (guard) -> Act (sandbox) -> Recover once -> Report. Same as g5.loop_case + justification rules."""
    from sandbox import factorial_stats
    log = [{"phase": "Plan", "utc": time.strftime("%H:%M:%SZ", time.gmtime()), "prereg_sha256": plan_rec["plan"].get("prereg_sha256")}]
    cur, retried, rec = plan_rec["plan"], False, {"retries": 0}
    while True:
        cfgs, problems, reports = guard(case, cur)
        log.append({"phase": "Verify (static fidelity + justification)", "verdict": "REJECT" if problems else "ACCEPT",
                    "violations": problems[:8], "changed": reports})
        raw = None
        if not problems:
            raw, problems = g5._execute(case, cfgs)
            log.append({"phase": "Act (sandbox, 4 configs x 3 seeds)", "status": "ok" if raw is not None else "error",
                        "runtime_violations": problems[:8]})
        if not problems:
            break
        if retried:
            rec.update({"status": "INCONCLUSIVE", "reason": problems[:8], "log": log, "final_plan": cur})
            log.append({"phase": "Report", "verdict": "INCONCLUSIVE (guard/execution still failing after one retry)"})
            return rec
        if not g5._budget_ok(EST["retry"]):
            rec.update({"status": "INCONCLUSIVE", "reason": ["budget ceiling: no retry"] + problems[:8], "log": log, "final_plan": cur})
            return rec
        try:
            cur, rawtxt = factorial_g6.retry(CASES[case], rid, cur, problems[:8])
        except Exception as e:  # noqa: BLE001
            rec.update({"status": "INCONCLUSIVE", "reason": [f"retry call failed: {e!r}"[:400]] + problems[:8], "log": log, "final_plan": cur})
            return rec
        retried, rec["retries"] = True, 1
        r = g5._prereg("loop_planner_retry", {k: cur.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")}, case, rid)
        log.append({"phase": "Recover (one live retry with the violation text)", "prereg_sha256": r["sha256"], "retry_raw_len": len(rawtxt)})
    stats = factorial_stats.all_seeds(raw, n_boot=N_BOOT)
    rec.update({"status": "ok", "metric": raw.get("metric", "accuracy"), "stats": stats, "final_plan": cur, "log": log,
                "fidelity": {cfg: fidelity.verdict_line(cfgs[cfg], reports[cfg]) for cfg in reports},
                "sources": {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}})
    log.append({"phase": "Report", "verdict": "measured"})
    return rec


# ---------------- offline stages ----------------
REF_FIX = {  # builder reference = the published correction, as structured edits (never shown to an agent)
    "civilwar_apparent": {
        "A": {"kind": "split", "steps": {"split_rows": (
            "def split_rows(df, seed):\n    idx = np.arange(len(df))\n"
            "    return idx[df['year'].to_numpy() < 1990], idx[df['year'].to_numpy() >= 1990]\n")}},
        "B": {"kind": "fit_scope", "steps": {"tune_mtry": (
            "def tune_mtry(X, y, seed, k=10):\n    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed + 1)\n"
            "    best, best_auc = MTRY_GRID[0], -1.0\n    for m in MTRY_GRID:\n"
            "        aucs = [roc_auc_score(y[te], forest_score(fit_forest(X[tr], y[tr], seed, m), X[te])) for tr, te in cv.split(X, y)]\n"
            "        if np.mean(aucs) > best_auc:\n            best, best_auc = m, float(np.mean(aucs))\n    return best\n")}},
        "A_code_line": "    return idx, idx", "B_code_line": "    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)"},
    "esl_selection": {
        "A": {"kind": "fit_scope", "steps": {
            "claimed_eval": ("def claimed_eval(df, seed):\n    X = df[feats(df)].to_numpy(dtype=float)\n"
                             "    y = df[TARGET].to_numpy().astype(int)\n    return y, cv_predict(X, y, seed)\n"),
            "cv_predict": ("def cv_predict(X, y, seed):\n    pred = np.empty_like(y)\n"
                           "    for tr, te in StratifiedKFold(n_splits=N_FOLDS, shuffle=True, random_state=seed).split(X, y):\n"
                           "        keep = screen(X[tr], y[tr])\n"
                           "        pred[te] = KNeighborsClassifier(n_neighbors=1).fit(X[tr][:, keep], y[tr]).predict(X[te][:, keep])\n"
                           "    return pred\n")}},
        "B": {"kind": "feature", "steps": {"feats": "def feats(df):\n    return [c for c in df.columns if c not in (TARGET,)]\n"}},
        "A_code_line": "    keep = screen(X, y)", "B_code_line": "    return [c for c in df.columns if c != TARGET]"},
}


def _summ(stats):
    ss = sorted(stats)
    f = lambda k: [round(stats[s]["full"]["acc"][k], 3) for s in ss]  # noqa: E731
    return {"metric": stats[ss[0]]["full"].get("metric", "accuracy"), "orig": f("orig"), "fix_A": f("fix_A"),
            "fix_B": f("fix_B"), "fix_both": f("fix_both"),
            "inflation_fix_both": [round(stats[s]["full"]["drop"]["fix_both"], 3) for s in ss],
            "inflation_ci": [[round(x, 3) for x in stats[s]["full"]["drop_ci"]["fix_both"]] for s in ss],
            "sign": g4.case_sign(stats)}


def ref(args):
    from sandbox import factorial_stats
    out = _load("ref", {})
    for c, plan in REF_FIX.items():
        if (args and c not in args) or (not args and c in out and out[c].get("status") == "ok"):
            continue
        cfgs, problems, _ = guard(c, plan | {"edits": {k: plan[k] for k in ("A", "B")}})
        if problems:
            print(c, "REF guard notes (builder reference is not gated):", problems)
        t0 = time.time()
        raw, rv = g5._execute(c, cfgs)
        if raw is None:
            out[c] = {"status": "error", "problems": rv}
            print(c, "REF ERROR", rv)
            continue
        st = factorial_stats.all_seeds(raw, n_boot=N_BOOT)
        out[c] = {"status": "ok", "summary": _summ(st), "stats": st, "elapsed_s": round(time.time() - t0)}
        print(c, json.dumps(out[c]["summary"]), flush=True)
        _save("ref", out)
    _save("ref", out)


def replay(args):
    """Tightened guard on every G5 executed plan (+ G6 reference patches). Previously accepted hard-case patches must
    still pass; the declared-but-unjustified clean-case column drops are expected to be rejected now."""
    out = {}
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g5" / f"r{r}.json").read_text())
        for c, lr in d["loop"].items():
            if lr["status"] != "ok":
                continue
            cd = g4.CASES[c]
            src = (cd / "train.py").read_text(encoding="utf-8")
            v = fidelity.check_justification(src, (cd / "excerpt.md").read_text(encoding="utf-8"),
                                             (cd / "data.csv").open(encoding="utf-8").readline().strip().split(","), lr["final_plan"])
            cf = fidelity.build_configs(src, lr["final_plan"]["edits"])
            sv = [x for i in cf.values() for x in (i["violations"] or fidelity.check_static(src, i["src"], i["kinds"], i["declared"])[0])]
            out[f"g5-r{r}/{c}"] = {"verdict": "REJECT" if v or sv else "ACCEPT", "violations": v + sv,
                                   "hard_case": c in g4.NEW}
    for c, plan in REF_FIX.items():
        _, problems, _ = guard(c, plan | {"edits": {k: plan[k] for k in ("A", "B")}})
        out[f"g6-ref/{c}"] = {"verdict": "REJECT" if problems else "ACCEPT", "violations": problems}
    _save("replay", out)
    for k, r in out.items():
        print(f"{k:42s} {r['verdict']} {[x[:90] for x in r['violations']][:2]}")


# ---------------- preregistration ----------------
def rule(args):
    src = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
           ("agent/fidelity.py", "agent/factorial_g5.py", "agent/factorial_g6.py", "agent/factorial.py",
            "baselines/single_prompt.py", "g5.py", "g6.py", "sandbox/factorial_stats.py", "sandbox/run_factorial.py",
            "eval/g6_truth.json")}
    g5._prereg("g6_scoring_rule", {"rule": SCORING_RULE, "published": PUBLISHED, "tol": TOL})
    g5._prereg("g6_source_hashes", src)
    from baselines.single_prompt import FACTORIAL_SYSTEM
    g5._prereg("g6_prompts", {"planner_system": factorial_g6.SYSTEM, "b3_system": FACTORIAL_SYSTEM})
    for c, d in CASES.items():
        g5._prereg("agent_view_frozen", g4._hashes(d), c)


def probe(args):
    """Memorisation probes. (1) agent/extract.memorization_probe as is (excerpt only). (2) the same question over the
    full agent view (excerpt + train.py + data head), since column names can identify a famous data set."""
    from agent import extract
    from agent.factorial import agent_view
    out = _load("probe", {})
    if not g5._budget_ok(EST["probe"] * 4):
        return
    for c in LEAKY:
        if c in out:
            continue
        r1 = extract.memorization_probe(CASES[c], "live")
        ans = llm.live_complete("Answer in one short line.", "If you recognise the dataset, paper or repository this material "
                                "comes from, name it; otherwise say UNKNOWN.\n\n" + agent_view(CASES[c]), est_usd=EST["probe"], tag="g6_probe")
        r2 = {"status": "pass" if "UNKNOWN" in ans.upper() else "FAIL_named_source", "answer": ans[:300]}
        out[c] = {"excerpt_only": r1, "full_agent_view": r2}
        print(c, json.dumps(out[c]), flush=True)
        _save("probe", out)


# ---------------- one repeat ----------------
def _b3(c, rid):
    from agent.factorial import agent_view
    from baselines.single_prompt import FACTORIAL_SYSTEM
    raw = llm.live_complete(FACTORIAL_SYSTEM, agent_view(CASES[c]) + f"\n\n[repeat id: {rid}]", est_usd=EST["b3"], tag="g6_b3")
    return llm.parse_json(raw), raw


def run(args):
    r = int(args[0])
    rid = f"g6-r{r}"
    res = _load(f"r{r}", {"repeat": rid, "b3": {}, "plan": {}, "loop": {}})
    todo_b3 = [c for c in CASES if c not in res["b3"] or "error" in res["b3"][c]]
    todo_plan = [c for c in CASES if c not in res["plan"] or "error" in res["plan"][c]]
    if not g5._budget_ok(len(todo_b3) * EST["b3"] + len(todo_plan) * (EST["plan"] + EST["retry"])):
        return
    for c, v in g5._parallel(_b3, todo_b3, rid).items():
        if isinstance(v, Exception):
            res["b3"][c] = {"error": repr(v)[:600]}
            print(c, "B3 ERROR", repr(v)[:300], flush=True)
            continue
        ans, raw = v
        rec = g5._prereg("b3_single_prompt", {k: ans.get(k) for k in ("leak", "A", "B", "predicted_drop_pp", "culprit_ranking")}, c, rid)
        res["b3"][c] = {"ans": ans, "raw": raw, "prereg_sha256": rec["sha256"]}
    _save(f"r{r}", res)
    for c, v in g5._parallel(lambda c, rid: factorial_g6.plan(CASES[c], rid), todo_plan, rid).items():
        if isinstance(v, Exception):
            res["plan"][c] = {"error": repr(v)[:600]}
            print(c, "PLAN ERROR", repr(v)[:300], flush=True)
            continue
        p, raw = v
        rec = g5._prereg("loop_planner", {k: p.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")}, c, rid)
        res["plan"][c] = {"plan": p, "raw": raw, "prereg_sha256": rec["sha256"]}
    _save(f"r{r}", res)
    for c in CASES:
        if c in res["loop"] or "plan" not in res["plan"].get(c, {}):
            continue
        t0 = time.time()
        res["loop"][c] = loop_case(c, rid, res["plan"][c])
        lr = res["loop"][c]
        sgn = g4.case_sign(lr["stats"]) if lr["status"] == "ok" else ("INCONCLUSIVE", None)
        print(f"{rid} {c:26s} {lr['status']} retries={lr['retries']} sign={sgn} {time.time() - t0:.0f}s", flush=True)
        _save(f"r{r}", res)


# ---------------- scoring ----------------
def score(args):
    rows, acc = {c: {} for c in CASES}, {}
    for r in (1, 2, 3):
        res = _load(f"r{r}")
        if not res:
            continue
        for c in CASES:
            row = {}
            lr = res["loop"].get(c)
            if lr is None:
                row["loop"] = {"sign": "NOT RUN"}
            elif lr["status"] != "ok":
                row["loop"] = {"sign": "INCONCLUSIVE", "retries": lr["retries"], "reason": lr.get("reason")}
            else:
                st = lr["stats"]
                s, cats = g4.case_sign(st)
                infl = [st[sd]["full"]["drop"]["fix_both"] for sd in sorted(st)]
                cis = [st[sd]["full"]["drop_ci"]["fix_both"] for sd in sorted(st)]
                row["loop"] = {"sign": s, "per_seed": cats, "retries": lr["retries"], "metric": lr.get("metric"),
                               "claimed": [round(st[sd]["full"]["acc"]["orig"], 3) for sd in sorted(st)],
                               "controlled": [round(st[sd]["full"]["acc"]["fix_both"], 3) for sd in sorted(st)],
                               "inflation_mean": round(float(np.mean(infl)), 3),
                               "inflation_per_seed": [round(x, 3) for x in infl],
                               "inflation_ci": [[round(x, 3) for x in ci] for ci in cis],
                               "components_mean": {k: round(v, 3) for k, v in g4.components(st).items()},
                               "fidelity": lr.get("fidelity"), "A": lr["final_plan"].get("A"), "B": lr["final_plan"].get("B"),
                               "kinds": {X: (lr["final_plan"].get("edits") or {}).get(X, {}).get("kind") for X in "AB"},
                               "planner_pred_pp": lr["final_plan"].get("predicted_drop_pp")}
                if "roc_auc" in st[sorted(st)[0]] and st[sorted(st)[0]]["roc_auc"]:
                    row["loop"]["roc_auc_claimed_controlled"] = [[round(st[sd]["roc_auc"]["acc"]["orig"], 3),
                                                                  round(st[sd]["roc_auc"]["acc"]["fix_both"], 3)] for sd in sorted(st)]
            lo = row["loop"]
            if c in LEAKY:
                pub = PUBLISHED[c]["inflation"]
                lo["published_inflation"] = pub
                lo["magnitude_ok"] = "inflation_mean" in lo and abs(lo["inflation_mean"] - pub) <= TOL
                lo["published_in_ci_seeds"] = sum(ci[0] <= pub <= ci[1] for ci in lo.get("inflation_ci", []))
                lo["reproduces"] = lo["sign"] == "+" and lo["magnitude_ok"]
            else:
                lo["false_alarm"] = lo["sign"] == "+"
            b = res["b3"].get(c, {})
            if "ans" in b:
                a = b["ans"]
                fb = float(a["predicted_drop_pp"]["fix_both"])
                bb = {"leak": bool(a.get("leak")), "fix_both_pp": fb, "A": a.get("A"), "B": a.get("B"),
                      "culprit": (a.get("culprit_ranking") or [None])[0]}
                if c in LEAKY:
                    bb["gets_it"] = bb["leak"] and fb >= 2 and abs(fb / 100 - PUBLISHED[c]["inflation"]) <= TOL
                else:
                    bb["false_alarm"] = bb["leak"]
                row["b3"] = bb
            else:
                row["b3"] = {"error": b.get("error", "not run")}
            rows[c][f"r{r}"] = row
    rep = {c: sum(bool(rows[c][r]["loop"].get("reproduces")) for r in rows[c]) for c in LEAKY}
    fa = sum(bool(rows[c][r]["loop"].get("false_alarm")) for c in CLEAN for r in rows[c])
    n_clean = sum(len(rows[c]) for c in CLEAN)
    acc = {"a_civilwar_reproduces": f"{rep['civilwar_apparent']}/{len(rows['civilwar_apparent'])}",
           "a_pass": rep["civilwar_apparent"] >= 2,
           "b_esl_reproduces": f"{rep['esl_selection']}/{len(rows['esl_selection'])}", "b_pass": rep["esl_selection"] >= 2,
           "c_clean_false_alarms": f"{fa}/{n_clean}", "c_pass": fa == 0 and n_clean == 6,
           "clean_inconclusive": sum(rows[c][r]["loop"]["sign"] == "INCONCLUSIVE" for c in CLEAN for r in rows[c]),
           "leaky_inconclusive": sum(rows[c][r]["loop"]["sign"] == "INCONCLUSIVE" for c in LEAKY for r in rows[c]),
           "retries": sum(rows[c][r]["loop"].get("retries", 0) for c in CASES for r in rows[c]),
           "b3_gets_it": {c: f"{sum(bool(rows[c][r]['b3'].get('gets_it')) for r in rows[c])}/{len(rows[c])}" for c in LEAKY},
           "b3_clean_false_alarms": f"{sum(bool(rows[c][r]['b3'].get('false_alarm')) for c in CLEAN for r in rows[c])}/{n_clean}"}
    acc["PASS"] = acc["a_pass"] and acc["b_pass"] and acc["c_pass"]
    variance = {c: {"loop_inflation_mean_per_repeat": [rows[c][r]["loop"].get("inflation_mean") for r in rows[c]],
                    "sd": (round(float(np.std([rows[c][r]["loop"]["inflation_mean"] for r in rows[c] if "inflation_mean" in rows[c][r]["loop"]], ddof=1)), 3)
                           if sum("inflation_mean" in rows[c][r]["loop"] for r in rows[c]) > 1 else None),
                    "b3_fix_both_pp": [rows[c][r]["b3"].get("fix_both_pp") for r in rows[c]]} for c in CASES}
    out = {"rule_sha256": _sha({"rule": SCORING_RULE, "published": PUBLISHED, "tol": TOL}), "acceptance": acc,
           "variance": variance, "cases": rows}
    _save("score", out)
    print(json.dumps(acc, indent=1))
    for c in CASES:
        for r, x in rows[c].items():
            lo, b = x["loop"], x["b3"]
            print(f"{c:24s} {r} loop {lo['sign']:12s} {lo.get('per_seed')} claimed={lo.get('claimed')} controlled={lo.get('controlled')} "
                  f"infl={lo.get('inflation_mean')} repro={lo.get('reproduces', '-')} FA={lo.get('false_alarm', '-')} kinds={lo.get('kinds')} | "
                  f"B3 leak={b.get('leak')} pp={b.get('fix_both_pp')} gets={b.get('gets_it', '-')} FA={b.get('false_alarm', '-')}")


if __name__ == "__main__":
    {"ref": ref, "replay": replay, "rule": rule, "probe": probe, "run": run, "score": score}[sys.argv[1]](sys.argv[2:])
