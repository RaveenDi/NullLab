"""Hybrid audit: RULES FIRST, SPARK ONLY WHEN NEEDED (EVAL-8 finding turned into a product path).

    python -m agent.hybrid <case_dir> [--live] [--referee] [--out DIR] [--report FILE] [--fresh]

Routing (every step records which rule or model produced it):
  1. run the fixed rule library (baselines/rulefix.py, no model) -> which rules fire (label-free).
  2. a rule fires with an applicable remedy -> measure the rule fix in the local sandbox ($0) -> cheap consistency check:
        measured sign '+'  (controlled score is lower, 95% interval above 0)  -> verdict from  "rules (no model)".
        anything else (sign 0/-/mixed, or the measurement failed)             -> rules and measurement DISAGREE -> ask the model.
  3. no rule fires, or only "detected, not applied" -> ask the model (Spark planner loop, plan -> guard -> sandbox -> verdict).
  4. optional Wonder referee (--referee, OFF by default, veto only, at most MAX_REFEREE_CALLS calls): may downgrade an
     INFLATED verdict to DISPUTED. It can never create an inflation finding.
Offline is the default. Without --live the model path serves only (a) a recorded run of the same case in this repository
(tagged "Spark (recorded run, no new call)") or (b) llm.set_replay() traces; otherwise the verdict is NEEDS_MODEL and nothing is
spent. --live is required to make a real call and still passes through agent.llm's spend gate and call caps.

Cost ledger: calls, tokens and USD per model. USD is the per-call ESTIMATE used by this repository's own spend gate
(EST_USD_PER_CALL), not a billed amount; tokens are estimated at 4 characters per token. Both are labelled as estimates."""
import argparse
import contextlib
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from agent import audit  # noqa: E402
from baselines import rulefix  # noqa: E402

TAG_RULES = "rules (no model)"
TAG_SPARK = "Spark"
TAG_SPARK_REC = "Spark (recorded run, no new call)"
TAG_WONDER = "Wonder"
TAG_SANDBOX = "sandbox (no model)"
EST_USD_PER_CALL = {"planner": 0.10, "retry": 0.10, "referee": 0.10}  # the estimates agent/factorial_g5.py passes to the spend gate
MAX_SPARK_CALLS = 3          # planner + at most one retry (+1 spare); a hard cap enforced here, on top of agent.llm's caps
MAX_REFEREE_CALLS = 10
SEEDS = (42, 43, 44)
PRICING_NOTE = ("USD is an ESTIMATE (the per-call figure this repo's spend gate uses), not a billed amount; real Meta Model API "
                "pricing is UNVERIFIED here. Tokens are estimated at 4 characters per token.")


class NeedsModel(RuntimeError):
    """The model path is required but not allowed (offline, no recorded run, no replay)."""


class BudgetExceeded(RuntimeError):
    pass


# ---------------- cost ledger ----------------
class Ledger:
    def __init__(self, max_spark=MAX_SPARK_CALLS, max_referee=MAX_REFEREE_CALLS):
        self.calls, self.max_spark, self.max_referee = [], max_spark, max_referee

    def n(self, role):
        return sum(1 for c in self.calls if c["role"] == role and not c["replayed"])

    def check(self, role):
        cap = self.max_referee if role == "referee" else self.max_spark
        if self.n(role) >= cap:
            raise BudgetExceeded(f"{role} call cap ({cap}) reached")

    def add(self, role, model, tag, tin, tout, usd, replayed=False):
        self.calls.append({"role": role, "model": model, "tag": tag, "tokens_in_est": int(tin), "tokens_out_est": int(tout),
                           "est_usd": 0.0 if replayed else round(float(usd), 4), "replayed": bool(replayed)})

    def totals(self):
        live = [c for c in self.calls if not c["replayed"]]
        by = {}
        for c in self.calls:
            b = by.setdefault(c["model"], {"calls": 0, "replayed_calls": 0, "tokens_in_est": 0, "tokens_out_est": 0, "est_usd": 0.0})
            b["replayed_calls" if c["replayed"] else "calls"] += 1
            b["tokens_in_est"] += c["tokens_in_est"]
            b["tokens_out_est"] += c["tokens_out_est"]
            b["est_usd"] = round(b["est_usd"] + c["est_usd"], 4)
        return {"calls": len(live), "replayed_calls": len(self.calls) - len(live),
                "est_usd": round(sum(c["est_usd"] for c in live), 4),
                "tokens_in_est": sum(c["tokens_in_est"] for c in self.calls), "tokens_out_est": sum(c["tokens_out_est"] for c in self.calls),
                "by_model": by, "note": PRICING_NOTE, "detail": self.calls}


