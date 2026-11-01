"""G5 driver: patch-fidelity guard + 3 independent repeats of B3 and the guarded loop on the G4 cases. Outputs in runs_g5/.
Stages (.venv\\Scripts\\python g5.py <stage> ...):
  replay      OFFLINE: guard on G4's legacy patches + builder fixtures (no live call)       -> runs_g5/replay.json
  rule        hash + log the scoring rule, guard/prompt source hashes, agent views           -> runs_g5/prereg_log.jsonl
  run <r>     repeat r (1..3): B3 x 8 (logged), planner x 8 (logged), then guarded loop x 8  -> runs_g5/r<r>.json
  score       preregistered acceptance                                                       -> runs_g5/score.json"""
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "runs_g5"
sys.path.insert(0, str(ROOT))
import g4  # noqa: E402  (case table, sign rule, B3 sign rule, components)
from agent import factorial_g5, fidelity, llm  # noqa: E402

SEEDS, N_BOOT = (42, 43, 44), 1000
HARD, CLEAN, CASES = g4.NEW, list(g4.CLEAN), g4.CASES
CEILING_USD = 22.0
EST = {"b3": 0.08, "plan": 0.10, "retry": 0.10}

# B3 label mapping by meaning (fixed before any G5 call): keyword hits decide which of OUR flaws a B3 label names.
B3_KEYWORDS = {
    "g4_freight_delay": {"A": ["carrier", "rate", "groupby", "target mean", "late-rate", "late rate"],
                         "B": ["fillna", "dwell", "imput", "missing", "zero"]},
    "g4_pump_inspection": {"A": ["selectkbest", "select", "f_classif", "feature selection", "anova"],
                           "B": ["shift", "lag", "prev", "next", "look-ahead", "future"]},
    "g4_crop_irrigation": {"A": ["scal", "pca", "standard", "decorrelat"], "B": ["grid", "tun", "hyperparam", "param"]},
    "g4_assay_replicates": {"A": ["imput", "fill", "failed", "per-class", "class mean", "label"],
                            "B": ["split", "replicate", "well", "group", "new compound", "triplicate"]},
}

SCORING_RULE = """G5 scoring rule (fixed before any G5 live call). Cases: 4 hard (g4_freight_delay, g4_pump_inspection,
g4_crop_irrigation, g4_assay_replicates) + 4 clean (clean_control, clean_group_correct, clean_wine_correct,
g4_visit_history_clean). 3 independent repeats r1..r3: fresh live calls; the only difference between repeats is the
line '[repeat id: g5-rK]' appended to the user message (temperature stays 0). Per repeat: B3 x 8 first (each hashed and
logged), then the loop planner x 8 (each hashed and logged), then execution.
LOOP = agent/factorial_g5.py planner (structured edits against named steps of train.py, applied by code) + the
patch-fidelity guard agent/fidelity.py (LOCALITY, MODEL, FEATURES, SPLIT static checks; SAMPLE SIZE runtime check).
Recover: on any guard rejection or execution error, ONE live retry with the violation/error text; if the retry still
fails, the case-repeat is INCONCLUSIVE (never FALSIFIED). Measurement: 4 configs x seeds 42/43/44, n_boot=1000,
UNPAIRED bootstrap. SIGN per seed: '+' if the 95% CI of drop_fix_both (orig - fix_both) > 0, '-' if < 0, '0' if it
spans 0; case-repeat sign = category shared by >= 2 of 3 seeds, else 'mixed'. Loop verdict = INFLATED iff sign '+'.
TRUTH (hard cases) = runs_g4/ref.json (builder reference patches, unchanged): freight '-', pump '+' culprit B,
crop '0', assay '+' culprit AxB. Clean truth = '0'.
(i)  loop clean false alarms (sign '+') <= 1 of 12 clean case-repeats.
(ii) loop sign == truth sign in >= 10 of 12 hard case-repeats (INCONCLUSIVE or 'mixed' counts as wrong).
(iii) B3 wrong in >= 6 of 12 hard case-repeats; B3 wrong iff sign != truth sign OR verdict (leak) != truth verdict OR
     (truth culprit defined AND B3 top culprit, mapped onto our labels by B3_KEYWORDS hit counts, != truth culprit).
     B3 sign: '+' if predicted fix_both drop >= +2pp, '-' if <= -2pp, else '0'. A tie in the mapping = unmapped.
(iv) every executed (accepted) config passes the static fidelity check again at scoring time and the runtime check.
PASS iff (i)-(iv) all hold. Reported alongside (not acceptance): clean INCONCLUSIVE count, retries used, B3 clean false
alarms, per-repeat fix_both drops and interaction with CIs, run-to-run SD of the mean fix_both drop per case."""


