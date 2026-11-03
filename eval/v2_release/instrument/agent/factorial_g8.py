"""G8: loop hardening re-run of the G7 disguised pair. Extends agent/factorial_g7.py (NOT edited): same cases, guards, rules,
planner prompt, measurement and acceptance numbers; NEW is the repair path and the honest outcome labels.

Repair budgets (per case, hard cap CASE_CALL_CAP planner-side live calls = 1 plan call + at most 3 repair calls):
  guard    one retry after a static-guard / SPLIT-USE-REQUIRED / runtime-fidelity rejection (rejection text fed back)
  crash    one retry after a sandbox crash or timeout (last lines of stderr fed back)
  bad_json one repair after a reply that is not parseable / schema-valid JSON (the bad reply + the parse error fed back);
           it applies to ANY reply: the first plan or a guard/crash retry reply.
A failure whose budget is already spent ends the case as  INCONCLUSIVE (harness failure: crash|bad_json|guard|call_cap|budget).
It is never silently a model verdict: it is counted in the denominator, listed, and reported apart from
'no effect (interval spans 0)'.
Native structured output (response_format json_schema) is documented at dev.meta.ai/docs/structured-output but has NOT been
tested live here (UNVERIFIED), so G8 keeps the prompt-based JSON (USE_NATIVE_SCHEMA = False).

Driver:  .venv/Scripts/python.exe -m agent.factorial_g8 [--model M] [--out DIR] [--replay TRACES] <stage> [args]
Stages: project (print projected spend, no call) | freeze (log sha256 of code+rules) | run <r>... | score | usage"""
import argparse
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import factorial_g5, factorial_g7 as g7, llm  # noqa: E402
from agent.factorial import agent_view  # noqa: E402

CASES, LEAKY, CLEAN = g7.CASES, g7.LEAKY, g7.CLEAN
SEEDS, N_BOOT, N_REPEATS, TEMPERATURE = g7.SEEDS, g7.N_BOOT, g7.N_REPEATS, g7.TEMPERATURE
PUBLISHED_INFLATION, TOL = g7.PUBLISHED_INFLATION, g7.TOL
SYSTEM, B3_SYSTEM = g7.SYSTEM, g7.B3_SYSTEM
DEFAULT_MODEL = "muse-spark-1.3-contributor"
USE_NATIVE_SCHEMA = False
REPAIR_KINDS = ("guard", "crash", "bad_json")
CASE_CALL_CAP = 4          # 1 plan call + one repair per kind (3); enforced before every planner-side call
EST = {"b3": 0.08, "plan": 0.10, "repair": 0.10}
CEILING_USD = float(os.environ.get("NULLLAB_G8_CEILING", "5.00"))
STDERR_LINES, STDERR_CHARS, BADREPLY_CHARS = 25, 2000, 6000
_IO = g7._IO


class HarnessFailure(RuntimeError):
    def __init__(self, kind, detail=""):
        super().__init__(f"{kind}: {detail}"[:600])
        self.kind, self.detail = kind, detail


def label(status, kind=None):
    return f"INCONCLUSIVE (harness failure: {kind})" if status == "INCONCLUSIVE" else status


