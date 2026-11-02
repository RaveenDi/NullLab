"""Regression replay (read-only, ZERO API calls): re-run the guard on every saved plan in runs_g5, runs_g6, runs_g7 and diff the
verdict against the one stored in that run's log. Also replays the two G7 harness failures through the new G8 repair path.

  .venv/Scripts/python.exe -m eval.regress [--out DIR] [--sandbox N]

Verdicts are replayed under the rule set that was LIVE in that generation (G5: static fidelity; G6: + justification;
G7: + SPLIT-USE-REQUIRED). A flip under the generation's own rules is UNEXPLAINED and fails the target (0 unexplained).
Separately each plan is replayed under TODAY's full rule set; a flip there is listed with its cause (a rule added later),
because that is the intended effect of a new rule, not a regression.
--sandbox N additionally re-executes the first N executed plans and compares the measured inflation (slow; off by default).
Nothing under runs_g5/6/7 is written. Output: <out>/regress.json (default runs_g8/regress.json)."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import factorial_g7 as g7  # noqa: E402

GEN_RULES = {"g5": (), "g6": ("justification",), "g7": ("justification", "split_required")}
ALL_RULES = ("justification", "split_required")
G6_CASES = ("civilwar_apparent", "civilwar_temporal_clean", "esl_selection", "esl_selection_clean")


def case_dir(gen, c):
    if gen == "g5":
        import g4
        return g4.CASES[c]
    return ROOT / "real" / c


def _rule_cause(case, plan, gen):
    """Which later rule flips this plan: run each later rule alone."""
    causes = []
    for rule in ALL_RULES:
        if rule in GEN_RULES[gen]:
            continue
        _, pr, _ = g7.guard(case, plan, rules=(rule,))
        if pr:
            causes.append(rule)
    return causes


def _known_cause(old, new, stored_violations):
    """Documented, deliberate guard change that explains a flip under the generation's own rules."""
    if old == "REJECT" and new == "ACCEPT" and stored_violations and all("FEATURES changed" in x for x in stored_violations):
        return ("agent/fidelity.py was relaxed in G6 so that a verbatim inline of feats' own comprehension is not a FEATURES change "
                "(code comments 'G6: feats inlined verbatim'; the G5 false rejection is documented in docs/EVAL-5.md). "
                "Stored violations are all FEATURES-changed texts.")
    return None