def _save(name, obj):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1))


def _load(name, default=None):
    p = OUT / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else default


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _prereg(kind, obj, case=None, repeat=None):
    rec = {"kind": kind, "case": case, "repeat": repeat, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "sha256": _sha(obj)}
    if case:
        rec["agent_view_sha256"] = g4._hashes(CASES[case])
    OUT.mkdir(exist_ok=True)
    with (OUT / "prereg_log.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print("PREREG", kind, case, repeat, rec["sha256"][:16], flush=True)
    return rec


def spent_meta():
    r = subprocess.run([sys.executable, str(llm.BS), "spend"], capture_output=True, text=True)
    return float(json.loads(r.stdout)["meta"]["spent_usd"])


def _budget_ok(n_calls_usd):
    s = spent_meta()
    if s + n_calls_usd > CEILING_USD:
        print(f"STOP: spent ${s:.2f} + projected ${n_calls_usd:.2f} passes the ${CEILING_USD} ceiling", flush=True)
        return False
    return True


# ---------------- offline replay ----------------
def replay(args):
    from eval import g5_fixtures as fx
    allk = list(fidelity.KINDS)
    out = {"legacy_g4_planner": {}, "legacy_g4_reference": {}, "legacy_spike_planner": {}, "structured_fixtures": {}}
    plan = json.loads((ROOT / "runs_g4" / "plan.json").read_text())
    truth = json.loads((ROOT / "eval" / "factorial_truth_g4.json").read_text())
    spike = json.loads((ROOT / "runs_spike4" / "prereg.json").read_text())["loop_plan"]["patches"]
    srcs = {c: (CASES[c] / "train.py").read_text(encoding="utf-8") for c in CASES}
    srcs["comp_visit_history"] = (ROOT / "factorial" / "comp_visit_history" / "train.py").read_text(encoding="utf-8")

    def legacy(bucket, c, patches):
        for cfg, p in patches.items():
            v, _ = fidelity.check_static(srcs[c], patch_src=p, kinds=allk)  # most permissive kinds
            inv = [x for x in v if not x.startswith("STRUCTURE: whole-file")]
            out[bucket][f"{c}/{cfg}"] = {"invariant_violations": inv, "invariants": "REJECT" if inv else "ok",
                                         "structured": False}
    for c in plan:
        legacy("legacy_g4_planner", c, plan[c]["plan"]["patches"])
    for c in truth:
        legacy("legacy_g4_reference", c, truth[c]["ref_patches"])
    legacy("legacy_spike_planner", "comp_visit_history", spike)
    for name, case in (("GOOD_SPIKE", "comp_visit_history"), ("GOOD_PUMP", "g4_pump_inspection"),
                       ("BAD_GROUP_FEATURE_DROP", "clean_group_correct"), ("BAD_GROUP_MODEL", "clean_group_correct")):
        cfgs = fidelity.build_configs(srcs[case], getattr(fx, name))
        for cfg, info in cfgs.items():
            v = list(info["violations"])
            rep = {}
            if not v:
                sv, rep = fidelity.check_static(srcs[case], info["src"], info["kinds"], info["declared"])
                v += sv
            out["structured_fixtures"][f"{name}/{cfg}"] = {"verdict": "REJECT" if v else "ACCEPT", "violations": v,
                                                           "changed": rep.get("changed")}
    _save("replay", out)
    for b, rows in out.items():
        for k, r in rows.items():
            print(f"{b:22s} {k:42s} {r.get('verdict', r.get('invariants'))} {(r.get("violations") or r.get("invariant_violations") or [])[:1]}")


# ---------------- preregistration ----------------
def rule(args):
    src = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in
           ("agent/fidelity.py", "agent/factorial_g5.py", "baselines/single_prompt.py", "g5.py", "eval/g5_fixtures.py")}
    _prereg("scoring_rule", {"rule": SCORING_RULE, "b3_keywords": B3_KEYWORDS})
    _prereg("source_hashes", src)
    _prereg("prompts", {"planner_system": factorial_g5.SYSTEM, "b3_system": __import__("baselines.single_prompt").single_prompt.FACTORIAL_SYSTEM})
    for c in CASES:
        _prereg("agent_view_frozen", g4._hashes(CASES[c]), c)