# ---------------- own output dir / prereg log / accounting (never touches runs_g7) ----------------
def out_dir():
    d = Path(os.environ.get("NULLLAB_G8_OUT") or ROOT / "runs_g8")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save(name, obj):
    with _IO:
        (out_dir() / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8")


def _load(name, default=None):
    p = out_dir() / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _prereg(kind, obj, case=None, repeat=None):
    rec = {"kind": kind, "case": case, "repeat": repeat, "model": llm.model_for(), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "sha256": hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()}
    with _IO, (out_dir() / "prereg_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def my_spent():
    p = llm.g8_log()
    return sum(json.loads(l).get("est_usd", 0) for l in p.read_text().splitlines() if l.strip()) if p.exists() else 0.0


def projected(n_cases=2 * N_REPEATS):
    base = n_cases * (EST["b3"] + EST["plan"])
    worst = base + n_cases * len(REPAIR_KINDS) * EST["repair"]
    return {"cases": n_cases, "expected_floor_usd": round(base, 2), "worst_case_usd": round(worst, 2), "ceiling_usd": CEILING_USD,
            "max_planner_calls_per_case": CASE_CALL_CAP, "max_live_calls_total": n_cases * (1 + CASE_CALL_CAP)}


def print_projection(n_cases):
    pj = projected(n_cases)
    print(f"PROJECTED SPEND (estimates, not billing): floor ${pj['expected_floor_usd']:.2f} (no repairs), worst case ${pj['worst_case_usd']:.2f} "
          f"({pj['cases']} cases, <= {pj['max_planner_calls_per_case']} planner calls + 1 B3 call each; ceiling ${pj['ceiling_usd']:.2f}; "
          f"already spent est ${my_spent():.2f})", flush=True)
    return pj


# ---------------- per-case call accounting ----------------
class CaseBudget:
    """Counts planner-side live calls and repair use for ONE case. Every call goes through call()."""

    def __init__(self, cap=CASE_CALL_CAP):
        self.cap, self.used, self.calls = cap, set(), []

    def take(self, kind):
        """Spend the single repair of `kind`; raises HarnessFailure(kind) if it was already spent."""
        if kind in self.used:
            raise HarnessFailure(kind, "its one repair attempt was already used")
        self.used.add(kind)

    def call(self, kind, system, msg, tag, model, temperature):
        if len(self.calls) >= self.cap:
            raise HarnessFailure("call_cap", f"{self.cap} planner-side calls already made for this case (next would be {kind})")
        if not llm.replaying() and my_spent() + EST["repair"] > CEILING_USD:
            raise HarnessFailure("budget", f"spend ceiling ${CEILING_USD:.2f} reached")
        kw = {}
        if USE_NATIVE_SCHEMA:  # off: UNVERIFIED
            kw["response_format"] = {"type": "json_schema", "json_schema": {"name": "plan", "schema": {"type": "object"}}}
        est = EST["plan"] if kind == "plan" else EST["repair"]
        raw, usage = llm.live_complete_ex(system, msg, est_usd=est, tag=tag, role="planner" if kind == "plan" else "planner_retry",
                                          model=model, temperature=TEMPERATURE if temperature is None else temperature, **kw)
        self.calls.append({"kind": kind, "tag": tag, "est_usd": est, "usage": usage or {},
                           "real_total_tokens": (usage or {}).get("total_tokens"), "reply_len": len(raw)})
        return raw


def _parse_validate(raw):
    try:
        p = llm.parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return None, [f"reply is not parseable JSON: {e!r}"[:240]]
    return p, g7.validate_plan(p)


def _json_repair_msg(base_msg, raw, problems):
    return (base_msg + "\n\nYOUR PREVIOUS REPLY WAS NOT USABLE:\n- " + "\n- ".join(problems) +
            "\n\nYOUR PREVIOUS REPLY (may be cut off):\n" + raw[:BADREPLY_CHARS] +
            "\n\nReturn ONLY the complete corrected JSON object (no markdown, no commentary) with the required schema.")


def _get_plan(bud, kind, system, msg, tag, model, temperature):
    """One planner-side call; an unusable reply gets the single bad_json repair; returns (plan, raw)."""
    raw = bud.call(kind, system, msg, tag, model, temperature)
    p, bad = _parse_validate(raw)
    if bad:
        bud.take("bad_json")
        raw = bud.call("bad_json", system, _json_repair_msg(msg, raw, bad), tag + "_json_repair", model, temperature)
        p, bad = _parse_validate(raw)
        if bad:
            raise HarnessFailure("bad_json", "; ".join(bad))
    return p, raw


def _fb_msg(case_dir, rid, prev, header, items, tail_note):
    return (factorial_g5.user_msg(case_dir, rid) + "\n\nYOUR PREVIOUS JSON:\n" +
            json.dumps({k: (prev or {}).get(k) for k in ("A", "A_code_line", "B", "B_code_line", "edits", "predicted_drop_pp",
                                                         "culprit_ranking", "reason")}) +
            f"\n\n{header}\n- " + "\n- ".join(items) + f"\n{tail_note}")


def stderr_tail(text):
    lines = (text or "").strip().splitlines()[-STDERR_LINES:]
    return "\n".join(lines)[-STDERR_CHARS:]


# ---------------- sandbox (indirection so tests/replays can stub it) ----------------
def _run_executor(case_dir, patches):
    from sandbox import executor
    return executor.run_factorial(Path(case_dir), patches, seeds=SEEDS, timeout=1500)


def _execute(case_dir, cfgs):
    """Returns ('ok', raw, runtime_violations) | ('crash', stderr_tail, [])."""
    from agent import fidelity
    patches = {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}
    ex = _run_executor(case_dir, patches)
    if ex["status"] != "ok":
        tail = stderr_tail(ex.get("stderr", "")) or f"(no stderr; status={ex['status']}, timeout_s={ex.get('timeout_s')})"
        return "crash", f"EXECUTION {ex['status']}:\n{tail}", []
    v = fidelity.check_runtime(ex["result"], {k: cfgs[k]["kinds"] for k in ("fix_A", "fix_B", "fix_both")})
    return "ok", ex["result"], v


# ---------------- the hardened pipeline: plan -> verify -> act, three separate repair budgets ----------------
def pipeline(case_dir, rid, model=None, temperature=None, rules=("justification", "split_required"), system=SYSTEM):
    """Returns a case record. status 'ok' (stats present) or 'INCONCLUSIVE' with harness_failure in
    crash|bad_json|guard|call_cap|budget. Never raises on a model/harness failure."""
    from sandbox import factorial_stats
    model = model or llm.model_for("planner")
    bud, log, rec = CaseBudget(), [], {"rid": rid}
    base = factorial_g5.user_msg(case_dir, rid)
    cur = None

    def finish(kind, detail, plan_=None):
        rec.update({"status": "INCONCLUSIVE", "harness_failure": kind, "label": label("INCONCLUSIVE", kind),
                    "reason": [str(detail)[:900]], "final_plan": plan_ or cur, "log": log, "calls": bud.calls,
                    "retries": len(bud.calls) - 1 if bud.calls else 0})
        return rec

    try:
        cur, raw = _get_plan(bud, "plan", system, base, "g8_planner", model, temperature)
        cur["mode"], cur["prereg_sha256"] = llm.mode_label("planner", model), factorial_g5.prereg_hash(cur)
        log.append({"phase": "Plan", "prereg_sha256": cur["prereg_sha256"], "calls": len(bud.calls)})
        rec["first_plan_prereg"] = _prereg("loop_planner", {k: cur.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")},
                                           Path(case_dir).name, rid)["sha256"]
        while True:
            cfgs, problems, reports = g7.guard(case_dir, cur, rules)
            log.append({"phase": "Verify", "verdict": "REJECT" if problems else "ACCEPT", "violations": problems[:8]})
            crashed = None
            if not problems:
                state, res, rtv = _execute(case_dir, cfgs)
                log.append({"phase": "Act", "status": "ok" if state == "ok" else "crash", "runtime_violations": rtv[:8]})
                if state == "crash":
                    crashed = res
                elif rtv:
                    problems = rtv
                else:
                    raw_result = res
                    break
            if crashed is not None:
                bud.take("crash")
                msg = _fb_msg(case_dir, rid, cur, "YOUR PLAN PASSED THE STATIC GUARD BUT CRASHED IN THE SANDBOX. Last lines of stderr:",
                              [crashed], "Fix ONLY the cause of the crash (for example an invalid argument or API misuse) and keep the rest of "
                                         "the plan. Return the corrected complete JSON with the same schema.")
                kind = "crash"
            else:
                bud.take("guard")
                msg = _fb_msg(case_dir, rid, cur, "It was REJECTED:", problems[:8],
                              "Return the corrected complete JSON with the same schema. Change only what the rejection requires.")
                kind = "guard"
            cur, raw = _get_plan(bud, kind, system, msg, f"g8_planner_{kind}_repair", model, temperature)
            cur["mode"], cur["prereg_sha256"] = llm.mode_label("planner", model, f"{kind} repair"), factorial_g5.prereg_hash(cur)
            _prereg(f"loop_planner_{kind}_repair", {k: cur.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")},
                    Path(case_dir).name, rid)
            log.append({"phase": f"Recover ({kind} repair)", "calls": len(bud.calls)})
    except HarnessFailure as e:
        return finish(e.kind, e.detail)
    except (llm.LiveNotAllowed, OSError) as e:  # API refusal / empty content / network: harness, not a model verdict
        return finish("api_error", repr(e))
    stats = factorial_stats.all_seeds(raw_result, n_boot=N_BOOT)
    from agent import fidelity
    rec.update({"status": "ok", "metric": raw_result.get("metric", "accuracy"), "stats": stats, "final_plan": cur, "log": log,
                "calls": bud.calls, "retries": len(bud.calls) - 1, "repairs_used": sorted(bud.used),
                "fidelity": {cfg: fidelity.verdict_line(cfgs[cfg], reports[cfg]) for cfg in reports},
                "sources": {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}})
    return rec


# ---------------- scoring: harness failures kept apart from model verdicts ----------------
def sign_of(rec):
    import g4
    if rec.get("status") != "ok":
        return "INCONCLUSIVE"
    return g4.case_sign(rec["stats"])[0]


def outcome_label(rec):
    if rec.get("status") != "ok":
        return rec.get("label") or label("INCONCLUSIVE", rec.get("harness_failure") or "unknown")
    s = sign_of(rec)
    return {"+": "inflation found (interval above 0)", "-": "reverse effect (interval below 0)", "0": "no effect (interval spans 0)"}.get(s, "mixed across seeds")


def score_cases(records):
    """records = {'civilwar_disguised': {'r1': rec,...}, 'civilwar_disguised_clean': {...}}. Pure function.
    Acceptance clauses are IDENTICAL to G7. Harness failures stay in the denominator and are listed."""
    import numpy as np
    L, C = records.get(LEAKY, {}), records.get(CLEAN, {})
    rows, harness = {LEAKY: {}, CLEAN: {}}, []
    for c, d in ((LEAKY, L), (CLEAN, C)):
        for r, rec in sorted(d.items()):
            row = {"label": outcome_label(rec), "sign": sign_of(rec), "calls": len(rec.get("calls", [])), "retries": rec.get("retries")}
            if rec.get("status") == "ok":
                infl = [rec["stats"][s]["full"]["drop"]["fix_both"] for s in sorted(rec["stats"])]
                row["inflation_mean"] = round(float(np.mean(infl)), 3)
                row["magnitude_ok"] = c == LEAKY and abs(row["inflation_mean"] - PUBLISHED_INFLATION) <= TOL
            else:
                harness.append({"case": c, "repeat": r, "failure": rec.get("harness_failure"), "reason": (rec.get("reason") or [""])[0][:200]})
            rows[c][r] = row
    acc = {"n_leaky": len(L), "n_clean": len(C),
           "a_direction_right": sum(x["sign"] == "+" for x in rows[LEAKY].values()),
           "b_clean_false_alarms": sum(x["sign"] == "+" for x in rows[CLEAN].values()),
           "c_magnitude_within_0.15": sum(bool(x.get("magnitude_ok")) for x in rows[LEAKY].values()),
           "no_effect_leaky": sum(x["sign"] == "0" for x in rows[LEAKY].values()),
           "no_effect_clean": sum(x["sign"] == "0" for x in rows[CLEAN].values()),
           "harness_inconclusive": len(harness), "harness_inconclusive_target": 0,
           "denominator_leaky": N_REPEATS, "denominator_clean": N_REPEATS}
    acc["PASS"] = (len(L) == N_REPEATS and len(C) == N_REPEATS and acc["a_direction_right"] >= 4 and acc["b_clean_false_alarms"] == 0
                   and acc["c_magnitude_within_0.15"] >= 3)
    acc["harness_target_met"] = acc["harness_inconclusive"] == 0
    return {"acceptance": acc, "harness_failures": harness, "cases": rows}


def score(args=None):
    recs = {c: {} for c in CASES}
    for r in range(1, N_REPEATS + 1):
        d = _load(f"r{r}")
        for c in CASES:
            if d and c in d.get("loop", {}):
                recs[c][f"r{r}"] = d["loop"][c]
    out = score_cases(recs)
    out["usage"] = usage_summary()
    _save("score", out)
    print(json.dumps(out["acceptance"], indent=1))
    for h in out["harness_failures"]:
        print("HARNESS FAILURE", h)


def usage_summary():
    """Real usage tokens next to the estimate, from the saved case records (and the usage log if present)."""
    est = tok = n = 0
    for r in range(1, N_REPEATS + 1):
        d = _load(f"r{r}") or {}
        for rec in d.get("loop", {}).values():
            for cl in rec.get("calls", []):
                est += cl["est_usd"]
                tok += cl.get("real_total_tokens") or 0
                n += 1
    return {"planner_side_calls": n, "estimated_usd": round(est, 2), "real_total_tokens": tok}


# ---------------- stages ----------------
def project(args=None):
    print_projection(2 * N_REPEATS if not args else 2 * int(args[0]))


def freeze(args=None):
    files = ("agent/factorial_g8.py", "agent/factorial_g7.py", "agent/llm.py", "agent/fidelity.py", "agent/factorial_g5.py",
             "agent/factorial_g6.py", "eval/build_g7.py", "eval/g7_truth.json", "sandbox/factorial_stats.py", "sandbox/run_factorial.py",
             "sandbox/executor.py")
    _prereg("g8_source_hashes", {x: hashlib.sha256((ROOT / x).read_bytes()).hexdigest() for x in files})
    _prereg("g8_prompts", {"planner_system": SYSTEM, "b3_system": B3_SYSTEM})
    _prereg("g8_rules", {"forecast_words": g7.FORECAST_WORDS, "repair_kinds": REPAIR_KINDS, "case_call_cap": CASE_CALL_CAP,
                         "temperature": TEMPERATURE, "n_repeats": N_REPEATS})
    for c, d in CASES.items():
        import g4
        _prereg("agent_view_frozen", g4._hashes(d), c)
    print("frozen; see", out_dir() / "prereg_log.jsonl")


def run(args):
    reps = [int(a) for a in args]
    model = llm.model_for()
    res = {r: _load(f"r{r}", {"repeat": f"g8-r{r}", "model": model, "temperature": TEMPERATURE, "b3": {}, "loop": {}}) for r in reps}
    todo = [(r, c) for r in reps for c in CASES if c not in res[r]["loop"]]  # a recorded harness failure is NOT re-rolled
    pj = print_projection(len(todo))
    if not llm.replaying() and my_spent() + pj["worst_case_usd"] > CEILING_USD:
        print(f"STOP: est spent ${my_spent():.2f} + worst case ${pj['worst_case_usd']:.2f} passes ceiling ${CEILING_USD:.2f}", flush=True)
        return

    def one(r, c):
        t0 = time.time()
        if c not in res[r]["b3"] or "error" in res[r]["b3"][c]:
            try:
                raw, usage = llm.live_complete_ex(B3_SYSTEM, agent_view(CASES[c]) + f"\n\n[repeat id: g8-r{r}]", est_usd=EST["b3"], tag="g8_b3",
                                                  role="b3", model=llm.model_for("b3"), temperature=TEMPERATURE)
                res[r]["b3"][c] = {"ans": llm.parse_json(raw), "raw": raw, "usage": usage}
            except Exception as e:  # noqa: BLE001
                res[r]["b3"][c] = {"error": repr(e)[:400]}
        lr = pipeline(CASES[c], f"g8-r{r}", model=model)
        print(f"g8-r{r} {c:26s} {outcome_label(lr)} calls={len(lr.get('calls', []))} {time.time() - t0:.0f}s", flush=True)
        return lr

    with ThreadPoolExecutor(3) as ex:
        futs = {k: ex.submit(one, *k) for k in todo}
        for (r, c), f in futs.items():
            try:
                res[r]["loop"][c] = f.result()
            except Exception as e:  # noqa: BLE001  (unexpected bug, still recorded, never a silent verdict)
                res[r]["loop"][c] = {"status": "INCONCLUSIVE", "harness_failure": "internal_error", "label": label("INCONCLUSIVE", "internal_error"),
                                     "reason": [repr(e)[:400]], "calls": [], "retries": 0}
            _save(f"r{r}", res[r])


STAGES = {"project": project, "freeze": freeze, "run": run, "score": score, "usage": lambda a=None: print(json.dumps(usage_summary()))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--out")
    ap.add_argument("--replay")
    ap.add_argument("stage")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    if a.replay and not a.out:
        raise SystemExit("--replay requires --out DIR")
    os.environ["NULLLAB_PHASE"] = "g8"
    os.environ["NULLLAB_MODEL"] = a.model or os.environ.get("NULLLAB_MODEL") or DEFAULT_MODEL
    if a.out:
        os.environ["NULLLAB_G8_OUT"] = a.out
    if a.replay:
        print("replay: loaded", llm.set_replay(a.replay), "recorded replies; no API call will be made")
    STAGES[a.stage](a.args)


if __name__ == "__main__":
    main()
