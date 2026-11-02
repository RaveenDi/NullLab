"""BRIEF-4 spike driver (G2 + G3). Stages (each writes runs_spike4/<stage>.json):
  ref      evaluator reference factorial (builder-written patches from eval/factorial_truth.json; validates the case)
  g2       2 LIVE calls on the spike case: claim extractor + falsifier (agent/extract.py, agent/falsify.py)
  prereg   2 LIVE calls: loop planner (writes fix_A/fix_B/fix_both + predicted drops) and B3 single prompt;
           both are hashed and appended to runs_spike4/prereg_log.jsonl BEFORE anything of theirs runs
  loop     runs the planner's patches in the sandbox (4 configs x seeds 42/43/44) + the G2 falsifier patch
  score    applies the BRIEF-4 acceptance + kill rule
Usage: python scripts/legacy/spike4.py <stage>"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))  # repo packages (agent, sandbox, baselines) when run from scripts/legacy
CASE_DIR = ROOT / "factorial" / "comp_visit_history"
OUT = ROOT / "runs_spike4"
SEEDS = (42, 43, 44)
N_BOOT = 1000


def _save(name, obj):
    OUT.mkdir(exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(obj, indent=1))


def _load(name):
    return json.loads((OUT / f"{name}.json").read_text())


def _measure(patches, label):
    from sandbox import executor, factorial_stats
    t0 = time.time()
    ex = executor.run_factorial(CASE_DIR, patches, seeds=SEEDS, timeout=600)
    out = {"label": label, "status": ex["status"], "backend": ex["backend"], "elapsed_s": round(time.time() - t0, 1)}
    if ex["status"] != "ok":
        out["stderr"] = ex.get("stderr", "")
        return out
    out["stats"] = factorial_stats.all_seeds(ex["result"], n_boot=N_BOOT)
    return out


def _print(m):
    print(m["label"], m["status"], m.get("stderr", "")[-600:])
    for s, r in m.get("stats", {}).items():
        f, q = r["full"], r["same_n"]
        print(f" seed {s}: acc " + " ".join(f"{k}={v:.3f}" for k, v in f["acc"].items()) + f"  n={f['n']}")
        print("   drops " + " ".join(f"{k}={v*100:+.1f}pp[{f['drop_ci'][k][0]*100:+.1f},{f['drop_ci'][k][1]*100:+.1f}]" for k, v in f["drop"].items())
              + f"  I={f['I']*100:+.1f}pp CI[{f['I_ci'][0]*100:+.1f},{f['I_ci'][1]*100:+.1f}]"
              + f"  | same-n({q['n']['orig']}) I={q['I']*100:+.1f} CI[{q['I_ci'][0]*100:+.1f},{q['I_ci'][1]*100:+.1f}]")


def ref():
    truth = json.loads((ROOT / "eval" / "factorial_truth.json").read_text())
    m = _measure(truth["ref_patches"], "REFERENCE (builder-written evaluator patches, not agent output)")
    _save("ref", m)
    _print(m)


def _prereg_log(kind, obj):
    blob = json.dumps(obj, sort_keys=True)
    rec = {"kind": kind, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sha256": hashlib.sha256(blob.encode()).hexdigest(),
           "agent_view_sha256": {n: hashlib.sha256((CASE_DIR / n).read_bytes()).hexdigest() for n in ("train.py", "data.csv", "excerpt.md")}}
    OUT.mkdir(exist_ok=True)
    with (OUT / "prereg_log.jsonl").open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print("PREREG", kind, rec["sha256"])
    return rec


def g2():
    from agent import extract, falsify, llm
    out = {}
    try:
        claim = extract.extract_claim(CASE_DIR, "live")
        out["extractor"] = {"parsed": True, "claim": claim, "grounding": claim["grounding"]}
    except Exception as e:  # noqa: BLE001
        out["extractor"] = {"parsed": False, "error": repr(e)[:500]}
        claim = None
    if claim:
        try:
            hyp = falsify.propose(CASE_DIR, claim, "live")
            out["falsifier"] = {"parsed": True, "hyp": hyp}
            _prereg_log("g2_falsifier", {k: hyp.get(k) for k in ("hypotheses", "primary", "code_patch")})
        except Exception as e:  # noqa: BLE001
            out["falsifier"] = {"parsed": False, "error": repr(e)[:500]}
    out["spike_calls_so_far"] = llm._calls_made()
    _save("g2", out)
    print(json.dumps({k: (v if k != "falsifier" else {kk: vv for kk, vv in v.items() if kk != "hyp"}) for k, v in out.items()}, indent=1)[:3000])


# scoring rule, fixed before any loop/B3 run and logged with the preregistration
SCORING_RULE = ("Ground-truth culprit = argmax over {A: mean drop_fix_A, B: mean drop_fix_B, AxB: mean I} across seeds 42-44 "
                "(loop measurement). B3 misranks iff its top-1 culprit (after mapping its A/B labels onto ours by meaning) "
                "differs. B3 point miss iff its predicted fix_both drop lies outside the loop's 95% CI of drop_fix_both "
                "on every seed. Acceptance: I CI excludes 0 on 3/3 seeds AND mean drop_fix_both >= 8pp AND (misrank OR point miss).")


def prereg():
    from agent import factorial
    from baselines import single_prompt
    _prereg_log("scoring_rule", {"rule": SCORING_RULE})
    out = {}
    plan, raw = factorial.plan(CASE_DIR)
    out["loop_plan"] = plan
    out["loop_plan_raw"] = raw
    _prereg_log("loop_planner", {k: plan.get(k) for k in ("A", "B", "patches", "predicted_drop_pp", "culprit_ranking")})
    _save("prereg", out)
    b3, raw3 = single_prompt.b3_factorial(CASE_DIR)
    out["b3"] = b3
    out["b3_raw"] = raw3
    _prereg_log("b3_single_prompt", {k: b3.get(k) for k in ("A", "B", "predicted_drop_pp", "culprit_ranking")})
    _save("prereg", out)
    print(json.dumps({"loop": {k: plan.get(k) for k in ("A", "B", "predicted_drop_pp", "culprit_ranking")},
                      "b3": {k: b3.get(k) for k in ("leak", "A", "B", "predicted_drop_pp", "culprit_ranking", "confidence")}}, indent=1))


def loop():
    from sandbox import executor
    pre = _load("prereg")
    m = _measure(pre["loop_plan"]["patches"], "LOOP (patches written LIVE by muse-spark-1.3 planner)")
    _save("loop", m)
    _print(m)
    g2r = _load("g2")
    if g2r.get("falsifier", {}).get("parsed"):
        ex = executor.run_experiment(CASE_DIR, g2r["falsifier"]["hyp"]["code_patch"], seeds=SEEDS, n_boot=N_BOOT,
                                     timeout=300, backend="subprocess")
        g2r["falsifier_run"] = ex
        _save("g2", g2r)
        print("G2 falsifier patch:", ex["status"], {s: round(r["delta"], 3) for s, r in ex.get("result", {}).get("seeds", {}).items()},
              ex.get("stderr", "")[-300:])


def score():
    """Applies SCORING_RULE. B3's and the planner's A/B labels map 1:1 onto ours (both name the patient-rate feature as A
    and the visit-level random split as B; checked by reading runs_spike4/prereg.json)."""
    pre, lp = _load("prereg"), _load("loop")
    st = lp["stats"]
    seeds = sorted(st)
    mean = lambda f: sum(f(st[s]["full"]) for s in seeds) / len(seeds)  # noqa: E731
    comp = {"A": mean(lambda r: r["drop"]["fix_A"]), "B": mean(lambda r: r["drop"]["fix_B"]), "AxB": mean(lambda r: r["I"])}
    truth_top = max(comp, key=comp.get)
    b3 = pre["b3"]
    b3_fb = b3["predicted_drop_pp"]["fix_both"] / 100
    outside = {s: not (st[s]["full"]["drop_ci"]["fix_both"][0] <= b3_fb <= st[s]["full"]["drop_ci"]["fix_both"][1]) for s in seeds}
    i_ex = {s: st[s]["full"]["I_excludes_0"] for s in seeds}
    i_ex_same_n = {s: st[s]["same_n"]["I_excludes_0"] for s in seeds}
    fb = mean(lambda r: r["drop"]["fix_both"])
    misrank = b3["culprit_ranking"][0] != truth_top
    point_miss = all(outside.values())
    res = {"components_mean_pp": {k: round(v * 100, 1) for k, v in comp.items()}, "truth_top": truth_top,
           "b3_top": b3["culprit_ranking"][0], "b3_misrank": misrank, "b3_fix_both_pp": b3_fb * 100,
           "b3_outside_loop_ci": outside, "b3_point_miss_all_seeds": point_miss,
           "loop_pred_pp": pre["loop_plan"]["predicted_drop_pp"], "loop_top": pre["loop_plan"]["culprit_ranking"][0],
           "I_ci_excludes_0": i_ex, "I_ci_excludes_0_same_n": i_ex_same_n, "fix_both_drop_mean_pp": round(fb * 100, 1),
           "acceptance": all(i_ex.values()) and fb >= 0.08 and (misrank or point_miss),
           "kill_B3_ranks_and_inside": (not misrank) and not point_miss,
           "kill_I_includes_0_or_drop_lt_5pp": (not all(i_ex.values())) or fb < 0.05}
    _save("score", res)
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"ref": ref, "g2": g2, "prereg": prereg, "loop": loop, "score": score}[sys.argv[1]]()