# ---------------- one repeat ----------------
def _b3(c, rid):
    from agent.factorial import agent_view
    from baselines.single_prompt import FACTORIAL_SYSTEM
    raw = llm.live_complete(FACTORIAL_SYSTEM, agent_view(CASES[c]) + f"\n\n[repeat id: {rid}]", est_usd=EST["b3"], tag="g5_b3")
    return llm.parse_json(raw), raw


def _parallel(fn, cases, rid, workers=4):
    res = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {c: ex.submit(fn, c, rid) for c in cases}
        for c, f in futs.items():
            try:
                res[c] = f.result()
            except Exception as e:  # noqa: BLE001
                res[c] = e
    return res


def _guard(case, edits):
    src = (CASES[case] / "train.py").read_text(encoding="utf-8")
    cfgs = fidelity.build_configs(src, edits)
    problems, reports = [], {}
    for cfg, info in cfgs.items():
        v = list(info["violations"])
        if not v:
            sv, rep = fidelity.check_static(src, info["src"], info["kinds"], info["declared"])
            v += sv
            reports[cfg] = {"changed": rep.get("changed"), "kinds": info["kinds"]}
        problems += [f"{cfg}: {x}" for x in v]
    return cfgs, problems, reports


def _execute(case, cfgs):
    from sandbox import executor
    patches = {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}
    ex = executor.run_factorial(CASES[case], patches, seeds=SEEDS, timeout=1500)
    if ex["status"] != "ok":
        return None, [f"EXECUTION {ex['status']}: {ex.get('stderr', '')[-1500:]}"]
    rv = fidelity.check_runtime(ex["result"], {k: cfgs[k]["kinds"] for k in ("fix_A", "fix_B", "fix_both")})
    return ex["result"], rv