@contextlib.contextmanager
def recording_llm(ledger, role, live):
    """Route agent.llm.live_complete through the ledger: enforces the call cap BEFORE the call, refuses a real call unless
    `live`, and books the call (replayed calls cost 0). Restores the original function on exit."""
    from agent import llm
    orig = llm.live_complete

    def proxy(system, user, est_usd=0.02, max_tokens=0, tag="", role="", model=None, temperature=0, **kw):  # noqa: A002
        r_ = role_name
        replay = llm.replaying()
        if not replay and not live:
            raise NeedsModel("a live model call is needed but --live was not given")
        ledger.check(r_)
        mdl = model or llm.model_for(role or "")
        reply = orig(system, user, est_usd=est_usd, max_tokens=max_tokens or llm.MIN_MAX_TOKENS, tag=tag, role=role, model=model, temperature=temperature, **kw)
        ledger.add(r_, mdl, tag, (len(system) + len(user)) / 4, len(reply or "") / 4, est_usd, replayed=replay)
        return reply

    role_name = role
    llm.live_complete = proxy
    try:
        yield
    finally:
        llm.live_complete = orig


# ---------------- helpers ----------------
def _under_root(p, root=ROOT):
    try:
        return Path(p).resolve().is_relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def summarize(rec):
    """Uniform numbers from a measured record (rule-baseline or loop). None if the record has no usable stats."""
    if not rec or rec.get("status") != "ok" or not rec.get("stats"):
        return None
    m = audit.measurement(rec)
    rows = m["rows"]
    unit_pp = m["metric"] == "accuracy"
    k = 100.0 if unit_pp else 1.0
    return {"metric": m["metric"], "unit": "pp" if unit_pp else m["metric"], "sign": m["sign"], "per_seed_sign": m["per_seed_sign"],
            "claimed": round(m["mean_claimed"], 4), "controlled": round(m["mean_controlled"], 4),
            "inflation": round(m["mean_drop"] * k, 3), "inflation_raw": m["mean_drop"],
            "ci_per_seed": {str(r["seed"]): [round(r["ci"][0] * k, 3), round(r["ci"][1] * k, 3)] for r in rows},
            "seeds": [str(r["seed"]) for r in rows], "n_controlled": [r["n_controlled"] for r in rows]}


def default_measure(case_dir, fresh=False, root=ROOT):
    """Measure the rule fix. Returns (record, how). A stored runs_rulefix record is reused ONLY for a case that lives in this
    repository AND whose generated patch hash equals the stored one (the data hash is not stored: UNVERIFIED if data.csv changed)."""
    case_dir = Path(case_dir)
    built = rulefix.build_configs(case_dir)
    stored = Path(root) / "runs_rulefix" / f"{case_dir.name}.json"
    if not fresh and stored.exists() and _under_root(case_dir, root):
        try:
            rec = json.loads(stored.read_text(encoding="utf-8"))
            same = all(rec["configs"][c]["src_sha256"] == hashlib.sha256(built["configs"][c]["src"].encode()).hexdigest()
                       for c in ("fix_A", "fix_B", "fix_both"))
            if same and rec.get("status") == "ok":
                return rec, "stored measurement (runs_rulefix, patch hash identical)"
        except (OSError, ValueError, KeyError):
            pass
    from agent import rules_measure
    return rules_measure.run_case(case_dir), "fresh sandbox run (local, no model)"


def find_recorded_spark(case_dir, root=ROOT):
    """A finished loop record of this case in runs_g*/ (newest dir first). Only for cases inside this repository."""
    if not _under_root(case_dir, root):
        return None
    name = Path(case_dir).name
    for d in sorted(Path(root).glob("runs_g*"), reverse=True):
        for f in sorted(d.glob("r[0-9]*.json")):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            rec = (j.get("loop") or {}).get(name) if isinstance(j, dict) else None
            if isinstance(rec, dict) and rec.get("status") == "ok" and rec.get("stats") and rec.get("sources"):
                return rec, f.relative_to(root).as_posix()
    return None


