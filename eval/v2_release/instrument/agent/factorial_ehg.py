"""EHG: preregistered run of the G8 harness on the disguised EHG pair (real/ehg_disguised leaky, real/ehg_disguised_clean).
Imports agent/factorial_g8.py (and through it g7/g5/g6/llm/fidelity), which are NOT edited; only the case mapping, the run directory, the
call log, the caps and the acceptance numbers are new. Preregistration: docs/EVAL-11-EHG-PREREG.md.

Everything lives in runs_ehg/ (own call log, own traces, own prereg log). configure() points the G8 modules' env-driven paths there
and refuses to proceed if any path would fall back to runs_g8/ (a live G8 run may be writing there).

Driver:  .venv/Scripts/python.exe -m agent.factorial_ehg [--model M] [--out DIR] <stage> [args]
Stages:  project             print projected spend and caps (no call)
         rulefix [force]     OFFLINE $0: baselines/rulefix.py on both cases through the sandbox -> runs_ehg/rules.json
         hashes              print the LF-normalised sha256 of code, prompts, rules, agent views (no write)
         freeze              append those hashes (with their payloads) to runs_ehg/prereg_log.jsonl
         verify              recompute the hashes from disk and compare with the last freeze record
         run <r>...          LIVE. refuses unless verify passes. repeats r in 1..3: B3 + the G8 pipeline per case
         score               preregistered acceptance -> runs_ehg/score.json
         usage               estimated spend and real tokens from the saved case records

Hash rule: every file is hashed after normalising CRLF to LF (git/OneDrive/Windows editors change line endings, the G7 log hash did not
match the file for that reason). A verifier recomputes: sha256(open(f,'rb').read().replace(b'\\r\\n', b'\\n')). A JSON payload is hashed as
sha256(json.dumps(payload, sort_keys=True)) (default separators, ensure_ascii)."""
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
from agent import factorial_g8 as g8, llm  # noqa: E402
from agent import factorial_g7 as g7  # noqa: E402
from agent.factorial import agent_view  # noqa: E402

LEAKY, CLEAN = "ehg_disguised", "ehg_disguised_clean"
CASES = {c: ROOT / "real" / c for c in (LEAKY, CLEAN)}
N_REPEATS = 3
TEMPERATURE = g8.TEMPERATURE            # 0.7
DEFAULT_MODEL = g8.DEFAULT_MODEL        # muse-spark-1.3-contributor
TOTAL_CALL_CAP = 40                     # all live calls of this run, B3 included; enforced by llm.MAX_G8_CALLS on OUR log
CEILING_USD = float(os.environ.get("NULLLAB_EHG_CEILING", "3.00"))
REFERENCE_INFLATION = 0.430             # offline reference, runs_g8_cases/reference.json (n=10 seeds): mean ROC-AUC 0.970 vs 0.540
PUBLISHED_RANGE = (0.36, 0.49)          # SVM row 0.358 .. RF row 0.494 (eval/g8_truth.json); the RF row is the stored truth value
TOL = 0.15

# files whose content is frozen (hashed after LF normalisation)
CODE_FILES = ("agent/factorial_ehg.py", "agent/factorial_g8.py", "agent/factorial_g7.py", "agent/llm.py", "agent/fidelity.py",
              "agent/factorial_g5.py", "agent/factorial_g6.py", "agent/factorial.py", "g4.py", "eval/build_g8_cases.py",
              "eval/g8_truth.json", "eval/run_rulefix.py", "baselines/rulefix.py", "sandbox/factorial_stats.py",
              "sandbox/run_factorial.py", "sandbox/executor.py")
DOC = "docs/EVAL-11-EHG-PREREG.md"


# ---------------- hashing (LF-normalised; the freeze log and the verifier use these same functions) ----------------
def lf_bytes(b):
    return b.replace(b"\r\n", b"\n")


def sha_file(p):
    return hashlib.sha256(lf_bytes(Path(p).read_bytes())).hexdigest()