def replay_saved():
    rows, flips_gen, flips_now, flips_known = [], [], [], []
    for gen in ("g5", "g6", "g7"):
        for p in sorted((ROOT / f"runs_{gen}").glob("r[0-9].json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            for c, lr in d.get("loop", {}).items():
                log, final = lr.get("log") or [], lr.get("final_plan")
                verifies = [x for x in log if x.get("phase", "").startswith("Verify")]
                first = (d.get("plan", {}).get(c) or {}).get("plan")
                cdir = case_dir(gen, c)
                for i, v in enumerate(verifies):
                    plan = first if i == 0 else final
                    if not plan:
                        continue
                    _, problems, _ = g7.guard(cdir, plan, rules=GEN_RULES[gen])
                    new, old = "REJECT" if problems else "ACCEPT", v.get("verdict")
                    row = {"gen": gen, "file": p.name, "case": c, "verify_index": i, "stored": old, "replayed": new}
                    if new != old:
                        cause = _known_cause(old, new, v.get("violations") or [])
                        if cause:
                            row["cause"] = cause
                            flips_known.append(row)
                        else:
                            row["unexplained"] = True
                            flips_gen.append(row)
                    # today's full rule set, flip cause
                    _, now_pr, _ = g7.guard(cdir, plan, rules=ALL_RULES)
                    now = "REJECT" if now_pr else "ACCEPT"
                    row["current_rules"] = now
                    if now != new:
                        row["cause"] = "rule added after this generation: " + ", ".join(_rule_cause(cdir, plan, gen) or ["unknown"])
                        flips_now.append(row)
                    rows.append(row)
    return rows, flips_gen, flips_now, flips_known


def sandbox_check(n):
    """Re-execute the first n executed plans; compare mean fix_both drop with the stored stats. Slow."""
    import numpy as np
    from sandbox import factorial_stats
    out, done = [], 0
    for gen in ("g5", "g6", "g7"):
        for p in sorted((ROOT / f"runs_{gen}").glob("r[0-9].json")):
            d = json.loads(p.read_text(encoding="utf-8"))
            for c, lr in d.get("loop", {}).items():
                if done >= n:
                    return out
                if lr.get("status") != "ok" or not lr.get("sources"):
                    continue
                from sandbox import executor
                ex = executor.run_factorial(case_dir(gen, c), lr["sources"], seeds=g7.SEEDS, timeout=1500)
                if ex["status"] != "ok":
                    out.append({"gen": gen, "file": p.name, "case": c, "status": ex["status"]})
                else:
                    st = factorial_stats.all_seeds(ex["result"], n_boot=g7.N_BOOT)
                    new = float(np.mean([st[s]["full"]["drop"]["fix_both"] for s in st]))
                    old = float(np.mean([lr["stats"][s]["full"]["drop"]["fix_both"] for s in lr["stats"]]))
                    out.append({"gen": gen, "file": p.name, "case": c, "stored_inflation": round(old, 4), "replayed_inflation": round(new, 4),
                                "match": abs(new - old) < 1e-6})
                done += 1
    return out


# ---------------- replay of the two G7 harness failures through the G8 repair path ----------------
def replay_g7_failures():
    """LABEL: replay, not a result. The model replies for the repair calls are MOCKS (the real G7 run never made those calls);
    the failing inputs (plan, rejection, sandbox stderr, unparseable reply) are the recorded G7 ones. The sandbox is stubbed
    (no model fit); what is exercised for real: the G8 state machine, the guard on the repaired source, the budget accounting,
    and the repaired split function run on the real case data."""
    from agent import factorial_g8 as g8, llm
    import numpy as np
    import pandas as pd
    out = {"label": "replay, not a result", "cases": {}}
    r3 = json.loads((ROOT / "runs_g7" / "r3.json").read_text(encoding="utf-8"))
    r4 = json.loads((ROOT / "runs_g7" / "r4.json").read_text(encoding="utf-8"))
    r1 = json.loads((ROOT / "runs_g7" / "r1.json").read_text(encoding="utf-8"))
    cdir = g7.CASES[g7.LEAKY]
    crash_plan = r3["loop"][g7.LEAKY]["final_plan"]
    stderr = r3["loop"][g7.LEAKY]["reason"][0]
    fixed = json.loads(json.dumps(crash_plan))
    fixed_src = fixed["edits"]["A"]["steps"]["split_rows"].replace('.to_numpy(kind="stable")', '.to_numpy(), kind="stable"')
    assert fixed_src != crash_plan["edits"]["A"]["steps"]["split_rows"]
    fixed["edits"]["A"]["steps"]["split_rows"] = fixed_src
    traces = [json.loads(l) for l in (ROOT / "runs_g7" / "traces.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    bad_reply = next(t["reply"] for t in traces if t["role"] == "planner_retry" and _unparseable(t["reply"], llm))
    good_plan = r1["loop"][g7.LEAKY]["final_plan"]

    def run(first_plan, replies, execs, name):
        calls = []
        orig = (llm.live_complete_ex, g8._run_executor)
        seq, ex_seq = list(replies), list(execs)

        def fake_llm(system, user, est_usd=0, max_tokens=0, tag="", role="", model=None, temperature=0, **kw):
            calls.append({"tag": tag, "user_has_stderr": "Last lines of stderr" in user, "user_has_rejection": "It was REJECTED" in user,
                          "user_has_bad_reply": "YOUR PREVIOUS REPLY WAS NOT USABLE" in user})
            return seq.pop(0), {"total_tokens": 0}

        def fake_exec(case_dir_, patches):
            r = ex_seq.pop(0)
            if r == "crash":
                return {"status": "error", "stderr": stderr}
            return {"status": "ok", "result": {"metric": "pr_auc"}}
        import sandbox.factorial_stats as fs
        from agent import fidelity
        o_stats, o_rt = fs.all_seeds, fidelity.check_runtime
        llm.live_complete_ex, g8._run_executor = fake_llm, fake_exec
        fs.all_seeds = lambda raw, n_boot=0: {"42": {"full": {"drop": {"fix_both": 0.3}, "drop_ci": {"fix_both": [0.2, 0.4]}, "acc": {"orig": 0.4, "fix_both": 0.1}}}}
        fidelity.check_runtime = lambda *a, **k: []
        import os
        o_env = os.environ.get("NULLLAB_G8_OUT")
        try:
            g8_cases = g8.pipeline(cdir, f"replay-{name}", model="mock-model", temperature=0)
            # g8.pipeline's first call is the plan call; we inject the first plan as the first reply
        finally:
            llm.live_complete_ex, g8._run_executor = orig[0], orig[1]
            fs.all_seeds, fidelity.check_runtime = o_stats, o_rt
            if o_env is None:
                os.environ.pop("NULLLAB_G8_OUT", None)
        return g8_cases, calls

    import tempfile, os
    tmp = tempfile.mkdtemp(prefix="g8_regress_")
    os.environ["NULLLAB_G8_OUT"] = tmp  # pipeline writes prereg_log only; never into runs_g5/6/7
    first = r3["plan"][g7.LEAKY]["plan"]
    # r3: plan -> SPLIT-USE rejection -> (recorded) crashing retry plan -> sandbox crash -> crash repair -> ok
    rec, calls = run(first, [json.dumps(first), json.dumps(crash_plan), json.dumps(fixed)], ["crash", "ok"], "r3")
    ns = {"np": np, "pd": pd}
    exec(fixed_src, ns)  # the repaired split function really runs on the real data
    df = pd.read_csv(cdir / "data.csv")
    tr, te = ns["split_rows"](df, 42)
    out["cases"]["r3_crash"] = {"g7_outcome": "INCONCLUSIVE (retry crashed: to_numpy(kind=...) TypeError)", "g8_status": rec["status"],
                                "recovered_past_failure": rec["status"] == "ok", "repairs_used": rec.get("repairs_used"), "planner_side_calls": len(rec["calls"]),
                                "calls_seen": calls, "stderr_fed_back": any(c["user_has_stderr"] for c in calls),
                                "repaired_split_runs_on_real_data": {"train_rows": int(len(tr)), "test_rows": int(len(te)),
                                                                      "test_epochs_all_later": bool(df["epoch"].to_numpy()[tr].max() <= df["epoch"].to_numpy()[te].min())}}
    # r4: plan -> rejection -> retry reply NOT JSON -> json repair -> ok
    first4 = r4["plan"][g7.LEAKY]["plan"]
    rec, calls = run(first4, [json.dumps(first4), bad_reply, json.dumps(good_plan)], ["ok"], "r4")
    out["cases"]["r4_bad_json"] = {"g7_outcome": "INCONCLUSIVE (retry reply not parseable JSON, no second retry)", "g8_status": rec["status"],
                                   "recovered_past_failure": rec["status"] == "ok", "repairs_used": rec.get("repairs_used"), "planner_side_calls": len(rec["calls"]),
                                   "calls_seen": calls, "bad_reply_fed_back": any(c["user_has_bad_reply"] for c in calls)}
    # and: a third failure of the same kind is NOT hidden
    rec, _ = run(first4, [json.dumps(first4), bad_reply, bad_reply], [], "r4b")
    out["cases"]["bad_json_twice"] = {"g8_label": g8.outcome_label(rec), "note": "second bad reply -> labelled harness failure, never a verdict"}
    return out


def _unparseable(text, llm):
    try:
        llm.parse_json(text)
        return False
    except Exception:  # noqa: BLE001
        return True


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs_g8"))
    ap.add_argument("--sandbox", type=int, default=0)
    a = ap.parse_args(argv)
    rows, flips_gen, flips_now, flips_known = replay_saved()
    res = {"label": "OFFLINE regression replay, zero API calls, read-only on runs_g5/g6/g7", "n_verdicts_replayed": len(rows),
           "unexplained_flips_under_own_generation_rules": flips_gen,
           "explained_flips_under_own_generation_rules": flips_known, "explained_flips_under_current_rules": flips_now,
           "target_met": not flips_gen}
    if a.sandbox:
        res["sandbox_replay"] = sandbox_check(a.sandbox)
    res["g7_failure_replay"] = replay_g7_failures()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "regress.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(f"replayed {len(rows)} stored verdicts: unexplained flips = {len(flips_gen)} (target 0)")
    for f in flips_gen:
        print("  UNEXPLAINED", f)
    for f in flips_known:
        print("  explained flip (own rules):", f["gen"], f["file"], f["case"], f["stored"], "->", f["replayed"], "|", f["cause"][:90])
    for f in flips_now:
        print("  flip under current rules:", f["gen"], f["file"], f["case"], f["stored"], "->", f["current_rules"], "|", f["cause"])
    for k, v in res["g7_failure_replay"]["cases"].items():
        print(f"  [replay, not a result] {k}: recovered={v.get("recovered_past_failure", v.get("g8_label"))} calls={v.get('planner_side_calls')} repairs={v.get('repairs_used')}")


if __name__ == "__main__":
    main()