def loop_case(case, rid, plan_rec):
    """Plan -> Act -> Verify -> Recover for one case-repeat. Returns a record with a full event log."""
    from sandbox import factorial_stats
    log = [{"phase": "Plan", "utc": time.strftime("%H:%M:%SZ", time.gmtime()), "prereg_sha256": plan_rec["plan"].get("prereg_sha256")}]
    cur, retried, rec = plan_rec["plan"], False, {"retries": 0}
    while True:
        cfgs, problems, reports = _guard(case, cur.get("edits"))
        log.append({"phase": "Verify (static fidelity)", "verdict": "REJECT" if problems else "ACCEPT",
                    "violations": problems[:8], "changed": reports})
        raw = None
        if not problems:
            raw, problems = _execute(case, cfgs)
            log.append({"phase": "Act (sandbox, 4 configs x 3 seeds)", "status": "ok" if raw is not None else "error",
                        "runtime_violations": problems[:8]})
        if not problems:
            break
        if retried:
            rec.update({"status": "INCONCLUSIVE", "reason": problems[:8], "log": log, "final_plan": cur})
            log.append({"phase": "Report", "verdict": "INCONCLUSIVE (guard/execution still failing after one retry)"})
            return rec
        if not _budget_ok(EST["retry"]):
            rec.update({"status": "INCONCLUSIVE", "reason": ["budget ceiling: no retry"] + problems[:8], "log": log, "final_plan": cur})
            return rec
        try:
            cur, rawtxt = factorial_g5.retry(CASES[case], rid, cur, problems[:8])
        except Exception as e:  # noqa: BLE001
            rec.update({"status": "INCONCLUSIVE", "reason": [f"retry call failed: {e!r}"[:400]] + problems[:8], "log": log, "final_plan": cur})
            return rec
        retried, rec["retries"] = True, 1
        r = _prereg("loop_planner_retry", {k: cur.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")}, case, rid)
        log.append({"phase": "Recover (one live retry with the violation text)", "prereg_sha256": r["sha256"],
                    "retry_raw_len": len(rawtxt)})
    stats = factorial_stats.all_seeds(raw, n_boot=N_BOOT)
    rec.update({"status": "ok", "stats": stats, "final_plan": cur, "log": log,
                "fidelity": {cfg: fidelity.verdict_line(cfgs[cfg], reports[cfg]) for cfg in reports},
                "sources": {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}})
    log.append({"phase": "Report", "verdict": "measured"})
    return rec


def run(args):
    r = int(args[0])
    rid = f"g5-r{r}"
    res = _load(f"r{r}", {"repeat": rid, "b3": {}, "plan": {}, "loop": {}})
    todo_b3 = [c for c in CASES if c not in res["b3"] or "error" in res["b3"][c]]
    todo_plan = [c for c in CASES if c not in res["plan"] or "error" in res["plan"][c]]
    proj = len(todo_b3) * EST["b3"] + len(todo_plan) * (EST["plan"] + EST["retry"])
    if not _budget_ok(proj):
        return
    for c, v in _parallel(_b3, todo_b3, rid).items():
        if isinstance(v, Exception):
            res["b3"][c] = {"error": repr(v)[:600]}
            print(c, "B3 ERROR", repr(v)[:300], flush=True)
            continue
        ans, raw = v
        rec = _prereg("b3_single_prompt", {k: ans.get(k) for k in ("leak", "A", "B", "predicted_drop_pp", "culprit_ranking")}, c, rid)
        res["b3"][c] = {"ans": ans, "raw": raw, "prereg_sha256": rec["sha256"]}
    _save(f"r{r}", res)
    for c, v in _parallel(lambda c, rid: factorial_g5.plan(CASES[c], rid), todo_plan, rid).items():
        if isinstance(v, Exception):
            res["plan"][c] = {"error": repr(v)[:600]}
            print(c, "PLAN ERROR", repr(v)[:300], flush=True)
            continue
        p, raw = v
        rec = _prereg("loop_planner", {k: p.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")}, c, rid)
        res["plan"][c] = {"plan": p, "raw": raw, "prereg_sha256": rec["sha256"]}
    _save(f"r{r}", res)
    for c in CASES:
        if c in res["loop"] or "plan" not in res["plan"].get(c, {}):
            continue
        t0 = time.time()
        res["loop"][c] = loop_case(c, rid, res["plan"][c])
        lr = res["loop"][c]
        sgn = g4.case_sign(lr["stats"]) if lr["status"] == "ok" else ("INCONCLUSIVE", None)
        print(f"{rid} {c:24s} {lr['status']} retries={lr['retries']} sign={sgn} {time.time() - t0:.0f}s", flush=True)
        _save(f"r{r}", res)


# ---------------- scoring ----------------
def map_b3(case, ans):
    kw = B3_KEYWORDS.get(case)
    mp = {}
    for lab in ("A", "B"):
        txt = str(ans.get(lab, "")).lower()
        if not kw:
            mp[lab] = lab
            continue
        hits = {ours: sum(k in txt for k in kw[ours]) for ours in ("A", "B")}
        mp[lab] = None if hits["A"] == hits["B"] else max(hits, key=hits.get)
    return mp


def score(args):
    refm = json.loads((ROOT / "runs_g4" / "ref.json").read_text())
    truth = {}
    for c in HARD:
        ts, _ = g4.case_sign(refm[c]["stats"])
        comp = g4.components(refm[c]["stats"])
        truth[c] = {"sign": ts, "verdict": "INFLATED" if ts == "+" else "NOT INFLATED",
                    "culprit": max(("A", "B", "AxB"), key=lambda k: comp[k]) if ts == "+" else None,
                    "components_pp": {k: round(v * 100, 1) for k, v in comp.items()}}
    for c in CLEAN:
        truth[c] = {"sign": "0", "verdict": "NOT INFLATED", "culprit": None}
    rows, audit = {c: {} for c in CASES}, []
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
                s, cats = g4.case_sign(lr["stats"])
                comp = g4.components(lr["stats"])
                row["loop"] = {"sign": s, "per_seed": cats, "retries": lr["retries"], "fidelity": lr.get("fidelity"),
                               "components_pp": {k: round(v * 100, 1) for k, v in comp.items()},
                               "fix_both_ci_pp": {sd: [round(x * 100, 1) for x in lr["stats"][sd]["full"]["drop_ci"]["fix_both"]] for sd in sorted(lr["stats"])},
                               "I_ci_pp": {sd: [round(x * 100, 1) for x in lr["stats"][sd]["full"]["I_ci"]] for sd in sorted(lr["stats"])},
                               "measured_culprit": max(("A", "B", "AxB"), key=lambda k: comp[k]),
                               "planner_pred_pp": lr["final_plan"].get("predicted_drop_pp")}
                # (iv) audit: re-run the static check on the executed sources
                src = (CASES[c] / "train.py").read_text(encoding="utf-8")
                cfgs = fidelity.build_configs(src, lr["final_plan"].get("edits"))
                for cfg, info in cfgs.items():
                    v = info["violations"] or fidelity.check_static(src, info["src"], info["kinds"], info["declared"])[0]
                    if v or info["src"] != lr["sources"][cfg]:
                        audit.append(f"r{r} {c} {cfg}: {v[:2] or 'source mismatch'}")
            row["loop"]["correct"] = row["loop"]["sign"] == truth[c]["sign"]
            row["loop"]["false_alarm"] = row["loop"]["sign"] == "+" and c in CLEAN
            b = res["b3"].get(c, {})
            if "ans" in b:
                a = b["ans"]
                fb = float(a["predicted_drop_pp"]["fix_both"])
                mp = map_b3(c, a) if c in HARD else {"A": "A", "B": "B"}
                top = (a.get("culprit_ranking") or [None])[0]
                top_m = {"A": mp.get("A"), "B": mp.get("B"), "AxB": "AxB"}.get(top, top)
                bb = {"sign": g4.b3_sign(fb), "fix_both_pp": fb, "verdict": "INFLATED" if a.get("leak") else "NOT INFLATED",
                      "culprit_raw": top, "culprit_mapped": top_m, "label_map": mp, "pred_pp": a["predicted_drop_pp"]}
                t = truth[c]
                bb["sign_wrong"] = bb["sign"] != t["sign"]
                bb["verdict_wrong"] = bb["verdict"] != t["verdict"]
                bb["culprit_wrong"] = t["culprit"] is not None and top_m != t["culprit"]
                bb["wrong"] = bb["sign_wrong"] or bb["verdict_wrong"] or bb["culprit_wrong"]
                row["b3"] = bb
            else:
                row["b3"] = {"wrong": None, "error": b.get("error", "not run")}
            rows[c][f"r{r}"] = row
    hard_runs = [rows[c][r] for c in HARD for r in rows[c]]
    clean_runs = [rows[c][r] for c in CLEAN for r in rows[c]]
    fa = sum(x["loop"]["false_alarm"] for x in clean_runs)
    ok = sum(x["loop"]["correct"] for x in hard_runs)
    b3w = sum(bool(x["b3"].get("wrong")) for x in hard_runs)
    variance = {}
    for c in CASES:
        vals = [rows[c][r]["loop"]["components_pp"]["both"] for r in rows[c] if "components_pp" in rows[c][r]["loop"]]
        variance[c] = {"loop_mean_fix_both_pp_per_repeat": vals,
                       "sd_pp": round(float(__import__("numpy").std(vals, ddof=1)), 1) if len(vals) > 1 else None,
                       "loop_signs": [rows[c][r]["loop"]["sign"] for r in rows[c]],
                       "b3_fix_both_pp": [rows[c][r]["b3"].get("fix_both_pp") for r in rows[c]],
                       "b3_verdicts": [rows[c][r]["b3"].get("verdict") for r in rows[c]]}
    acc = {"i_clean_false_alarms": f"{fa}/{len(clean_runs)}", "i_pass": fa <= 1 and len(clean_runs) == 12,
           "ii_hard_sign_correct": f"{ok}/{len(hard_runs)}", "ii_pass": ok >= 10 and len(hard_runs) == 12,
           "iii_b3_wrong_hard": f"{b3w}/{len(hard_runs)}", "iii_pass": b3w >= 6 and len(hard_runs) == 12,
           "iv_fidelity_audit_failures": audit, "iv_pass": not audit,
           "clean_inconclusive": sum(x["loop"]["sign"] == "INCONCLUSIVE" for x in clean_runs),
           "hard_inconclusive": sum(x["loop"]["sign"] == "INCONCLUSIVE" for x in hard_runs),
           "retries_used": sum(x["loop"].get("retries", 0) for x in hard_runs + clean_runs),
           "b3_clean_false_alarms": f"{sum(x['b3'].get('verdict') == 'INFLATED' for x in clean_runs)}/{len(clean_runs)}"}
    acc["PASS"] = all(acc[k] for k in ("i_pass", "ii_pass", "iii_pass", "iv_pass"))
    out = {"rule_sha256": _sha({"rule": SCORING_RULE, "b3_keywords": B3_KEYWORDS}), "truth": truth, "acceptance": acc,
           "variance": variance, "cases": rows}
    _save("score", out)
    print(json.dumps(acc, indent=1))
    for c in CASES:
        for r, x in rows[c].items():
            lo, b = x["loop"], x["b3"]
            print(f"{c:24s} {r} truth {truth[c]['sign']:2s} | loop {lo['sign']:12s} {lo.get('per_seed')} both={lo.get('components_pp', {}).get('both')} "
                  f"I={lo.get('components_pp', {}).get('AxB')} culprit={lo.get('measured_culprit')} retries={lo.get('retries')} | "
                  f"B3 {b.get('sign')} {b.get('fix_both_pp')} {b.get('verdict')} top={b.get('culprit_mapped')} wrong={b.get('wrong')}")


if __name__ == "__main__":
    {"replay": replay, "rule": rule, "run": run, "score": score}[sys.argv[1]](sys.argv[2:])