def sha_obj(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def sha_text(s):
    return hashlib.sha256(s.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def code_hashes(root=ROOT):
    return {x: sha_file(Path(root) / x) for x in CODE_FILES}


def prompt_hashes():
    return {"planner_system_sha256": sha_text(g8.SYSTEM), "b3_system_sha256": sha_text(g8.B3_SYSTEM),
            "bundle_sha256_g8_compatible": sha_obj({"planner_system": g8.SYSTEM, "b3_system": g8.B3_SYSTEM})}


def rules_payload():
    return {"forecast_words": list(g7.FORECAST_WORDS), "repair_kinds": list(g8.REPAIR_KINDS), "case_call_cap": g8.CASE_CALL_CAP,
            "total_call_cap": TOTAL_CALL_CAP, "temperature": TEMPERATURE, "n_repeats": N_REPEATS, "seeds": list(g8.SEEDS),
            "n_boot": g8.N_BOOT, "guard_rules": ["justification", "split_required"], "tolerance": TOL,
            "reference_inflation": REFERENCE_INFLATION, "published_range": list(PUBLISHED_RANGE),
            "acceptance": {"direction_right_min": 3, "clean_false_alarms_max": 0, "magnitude_ok_min": 2, "denominator_each": N_REPEATS,
                           "harness_inconclusive": "counted in the denominator as not-met; never a false alarm"},
            "ceiling_usd": CEILING_USD}


def view_hashes():
    out = {}
    for c, d in CASES.items():
        out[c] = {"files_lf": {n: sha_file(d / n) for n in ("train.py", "data.csv", "excerpt.md")},
                  "agent_view_text_sha256": sha_text(agent_view(d)),
                  "planner_user_msg_sha256": sha_text(g8.factorial_g5.user_msg(d, "RID")),
                  "forecast_words_in_excerpt": g7.forecast_claim((d / "excerpt.md").read_text(encoding="utf-8"))}
    return out


def all_hashes():
    return {"code": code_hashes(), "prompts": prompt_hashes(), "rules": {"payload": rules_payload(), "sha256": sha_obj(rules_payload())},
            "agent_views": view_hashes()}


# ---------------- paths / environment ----------------
def out_dir():
    d = Path(os.environ.get("NULLLAB_EHG_OUT") or ROOT / "runs_ehg")
    d.mkdir(parents=True, exist_ok=True)
    return d


def configure():
    """Point every env-driven path of the G8 modules at OUR directory and set our caps. Raises if anything would hit runs_g8."""
    d = out_dir()
    os.environ["NULLLAB_PHASE"] = "g8"
    os.environ["NULLLAB_G8_OUT"] = str(d)
    os.environ["NULLLAB_G8_LOG"] = str(d / "live_calls_ehg.jsonl")
    os.environ["NULLLAB_TRACES"] = str(d / "traces.jsonl")
    llm.MAX_G8_CALLS = TOTAL_CALL_CAP
    g8.CEILING_USD = CEILING_USD
    forbidden = (ROOT / "runs_g8").resolve()
    for p in (g8.out_dir(), llm.g8_log(), llm.trace_file()):
        if forbidden in Path(p).resolve().parents or Path(p).resolve() == forbidden:
            raise SystemExit(f"refusing: {p} is under runs_g8 (a live G8 run owns it)")
    return d


def _prereg(kind, payload, case=None):
    rec = {"kind": kind, "case": case, "model": llm.model_for(), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "normalisation": "CRLF->LF before hashing", "payload": payload, "sha256": sha_obj(payload)}
    with (out_dir() / "prereg_log.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _save(name, obj):
    with g8._IO:
        (out_dir() / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8", newline="\n")


def _load(name, default=None):
    p = out_dir() / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


# ---------------- stages: project / hashes / freeze / verify ----------------
def project(args=None):
    configure()
    pj = g8.print_projection(2 * N_REPEATS)
    pj = dict(pj, total_call_cap=TOTAL_CALL_CAP, within_total_cap=pj["max_live_calls_total"] <= TOTAL_CALL_CAP)
    print(json.dumps(pj))
    return pj


def hashes(args=None):
    print(json.dumps(all_hashes(), indent=1))


def freeze(args=None):
    configure()
    h = all_hashes()
    _prereg("ehg_source_hashes", h["code"])
    _prereg("ehg_prompts", h["prompts"])
    _prereg("ehg_rules", h["rules"]["payload"])
    for c, v in h["agent_views"].items():
        _prereg("ehg_agent_view_frozen", v, c)
    doc = ROOT / DOC
    _prereg("ehg_prereg_doc", {"path": DOC, "sha256_lf": sha_file(doc) if doc.exists() else None})
    print("frozen ->", out_dir() / "prereg_log.jsonl")


def _last(kind, case=None):
    p = out_dir() / "prereg_log.jsonl"
    recs = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
    recs = [r for r in recs if r["kind"] == kind and r.get("case") == case]
    return recs[-1] if recs else None


def verify_problems():
    """Recompute everything from disk and compare with the LAST freeze record of each kind. Returns a list of problems."""
    h, bad = all_hashes(), []
    checks = [("ehg_source_hashes", None, h["code"]), ("ehg_prompts", None, h["prompts"]), ("ehg_rules", None, h["rules"]["payload"])]
    checks += [("ehg_agent_view_frozen", c, v) for c, v in h["agent_views"].items()]
    for kind, case, now in checks:
        rec = _last(kind, case)
        if rec is None:
            bad.append(f"{kind} {case or ''}: no freeze record")
        elif rec["payload"] != now or rec["sha256"] != sha_obj(now) or rec["sha256"] != sha_obj(rec["payload"]):
            diff = [k for k in now if isinstance(now, dict) and rec["payload"].get(k) != now[k]] if isinstance(rec["payload"], dict) else []
            bad.append(f"{kind} {case or ''}: differs from the freeze record {diff}")
    doc = _last("ehg_prereg_doc")
    if doc is None or not (ROOT / DOC).exists():
        bad.append("prereg doc: no freeze record or file missing")
    elif doc["payload"]["sha256_lf"] != sha_file(ROOT / DOC):
        bad.append("prereg doc changed after the freeze")
    return bad


def verify(args=None):
    configure()
    bad = verify_problems()
    print("VERIFY OK: every hash recomputed from disk equals its freeze record" if not bad else "VERIFY FAILED:\n- " + "\n- ".join(bad))
    return not bad


# ---------------- offline: the rule-based baseline on the pair ($0, no model) ----------------
def _rule_row(rec):
    """Same row as eval/run_rulefix._row (copied verbatim so agent code never imports eval/)."""
    import g4
    st = rec["stats"]
    sign, cats = g4.case_sign(st)
    comp = g4.components(st)
    full = {s: st[s]["full"] for s in sorted(st)}
    scale = 100.0 if rec.get("metric", "accuracy") == "accuracy" else 1.0
    unit = "pp" if scale == 100.0 else "PR-AUC"
    return {"status": "ok", "sign": sign, "per_seed": cats, "verdict": "INFLATED" if sign == "+" else "NOT INFLATED", "unit": unit,
            "inflation": round(comp["both"] * scale, 3), "A": round(comp["A"] * scale, 3), "B": round(comp["B"] * scale, 3),
            "I": round(comp["AxB"] * scale, 3),
            "ci_per_seed": {s: [round(x * scale, 3) for x in full[s]["drop_ci"]["fix_both"]] for s in full},
            "n_orig": {s: full[s]["n"]["orig"] for s in full}, "n_fix_both": {s: full[s]["n"]["fix_both"] for s in full},
            "acc_orig": {s: round(full[s]["acc"]["orig"], 4) for s in full}, "acc_fix_both": {s: round(full[s]["acc"]["fix_both"], 4) for s in full},
            "fired": list(rec["fired"]), "not_applied": rec["not_applied"],
            "rules_applied_both": rec["configs"]["fix_both"]["rules_applied"], "steps_changed": rec["configs"]["fix_both"]["steps"]}


def rulefix(args=None):
    configure()
    p = out_dir() / "rules.json"
    if p.exists() and "force" not in (args or []):
        print(p, "exists; pass 'force' to redo")
        return json.loads(p.read_text(encoding="utf-8"))
    from agent import rules_measure  # agent code stays out of the evaluation folder (invariant in tests/test_nulllab.py)
    from baselines import rulefix as rf
    out = {"label": "OFFLINE rule baseline (baselines/rulefix.py, no LLM, $0, no live call) on the disguised EHG pair; run BEFORE any live call",
           "spec_sha256": rf.spec_sha256(), "rulefix_sha256_lf": sha_file(ROOT / "baselines" / "rulefix.py"), "cases": {}}
    for c, d in CASES.items():
        rec = rules_measure.run_case(d)
        row = _rule_row(rec) if rec["status"] == "ok" else {"status": rec["status"], "stderr": rec.get("stderr")}
        out["cases"][c] = {"fired": rec["fired"], "not_applied": rec["not_applied"], "status": rec["status"], "row": row,
                           "elapsed_s": rec["elapsed_s"],
                           "configs": {k: {"rules_applied": v["rules_applied"], "src_sha256": v["src_sha256"]} for k, v in rec["configs"].items()}}
        print(f"{c:22s} {rec['status']} fired={list(rec['fired'])} sign={row.get('sign')} inflation={row.get('inflation')}", flush=True)
    out["rules_fire_on_pair"] = any(v["fired"] for v in out["cases"].values())
    _save("rules", out)
    return out


# ---------------- live: B3 + the G8 pipeline per case ----------------
def run(args):
    configure()
    bad = verify_problems()
    if bad:
        raise SystemExit("REFUSING TO RUN: freeze missing or code/prompts/views changed since freeze:\n- " + "\n- ".join(bad))
    reps = [int(a) for a in args]
    if not reps or any(r < 1 or r > N_REPEATS for r in reps):
        raise SystemExit(f"repeats must be in 1..{N_REPEATS}")
    model = llm.model_for()
    res = {r: _load(f"r{r}", {"repeat": f"ehg-r{r}", "model": model, "temperature": TEMPERATURE, "b3": {}, "loop": {}}) for r in reps}
    todo = [(r, c) for r in reps for c in CASES if c not in res[r]["loop"]]  # a recorded harness failure is NOT re-rolled
    pj = g8.print_projection(len(todo))
    if not llm.replaying() and g8.my_spent() + pj["worst_case_usd"] > CEILING_USD:
        print(f"STOP: est spent ${g8.my_spent():.2f} + worst case ${pj['worst_case_usd']:.2f} passes ceiling ${CEILING_USD:.2f}", flush=True)
        return

    def one(r, c):
        t0 = time.time()
        if c not in res[r]["b3"] or "error" in res[r]["b3"][c]:
            try:
                raw, usage = llm.live_complete_ex(g8.B3_SYSTEM, agent_view(CASES[c]) + f"\n\n[repeat id: ehg-r{r}]", est_usd=g8.EST["b3"],
                                                  tag="ehg_b3", role="b3", model=llm.model_for("b3"), temperature=TEMPERATURE)
                res[r]["b3"][c] = {"ans": llm.parse_json(raw), "raw": raw, "usage": usage}
            except Exception as e:  # noqa: BLE001
                res[r]["b3"][c] = {"error": repr(e)[:400]}
        lr = g8.pipeline(CASES[c], f"ehg-r{r}", model=model)
        print(f"ehg-r{r} {c:22s} {g8.outcome_label(lr)} calls={len(lr.get('calls', []))} {time.time() - t0:.0f}s", flush=True)
        return lr

    with ThreadPoolExecutor(3) as ex:
        futs = {k: ex.submit(one, *k) for k in todo}
        for (r, c), f in futs.items():
            try:
                res[r]["loop"][c] = f.result()
            except Exception as e:  # noqa: BLE001
                res[r]["loop"][c] = {"status": "INCONCLUSIVE", "harness_failure": "internal_error",
                                     "label": g8.label("INCONCLUSIVE", "internal_error"), "reason": [repr(e)[:400]], "calls": [], "retries": 0}
            _save(f"r{r}", res[r])


# ---------------- scoring ----------------
def b3_row(rec_b3, c):
    if "ans" not in (rec_b3 or {}):
        return {"error": (rec_b3 or {}).get("error", "not run")}
    a = rec_b3["ans"]
    try:
        fb = float(a["predicted_drop_pp"]["fix_both"])
    except (KeyError, TypeError, ValueError):
        return {"error": "unusable B3 answer"}
    row = {"leak": bool(a.get("leak")), "fix_both_pp": fb}
    if c == LEAKY:
        row["gets_it"] = row["leak"] and fb >= 2 and abs(fb / 100 - REFERENCE_INFLATION) <= TOL
    else:
        row["false_alarm"] = row["leak"]
    return row


def score_cases(records, b3=None):
    """Pure. records = {case: {'r1': loop record, ...}}. Acceptance fixed in the prereg; harness failures stay in the denominator."""
    import numpy as np
    L, C = records.get(LEAKY, {}), records.get(CLEAN, {})
    rows, harness = {LEAKY: {}, CLEAN: {}}, []
    for c, d in ((LEAKY, L), (CLEAN, C)):
        for r, rec in sorted(d.items()):
            row = {"label": g8.outcome_label(rec), "sign": g8.sign_of(rec), "calls": len(rec.get("calls", [])), "retries": rec.get("retries")}
            if rec.get("status") == "ok":
                infl = [rec["stats"][s]["full"]["drop"]["fix_both"] for s in sorted(rec["stats"])]
                row["inflation_mean"] = round(float(np.mean(infl)), 3)
                row["inflation_ci"] = [[round(x, 3) for x in rec["stats"][s]["full"]["drop_ci"]["fix_both"]] for s in sorted(rec["stats"])]
                if c == LEAKY:
                    row["magnitude_ok"] = abs(row["inflation_mean"] - REFERENCE_INFLATION) <= TOL
                    row["within_published_range"] = PUBLISHED_RANGE[0] - 0.005 <= row["inflation_mean"] <= PUBLISHED_RANGE[1] + 0.005
            else:
                harness.append({"case": c, "repeat": r, "failure": rec.get("harness_failure"), "reason": (rec.get("reason") or [""])[0][:200]})
            if b3 and r in b3.get(c, {}):
                row["b3"] = b3[c][r]
            rows[c][r] = row
    acc = {"n_leaky": len(L), "n_clean": len(C),
           "a_direction_right": sum(x["sign"] == "+" for x in rows[LEAKY].values()),
           "b_clean_false_alarms": sum(x["sign"] == "+" for x in rows[CLEAN].values()),
           "c_magnitude_within_0.15_of_0.43": sum(bool(x.get("magnitude_ok")) for x in rows[LEAKY].values()),
           "no_effect_leaky": sum(x["sign"] == "0" for x in rows[LEAKY].values()),
           "no_effect_clean": sum(x["sign"] == "0" for x in rows[CLEAN].values()),
           "harness_inconclusive": len(harness), "denominator_leaky": N_REPEATS, "denominator_clean": N_REPEATS}
    acc["PASS"] = (len(L) == N_REPEATS and len(C) == N_REPEATS and acc["a_direction_right"] == N_REPEATS
                   and acc["b_clean_false_alarms"] == 0 and acc["c_magnitude_within_0.15_of_0.43"] >= 2)
    acc["harness_target_met"] = acc["harness_inconclusive"] == 0
    b3s = [x["b3"] for d in rows.values() for x in d.values() if "b3" in x]
    acc["b3_gets_it_leaky"] = sum(bool(x["b3"].get("gets_it")) for x in rows[LEAKY].values() if "b3" in x)
    acc["b3_false_alarms_clean"] = sum(bool(x["b3"].get("false_alarm")) for x in rows[CLEAN].values() if "b3" in x)
    acc["b3_errors"] = sum("error" in x for x in b3s)
    return {"acceptance": acc, "harness_failures": harness, "cases": rows}


def truth_check():
    """Host-only: read the published numbers out of eval/g8_truth.json and confirm the constants used for scoring."""
    t = json.loads((ROOT / "eval" / "g8_truth.json").read_text(encoding="utf-8"))[LEAKY]["published"]
    b, a = t["table2_oversample_before_partition_AUC_reproduced"], t["table3_oversample_after_partition_AUC_default"]
    rows = {k: round((b[k] - a[k]) / 100, 3) for k in b}
    return {"published_rows": rows, "stored_truth": t["published_inflation_roc_auc"],
            "range_ok": min(rows.values()) == round(PUBLISHED_RANGE[0], 3) or abs(min(rows.values()) - PUBLISHED_RANGE[0]) < 0.005,
            "max_row_ok": abs(max(rows.values()) - PUBLISHED_RANGE[1]) < 0.005}


def score(args=None):
    configure()
    recs, b3 = {c: {} for c in CASES}, {c: {} for c in CASES}
    for r in range(1, N_REPEATS + 1):
        d = _load(f"r{r}")
        for c in CASES:
            if d and c in d.get("loop", {}):
                recs[c][f"r{r}"] = d["loop"][c]
                b3[c][f"r{r}"] = b3_row(d.get("b3", {}).get(c), c)
    out = score_cases(recs, b3)
    out["rules_baseline"] = {c: {"fired": v["fired"], "sign": v["row"].get("sign"), "inflation": v["row"].get("inflation")}
                             for c, v in (_load("rules", {}) or {}).get("cases", {}).items()}
    out["truth_check"] = truth_check()
    out["usage"] = g8.usage_summary()
    out["note"] = "inflation = claimed minus controlled ROC-AUC (fix_both), mean over seeds 42/43/44; reference +0.430, published range +0.36..+0.49"
    _save("score", out)
    print(json.dumps(out["acceptance"], indent=1))
    for h in out["harness_failures"]:
        print("HARNESS FAILURE", h)
    return out


STAGES = {"project": project, "hashes": hashes, "freeze": freeze, "verify": verify, "rulefix": rulefix, "run": run, "score": score,
          "usage": lambda a=None: (configure(), print(json.dumps(g8.usage_summary())))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--out")
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    os.environ["NULLLAB_MODEL"] = a.model or os.environ.get("NULLLAB_MODEL") or DEFAULT_MODEL
    if a.out:
        os.environ["NULLLAB_EHG_OUT"] = a.out
    STAGES[a.stage](a.args)


if __name__ == "__main__":
    main()