# ---------------- the Spark loop (existing planner + guard + sandbox), every piece injectable ----------------
def spark_loop(case_dir, ledger, live, plan_fn=None, retry_fn=None, execute_fn=None, repeat_id="hybrid"):
    """Plan -> guard (agent/fidelity) -> sandbox -> stats; one retry on a guard/execution failure, as in g5.loop_case.
    Returns a loop-shaped record. plan_fn(case_dir, rid)->(plan, raw); retry_fn(case_dir, rid, prev, problems)->(plan, raw);
    execute_fn(case_dir, patches)->raw result dict or raises. Defaults are the real planner and sandbox."""
    from agent import factorial_g5, fidelity, llm
    case_dir = Path(case_dir)
    plan_fn = plan_fn or factorial_g5.plan
    retry_fn = retry_fn or factorial_g5.retry
    if execute_fn is None:
        def execute_fn(cd, patches):
            from sandbox import executor
            ex = executor.run_factorial(cd, patches, seeds=SEEDS, timeout=1500)
            if ex["status"] != "ok":
                raise RuntimeError(f"EXECUTION {ex['status']}: {ex.get('stderr', '')[-600:]}")
            return ex["result"]
    from sandbox import factorial_stats
    src = (case_dir / "train.py").read_text(encoding="utf-8")
    log, rec, retried = [], {"retries": 0}, False
    with recording_llm(ledger, "planner", live):
        cur, _raw = plan_fn(case_dir, repeat_id)
        log.append({"phase": "Plan", "by": TAG_SPARK, "prereg_sha256": cur.get("prereg_sha256")})
        while True:
            cfgs = fidelity.build_configs(src, cur.get("edits"))
            problems, reports = [], {}
            for cfg, info in cfgs.items():
                v = list(info["violations"])
                if not v:
                    sv, rep = fidelity.check_static(src, info["src"], info["kinds"], info["declared"])
                    v += sv
                    reports[cfg] = rep
                problems += [f"{cfg}: {x}" for x in v]
            log.append({"phase": "Verify (static fidelity guard)", "by": "code (no model)", "verdict": "REJECT" if problems else "ACCEPT",
                        "violations": problems[:6]})
            raw = None
            if not problems:
                try:
                    raw = execute_fn(case_dir, {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")})
                    log.append({"phase": "Act (sandbox)", "by": TAG_SANDBOX, "status": "ok"})
                except Exception as e:  # noqa: BLE001
                    problems = [str(e)[:600]]
                    log.append({"phase": "Act (sandbox)", "by": TAG_SANDBOX, "status": "error", "error": problems[0]})
            if not problems:
                break
            if retried:
                rec.update({"status": "INCONCLUSIVE", "reason": problems[:6], "log": log, "final_plan": cur})
                return rec
            try:
                cur, _raw = retry_fn(case_dir, repeat_id, cur, problems[:6])
            except (BudgetExceeded, NeedsModel, llm.LiveNotAllowed) as e:
                rec.update({"status": "INCONCLUSIVE", "reason": [f"retry not made: {e}"] + problems[:6], "log": log, "final_plan": cur})
                return rec
            retried, rec["retries"] = True, 1
            log.append({"phase": "Recover (one retry with the violation text)", "by": TAG_SPARK})
    rec.update({"status": "ok", "stats": factorial_stats.all_seeds(raw, n_boot=1000), "metric": raw.get("metric", "accuracy"),
                "final_plan": cur, "log": log,
                "fidelity": {c: fidelity.verdict_line(cfgs[c], reports[c]) for c in reports},
                "sources": {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}})
    return rec


# ---------------- Wonder referee (veto only) ----------------
REFEREE_SYSTEM = ("You are a skeptical referee of a machine-learning leakage audit. You are shown the claim, the code change that was "
                  "tested and the measured result. You may only VETO: say veto=true if the change tested is NOT a legitimate control "
                  "for the claim (it changes the model, metric or task, or removes information the claim's intended use would have). "
                  'Reply with JSON only: {"veto": true|false, "reason": "<one sentence>"}')


def wonder_referee(case_dir, ledger, live, finding):
    """Default referee: one call to the Wonder model. Returns {"veto": bool, "reason": str, "called": bool}."""
    from agent import llm
    ledger.check("referee")
    user = (f"CLAIM:\n{(Path(case_dir) / 'excerpt.md').read_text(encoding='utf-8')[:3000]}\n\nCHANGE TESTED (diff):\n{finding.get('diff', '')[:4000]}\n\n"
            f"MEASURED: claimed {finding['summary']['claimed']} vs controlled {finding['summary']['controlled']} ({finding['summary']['metric']}), "
            f"inflation {finding['summary']['inflation']} {finding['summary']['unit']}, sign {finding['summary']['sign']}.")
    with recording_llm(ledger, "referee", live):
        raw = llm.live_complete(REFEREE_SYSTEM, user, est_usd=EST_USD_PER_CALL["referee"], tag="hybrid_referee", role="referee",
                                model=os.environ.get("NULLLAB_MODEL_REFEREE", "muse-wonder-1.0"))
    try:
        j = llm.parse_json(raw)
        return {"veto": bool(j.get("veto")), "reason": str(j.get("reason", ""))[:400], "called": True}
    except Exception:  # noqa: BLE001
        return {"veto": False, "reason": "referee reply unparsable: no veto", "called": True}


# ---------------- the router ----------------
def _step(steps, step, by, detail=""):
    steps.append({"step": step, "by": by, "detail": detail})


def _verdict_from(summary):
    return "INFLATED" if summary and summary["sign"] == "+" else "NOT INFLATED"


def run_hybrid(case_dir, *, live=False, referee=False, referee_fn=None, measure=None, spark_runner=None, detector=None,
               fresh=False, allow_recorded=True, out_dir=None, max_spark_calls=MAX_SPARK_CALLS, root=ROOT):
    """Audit one case folder (train.py, data.csv, excerpt.md). Returns the result dict (also written to out_dir/hybrid.json).

    measure(case_dir)->(rule_record, how)            default: default_measure (stored-if-identical, else local sandbox)
    spark_runner(case_dir, ledger, live)->loop record default: spark_loop (real planner; needs live or replay)
    detector(case_dir)->detection dict               default: baselines.rulefix.detect
    referee_fn(case_dir, ledger, live, finding)      default: wonder_referee; only used when referee=True"""
    case_dir = Path(case_dir)
    name = case_dir.name
    ledger = Ledger(max_spark=max_spark_calls)
    steps = []
    det = (detector or rulefix.detect)(case_dir)
    applicable = sorted(r for r, v in det["fired"].items() if v.get("applicable") is not False)
    _step(steps, "detect leakage patterns", TAG_RULES,
          f"rules fired: {', '.join(sorted(det['fired'])) or 'none'}" + (f"; detected but not applicable: {', '.join(det['not_applied'])}" if det["not_applied"] else ""))
    res = {"case": name, "case_dir": str(case_dir), "rules_fired": sorted(det["fired"]), "rules_applicable": applicable,
           "verdict": None, "source": None, "route": None, "summary": None, "needs_model": False, "referee": None,
           "record_file": None, "diff": ""}
    rule_rec = spark_rec = None
    rule_summary = None
    disagree = None

    # --- rules branch
    if applicable:
        try:
            rule_rec, how = (measure or (lambda c: default_measure(c, fresh=fresh, root=root)))(case_dir)
        except Exception as e:  # noqa: BLE001
            rule_rec, how = {"status": "error", "stderr": repr(e)[:400]}, "measurement raised"
        rule_summary = summarize(rule_rec)
        _step(steps, "measure the rule fix (4 configs x seeds 42/43/44, unpaired bootstrap)", TAG_SANDBOX,
              how + (f"; sign {rule_summary['sign']}" if rule_summary else f"; status {rule_rec.get('status')}"))
        if rule_summary and rule_summary["sign"] == "+":
            res.update(verdict="INFLATED", source=TAG_RULES, route="rules fired and the measurement confirms (consistency check passed)",
                       summary=rule_summary)
        else:
            disagree = ("rules fired but the measured drop is not clearly positive (sign " + (rule_summary["sign"] if rule_summary else "n/a") + ")"
                        if rule_summary else "rules fired but the measurement failed")
            _step(steps, "consistency check", TAG_RULES, "DISAGREE: " + disagree + " -> model consulted")
    else:
        disagree = "no rule fired" if not det["fired"] else "rule(s) detected but their remedy is not applicable"
        _step(steps, "route", TAG_RULES, f"{disagree} -> model consulted")

    # --- model branch
    if res["verdict"] is None:
        runner = spark_runner or (lambda c, led, lv: spark_loop(c, led, lv))
        got = None
        try:
            from agent import llm
            if live or llm.replaying() or spark_runner is not None:
                spark_rec = runner(case_dir, ledger, live)
                got = TAG_SPARK if live else (TAG_SPARK + " (replayed traces, no new call)" if llm.replaying() else TAG_SPARK + " (injected runner, no live call)")
            elif allow_recorded and (rec := find_recorded_spark(case_dir, root)):
                spark_rec, src_file = rec
                got = TAG_SPARK_REC
                _step(steps, "plan and fix", got, f"served from {src_file}; no call made")
            else:
                raise NeedsModel("offline: no recorded Spark run of this case and --live not given")
        except NeedsModel as e:
            res["needs_model"] = True
            if rule_summary:  # rules fired but measurement did not confirm: keep their measured numbers, flag it
                res.update(verdict="UNRESOLVED", source=TAG_RULES, summary=rule_summary,
                           route=f"{disagree}; {e}. Rules measured no clear drop; the model was not consulted")
            elif applicable:  # a rule fired but its measurement failed: the numbers are missing, not "no leakage"
                res.update(verdict="MEASUREMENT_FAILED", source=TAG_RULES,
                           route=f"{disagree} ({(rule_rec or {}).get('status')}: {str((rule_rec or {}).get('stderr', ''))[-200:]}); {e}")
            else:
                res.update(verdict="NEEDS_MODEL", source=TAG_RULES,
                           route=f"{disagree}; {e}. No leakage pattern in the rule library matched: this is NOT a clean bill of health")
        except BudgetExceeded as e:
            res.update(verdict="INCONCLUSIVE", source=TAG_SPARK, route=f"{disagree}; {e}")
        except Exception as e:  # noqa: BLE001  (LiveNotAllowed, bad JSON from the model, ...)
            res.update(verdict="INCONCLUSIVE", source=TAG_SPARK, route=f"{disagree}; model path failed: {e!r}"[:500])
        if spark_rec is not None:
            if got and got != TAG_SPARK_REC:
                _step(steps, "plan and fix (structured edits)", got, f"{len(ledger.calls)} model call(s)")
            ss = summarize(spark_rec)
            if ss is None:
                res.update(verdict="INCONCLUSIVE", source=got, route=f"{disagree}; the model's fix was rejected or failed: "
                           + "; ".join(spark_rec.get("reason") or ["no stats"])[:300])
            else:
                res.update(verdict=_verdict_from(ss), source=got, summary=ss,
                           route=f"{disagree}; model consulted" + (f" (rules had said sign {rule_summary['sign']})" if rule_summary else ""))
    final_rec = spark_rec if (spark_rec is not None and summarize(spark_rec)) else (rule_rec if rule_summary else None)
    res["final_kind"] = "loop" if final_rec is spark_rec and spark_rec is not None else "rulefix"

    # --- referee (veto only)
    if referee and res["verdict"] == "INFLATED" and final_rec is not None:
        try:
            finding = {"summary": res["summary"], "diff": audit.patch_diff(case_dir, final_rec, "fix_both")}
            r = (referee_fn or wonder_referee)(case_dir, ledger, live, finding)
        except Exception as e:  # noqa: BLE001
            r = {"veto": False, "reason": f"referee not run: {e}"[:300], "called": False}
        res["referee"] = r
        _step(steps, "referee (veto only)", TAG_WONDER, ("VETO: " if r.get("veto") else "no veto: ") + r.get("reason", ""))
        if r.get("veto"):
            res.update(verdict="DISPUTED", source=TAG_WONDER + " veto (over " + res["source"] + ")")

    res["steps"] = steps
    res["ledger"] = ledger.totals()
    res["steps"].append({"step": "verdict", "by": res["source"] or "-", "detail": res["verdict"]})
    if final_rec is not None:
        with contextlib.suppress(Exception):
            res["diff"] = audit.patch_diff(case_dir, final_rec, "fix_both")
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        if final_rec is not None:
            if res["final_kind"] == "loop":
                f = out / "r1.json"
                f.write_text(json.dumps({"repeat": "hybrid", "loop": {name: final_rec}}, indent=1), encoding="utf-8")
            else:
                f = out / f"{name}.json"
                f.write_text(json.dumps(final_rec, indent=1), encoding="utf-8")
            res["record_file"] = str(f)
        (out / "hybrid.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    return res


# ---------------- report ----------------
def render_report(res, case_dir=None, detail=True):
    """Markdown: verdict, who produced each step, cost ledger, then (when a record exists) the full reviewer audit report."""
    s = res["summary"]
    L = [f"# NullLab hybrid audit: {res['case']}", "",
         f"**Verdict: {res['verdict']}** | produced by: **{res['source']}**", "", f"Route: {res['route']}", ""]
    if s:
        L += [f"Claimed {s['claimed']} vs controlled {s['controlled']} ({s['metric']}); inflation {s['inflation']:+} {s['unit']}; "
              f"sign `{s['sign']}` (per seed {s['per_seed_sign']}); 95% interval per seed (unpaired bootstrap): "
              + ", ".join(f"{k}: [{a}, {b}]" for k, (a, b) in s["ci_per_seed"].items()) + ".", ""]
    if res.get("needs_model"):
        L += ["> The model was needed and not called. This verdict is not a statement that the pipeline is clean.", ""]
    L += ["## Who did what", "", "| step | produced by | detail |", "|---|---|---|"]
    L += [f"| {x['step']} | {x['by']} | {x['detail']} |" for x in res["steps"]]
    lg = res["ledger"]
    L += ["", "## Cost ledger", "",
          f"Model calls: **{lg['calls']}** live, {lg['replayed_calls']} replayed. Estimated USD: **{lg['est_usd']:.2f}**. "
          f"Estimated tokens: {lg['tokens_in_est']} in / {lg['tokens_out_est']} out.", ""]
    if lg["by_model"]:
        L += ["| model | live calls | replayed | est. tokens in | est. tokens out | est. USD |", "|---|---|---|---|---|---|"]
        L += [f"| {m} | {b['calls']} | {b['replayed_calls']} | {b['tokens_in_est']} | {b['tokens_out_est']} | {b['est_usd']:.2f} |" for m, b in lg["by_model"].items()]
        L.append("")
    else:
        L += ["No model was called: the rule path and the local sandbox cost $0.", ""]
    L += [f"_{lg['note']}_", ""]
    if res.get("referee"):
        L += ["## Referee", "", f"Wonder referee ({'veto' if res['referee'].get('veto') else 'no veto'}): {res['referee'].get('reason', '')}", ""]
    if detail and res.get("record_file") and case_dir:
        try:
            F = audit.build_finding(case_dir, case=res["case"], run=res["record_file"])
            L += ["---", "", "## Full audit report (agent.audit, built from the stored record)", "", audit.render_md(F)]
        except SystemExit as e:
            L += ["", f"_Full audit report not built: {e}_"]
        except Exception as e:  # noqa: BLE001
            L += ["", f"_Full audit report not built: {e!r}_"]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m agent.hybrid", description=__doc__.split("\n")[0])
    ap.add_argument("case_dir")
    ap.add_argument("--live", action="store_true", help="allow real model calls (still passes the spend gate); default is offline")
    ap.add_argument("--referee", action="store_true", help="enable the Wonder veto referee (off by default; max 10 calls)")
    ap.add_argument("--out", help="directory for hybrid.json and the measured record (default: a temp dir)")
    ap.add_argument("--report", help="write the markdown report here")
    ap.add_argument("--fresh", action="store_true", help="ignore stored rule measurements, re-run the sandbox")
    ap.add_argument("--no-recorded", action="store_true", help="do not serve the model path from recorded runs")
    a = ap.parse_args(argv)
    out = a.out or tempfile.mkdtemp(prefix="nulllab_hybrid_")
    res = run_hybrid(a.case_dir, live=a.live, referee=a.referee, fresh=a.fresh, allow_recorded=not a.no_recorded, out_dir=out)
    text = render_report(res, a.case_dir)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text, encoding="utf-8", newline="\n")
    lg = res["ledger"]
    print(f"{res['case']}: {res['verdict']} [{res['source']}] model calls {lg['calls']} est ${lg['est_usd']:.2f}; record dir {out}"
          + (f"; report {a.report}" if a.report else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
