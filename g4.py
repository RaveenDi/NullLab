"""G4 driver: 4 new compositional cases + 4 clean cases, preregistered B3 vs loop. Outputs in runs_g4/.
Stages (python g4.py <stage> [case ...]):
  ref      evaluator reference factorial (builder-written patches from eval/factorial_truth_g4.json) -> ground truth.
           Run BEFORE preregistration to validate the designs (as in the spike); never shown to an agent.
  rule     hash + log the scoring rule and every case's agent-view hashes (prereg_log.jsonl)        [no live call]
  b3       ONE live single-prompt call per case (no execution); hashed + logged before anything of the loop runs
  plan     ONE live loop-planner call per case (writes fix_A / fix_B / fix_both + predicted drops); hashed + logged
  loop     runs the planner's patches: 4 configs x seeds 42/43/44, n_boot=1000, unpaired bootstrap
  score    applies the preregistered rule (SCORING_RULE) -> runs_g4/score.json"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "runs_g4"
SEEDS = (42, 43, 44)
N_BOOT = 1000
NEW = ["g4_freight_delay", "g4_pump_inspection", "g4_crop_irrigation", "g4_assay_replicates"]
CLEAN = {"clean_control": ROOT / "corpus" / "clean_control", "clean_group_correct": ROOT / "corpus" / "clean_group_correct",
         "clean_wine_correct": ROOT / "corpus" / "clean_wine_correct",
         "g4_visit_history_clean": ROOT / "factorial" / "g4_visit_history_clean"}
CASES = {**{c: ROOT / "factorial" / c for c in NEW}, **CLEAN}

SCORING_RULE = """G4 scoring rule (fixed before any B3 / planner / loop run).
SIGN of a fix-both measurement on one seed: '+' if the 95% CI of drop_fix_both (orig - fix_both) is entirely > 0,
'-' if entirely < 0, '0' if it spans 0. A case's sign = the category shared by >= 2 of seeds 42/43/44, else 'mixed'.
TRUTH (new cases): the sign, components and culprit come from the EVALUATOR reference patches (builder-written,
eval/factorial_truth_g4.json), run with the same sandbox and statistics. Truth verdict = INFLATED iff truth sign '+'.
Truth culprit (only defined when truth sign is '+') = argmax over {A: mean drop_fix_A, B: mean drop_fix_B, AxB: mean I}.
LOOP sign = the same rule applied to the loop's own run of the planner's LIVE-written patches. Loop correct iff loop
sign == truth sign. Loop verdict = INFLATED iff loop sign '+'.
B3 (one live call, no execution): sign = '+' if predicted fix_both drop >= +2pp, '-' if <= -2pp, else '0'.
B3 verdict = INFLATED iff its 'leak' field is true. B3 culprit = its culprit_ranking[0], after mapping its A/B labels
onto ours by meaning (mapping logged before the loop runs). B3 is WRONG on a case iff sign != truth sign OR
verdict != truth verdict OR (truth culprit defined AND B3 culprit != truth culprit).
CLEAN cases (3 frozen corpus controls + 1 clean factorial variant): loop false alarm iff loop sign is '+'.
Strict check reported alongside: fix-both CI spans 0 on all 3 seeds.
ACCEPTANCE: loop sign correct on >= 3/4 new cases AND B3 wrong on >= 2/4 new cases AND loop false alarms 0/4 clean.
If B3 is right on nearly everything (wrong on <= 1/4), the finding is: execution adds quantification only."""


def _save(name, obj):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1))


def _load(name, default=None):
    p = OUT / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else default


def _hashes(case_dir):
    return {n: hashlib.sha256((case_dir / n).read_bytes()).hexdigest() for n in ("train.py", "data.csv", "excerpt.md")}


def _prereg_log(kind, obj, case=None):
    blob = json.dumps(obj, sort_keys=True)
    rec = {"kind": kind, "case": case, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "sha256": hashlib.sha256(blob.encode()).hexdigest()}
    if case:
        rec["agent_view_sha256"] = _hashes(CASES[case])
    OUT.mkdir(exist_ok=True)
    with (OUT / "prereg_log.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print("PREREG", kind, case, rec["sha256"][:16])
    return rec


def _measure(case_dir, patches, label):
    from sandbox import executor, factorial_stats
    t0 = time.time()
    ex = executor.run_factorial(case_dir, patches, seeds=SEEDS, timeout=1500)
    out = {"label": label, "status": ex["status"], "backend": ex["backend"], "elapsed_s": round(time.time() - t0, 1)}
    if ex["status"] != "ok":
        out["stderr"] = ex.get("stderr", "")
        return out
    out["stats"] = factorial_stats.all_seeds(ex["result"], n_boot=N_BOOT)
    return out


def _print(case, m):
    print(f"== {case}: {m['label'][:40]} {m['status']} {m.get('elapsed_s')}s", m.get("stderr", "")[-800:])
    for s, r in m.get("stats", {}).items():
        f = r["full"]
        print(f" seed {s}: acc " + " ".join(f"{k}={v:.3f}" for k, v in f["acc"].items()) + f" n={f['n']['orig']}/{f['n']['fix_both']}")
        print("   drops " + " ".join(f"{k}={v*100:+.1f}[{f['drop_ci'][k][0]*100:+.1f},{f['drop_ci'][k][1]*100:+.1f}]" for k, v in f["drop"].items())
              + f"  I={f['I']*100:+.1f}[{f['I_ci'][0]*100:+.1f},{f['I_ci'][1]*100:+.1f}]")


def _sel(args, pool):
    return [a for a in args if a in pool] or list(pool)


def ref(args):
    truth = json.loads((ROOT / "eval" / "factorial_truth_g4.json").read_text())
    res = _load("ref", {})
    for c in _sel(args, [k for k in truth]):
        m = _measure(CASES[c], truth[c]["ref_patches"], "REFERENCE (builder-written evaluator patches)")
        res[c] = m
        _print(c, m)
        _save("ref", res)


def rule(args):
    _prereg_log("scoring_rule", {"rule": SCORING_RULE})
    for c in CASES:
        _prereg_log("agent_view_frozen", _hashes(CASES[c]), c)


def b3(args):
    from baselines import single_prompt
    res = _load("b3", {})
    for c in _sel(args, CASES):
        if c in res and "error" not in res[c]:
            continue
        try:
            ans, raw = single_prompt.b3_factorial(CASES[c])
            res[c] = {"ans": ans, "raw": raw}
            rec = _prereg_log("b3_single_prompt", {k: ans.get(k) for k in ("leak", "A", "B", "predicted_drop_pp", "culprit_ranking")}, c)
            res[c]["prereg_sha256"] = rec["sha256"]
            print(c, json.dumps({k: ans.get(k) for k in ("leak", "A", "B", "predicted_drop_pp", "culprit_ranking", "confidence")})[:900])
        except Exception as e:  # noqa: BLE001
            res[c] = {"error": repr(e)[:600]}
            print(c, "B3 ERROR", repr(e)[:300])
        _save("b3", res)


def plan(args):
    from agent import factorial
    res = _load("plan", {})
    for c in _sel(args, CASES):
        if c in res and "error" not in res[c]:
            continue
        try:
            p, raw = factorial.plan(CASES[c])
            res[c] = {"plan": p, "raw": raw}
            rec = _prereg_log("loop_planner", {k: p.get(k) for k in ("A", "B", "patches", "predicted_drop_pp", "culprit_ranking")}, c)
            res[c]["prereg_sha256"] = rec["sha256"]
            print(c, json.dumps({k: p.get(k) for k in ("A", "B", "predicted_drop_pp", "culprit_ranking")})[:900])
        except Exception as e:  # noqa: BLE001
            res[c] = {"error": repr(e)[:600]}
            print(c, "PLAN ERROR", repr(e)[:300])
        _save("plan", res)


def loop(args):
    pl = _load("plan")
    res = _load("loop", {})
    for c in _sel(args, [k for k in pl if "plan" in pl[k]]):
        m = _measure(CASES[c], pl[c]["plan"]["patches"], "LOOP (patches written LIVE by muse-spark-1.3 planner)")
        res[c] = m
        _print(c, m)
        _save("loop", res)


# ---------------- scoring ----------------
def seed_sign(lo, hi):
    return "+" if lo > 0 else ("-" if hi < 0 else "0")


def case_sign(stats):
    cats = [seed_sign(*stats[s]["full"]["drop_ci"]["fix_both"]) for s in sorted(stats)]
    for k in ("+", "-", "0"):
        if cats.count(k) >= 2:
            return k, cats
    return "mixed", cats


def components(stats):
    ss = sorted(stats)
    mean = lambda f: sum(f(stats[s]["full"]) for s in ss) / len(ss)  # noqa: E731
    return {"A": mean(lambda r: r["drop"]["fix_A"]), "B": mean(lambda r: r["drop"]["fix_B"]),
            "AxB": mean(lambda r: r["I"]), "both": mean(lambda r: r["drop"]["fix_both"])}


def b3_sign(pp):
    return "+" if pp >= 2 else ("-" if pp <= -2 else "0")


def score(args):
    refm, b3r, pl, lp = _load("ref"), _load("b3"), _load("plan"), _load("loop")
    mapping = _load("b3_label_map", {})  # {case: {"A": "A"|"B", "B": "A"|"B"}} logged before the loop ran
    rows = {}
    for c in CASES:
        r = {"kind": "NEW" if c in NEW else "CLEAN"}
        if c in refm and refm[c]["status"] == "ok":
            ts, tcats = case_sign(refm[c]["stats"])
            comp = components(refm[c]["stats"])
            r["truth"] = {"sign": ts, "per_seed": tcats, "components_pp": {k: round(v * 100, 1) for k, v in comp.items()},
                          "verdict": "INFLATED" if ts == "+" else "NOT INFLATED",
                          "culprit": max(("A", "B", "AxB"), key=lambda k: comp[k]) if ts == "+" else None}
        if c in lp and lp[c]["status"] == "ok":
            ls, lcats = case_sign(lp[c]["stats"])
            comp = components(lp[c]["stats"])
            r["loop"] = {"sign": ls, "per_seed": lcats, "components_pp": {k: round(v * 100, 1) for k, v in comp.items()},
                         "fix_both_ci_pp": {s: [round(x * 100, 1) for x in lp[c]["stats"][s]["full"]["drop_ci"]["fix_both"]] for s in sorted(lp[c]["stats"])},
                         "I_ci_pp": {s: [round(x * 100, 1) for x in lp[c]["stats"][s]["full"]["I_ci"]] for s in sorted(lp[c]["stats"])},
                         "measured_culprit": max(("A", "B", "AxB"), key=lambda k: comp[k]),
                         "planner_pred_pp": pl[c]["plan"].get("predicted_drop_pp"), "planner_ranking": pl[c]["plan"].get("culprit_ranking"),
                         "planner_A": pl[c]["plan"].get("A"), "planner_B": pl[c]["plan"].get("B")}
            r["loop"]["false_alarm"] = ls == "+"
            r["loop"]["strict_spans0_all_seeds"] = all(x == "0" for x in lcats)
        elif c in lp:
            r["loop"] = {"status": lp[c]["status"], "stderr": lp[c].get("stderr", "")[-400:]}
        if c in b3r and "ans" in b3r[c]:
            a = b3r[c]["ans"]
            fb = float(a["predicted_drop_pp"]["fix_both"])
            mp = mapping.get(c, {"A": "A", "B": "B"})
            top = a["culprit_ranking"][0] if a.get("culprit_ranking") else None
            top_m = {"A": mp.get("A"), "B": mp.get("B"), "AxB": "AxB"}.get(top, top)
            r["b3"] = {"sign": b3_sign(fb), "fix_both_pp": fb, "verdict": "INFLATED" if a.get("leak") else "NOT INFLATED",
                       "culprit_raw": top, "culprit_mapped": top_m, "label_map": mp, "pred_pp": a["predicted_drop_pp"],
                       "confidence": a.get("confidence")}
        if "truth" in r:
            t = r["truth"]
            if "loop" in r and "sign" in r["loop"]:
                r["loop"]["sign_correct"] = r["loop"]["sign"] == t["sign"]
            if "b3" in r:
                b = r["b3"]
                b["sign_wrong"] = b["sign"] != t["sign"]
                b["verdict_wrong"] = b["verdict"] != t["verdict"]
                b["culprit_wrong"] = (t["culprit"] is not None) and (b["culprit_mapped"] != t["culprit"])
                b["wrong"] = b["sign_wrong"] or b["verdict_wrong"] or b["culprit_wrong"]
            if "loop" in r and "sign" in r["loop"] and "b3" in r:
                lo = [lp[c]["stats"][s]["full"]["drop_ci"]["fix_both"] for s in sorted(lp[c]["stats"])]
                r["b3"]["point_outside_loop_ci_all_seeds"] = all(not (x[0] <= r["b3"]["fix_both_pp"] / 100 <= x[1]) for x in lo)
        rows[c] = r
    new = [rows[c] for c in NEW]
    clean = [rows[c] for c in CLEAN]
    loop_ok = sum(bool(r.get("loop", {}).get("sign_correct")) for r in new)
    b3_wrong = sum(bool(r.get("b3", {}).get("wrong")) for r in new)
    fa = sum(bool(r.get("loop", {}).get("false_alarm")) for r in clean)
    acc = {"loop_sign_correct_new": f"{loop_ok}/4", "b3_wrong_new": f"{b3_wrong}/4", "loop_false_alarms_clean": f"{fa}/4",
           "strict_clean_spans0_all_seeds": f"{sum(bool(r.get('loop', {}).get('strict_spans0_all_seeds')) for r in clean)}/4",
           "b3_false_alarms_clean": f"{sum(r.get('b3', {}).get('verdict') == 'INFLATED' for r in clean)}/4",
           "PASS": loop_ok >= 3 and b3_wrong >= 2 and fa == 0}
    out = {"rule_sha256": hashlib.sha256(json.dumps({"rule": SCORING_RULE}, sort_keys=True).encode()).hexdigest(),
           "acceptance": acc, "cases": rows}
    _save("score", out)
    print(json.dumps(acc, indent=1))
    for c, r in rows.items():
        t, l, b = r.get("truth", {}), r.get("loop", {}), r.get("b3", {})
        print(f"{c:24s} truth {t.get('sign')} {t.get('culprit')} {t.get('components_pp')} | loop {l.get('sign')} {l.get('per_seed')} "
              f"{l.get('components_pp')} | B3 {b.get('sign')} {b.get('fix_both_pp')} {b.get('verdict')} {b.get('culprit_mapped')} wrong={b.get('wrong')}")


if __name__ == "__main__":
    {"ref": ref, "rule": rule, "b3": b3, "plan": plan, "loop": loop, "score": score}[sys.argv[1]](sys.argv[2:])
