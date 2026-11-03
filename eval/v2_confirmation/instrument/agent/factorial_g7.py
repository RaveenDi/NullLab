"""G7: disguised civil-war case, SPLIT-USE-REQUIRED rule, schema-validated planner, swappable model, traces and replay,
and the muse-wonder planner probe. Copy/extension of the G6 pipeline (agent/factorial_g6.py, g6.py are NOT edited).
Driver:  .venv/Scripts/python.exe -m agent.factorial_g7 [--model M] [--temp T] [--out DIR] [--replay TRACES] <stage> [args]
Stages (all live stages run with NULLLAB_PHASE=g7: own call log runs_g7/live_calls_g7.jsonl, own cap, every reply traced):
  rule            write runs_g7/PREREG.md + log its sha256, source and prompt hashes            (before any live call)
  replay6         OFFLINE $0: SPLIT-USE-REQUIRED over the saved G6 plans (+ G5 plans)           -> replay_g6.json
  ref             OFFLINE $0: builder reference (temporal split) on the disguised cases          -> ref.json
  modelcheck <m>  one cheap call: does model m serve chat completions at temperature 0.7?        -> modelcheck_<m>.json
  probe <v>       contamination probe of disguise version v (2 calls)                            -> probe_v<v>.json
  freeze          log sha256 of the frozen agent views of both disguised cases
  run <r>...      repeats: B3 + planner for both cases, then guarded loop (3 in parallel)         -> r<r>.json
  score           preregistered acceptance                                                       -> score.json
  wonder          muse-wonder-1.0 as planner on the 8 synthetic G5 cases (one repeat)            -> wonder.json
  spark5          offline: the same metrics computed from the saved spark G5 runs                -> spark_g5_metrics.json"""
import argparse
import ast
import calendar
import hashlib
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import factorial_g5, factorial_g6, fidelity, llm  # noqa: E402
from agent.factorial import agent_view  # noqa: E402

CASES = {c: ROOT / "real" / c for c in ("civilwar_disguised", "civilwar_disguised_clean")}
LEAKY, CLEAN = "civilwar_disguised", "civilwar_disguised_clean"
SEEDS, N_BOOT = (42, 43, 44), 1000
PUBLISHED_INFLATION, TOL = 0.36, 0.15
N_REPEATS = 5
TEMPERATURE = 0.7
TASK1_CEILING_USD, TOTAL_CEILING_USD = 3.30, 4.50   # estimates summed from runs_g7/live_calls_g7.jsonl
EST = {"b3": 0.08, "plan": 0.10, "retry": 0.10, "probe": 0.03, "check": 0.02}
KINDS = ("split", "fit_scope", "feature")
_IO = threading.Lock()

# B3 = the single-prompt reading baseline. Copied verbatim from baselines/single_prompt.FACTORIAL_SYSTEM (G6 used the
# same text); tests/test_g7.py asserts the copy is still identical.
B3_SYSTEM = (
    "You are reviewing a machine-learning claim for evaluation flaws. Do NOT run any code; judge from reading only. "
    "Given the paper excerpt, the training script and the data head, name up to two flaws (A and B) that could make the "
    "reported accuracy higher than the claim's intended use would see. Predict the accuracy drop in percentage points "
    "(positive = accuracy falls) if ONLY A were fixed, if ONLY B were fixed, and if BOTH were fixed. Rank the culprits of the "
    "inflation among 'A' (A alone carries most of it), 'B' (B alone carries most of it), 'AxB' (only the combination: fixing "
    "either alone leaves most of the inflation). Return ONLY JSON: "
    '{"leak": true/false, "A": str, "B": str, "predicted_drop_pp": {"fix_A": number, "fix_B": number, "fix_both": number}, '
    '"culprit_ranking": ["A"|"B"|"AxB", ...], "confidence": <0-1>, "reason": <one sentence>}.')

# The G6 planner prompt, unchanged: SPLIT-USE-REQUIRED is enforced by the guard and taught only by the rejection text.
SYSTEM = factorial_g6.SYSTEM


def out_dir():
    d = Path(os.environ.get("NULLLAB_G7_OUT") or ROOT / "runs_g7")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _save(name, obj):
    with _IO:
        (out_dir() / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8")


def _load(name, default=None):
    p = out_dir() / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def _prereg(kind, obj, case=None, repeat=None):
    rec = {"kind": kind, "case": case, "repeat": repeat, "model": llm.model_for(), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "sha256": _sha(obj)}
    with _IO, (out_dir() / "prereg_log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    print("PREREG", kind, case, repeat, rec["sha256"][:16], flush=True)
    return rec


# ---------------- budget (own accounting from this phase's call log) ----------------
def my_spent():
    p = llm.g7_log()
    return sum(json.loads(l).get("est_usd", 0) for l in p.read_text().splitlines() if l.strip()) if p.exists() else 0.0


def budget_ok(projected, ceiling=TASK1_CEILING_USD):
    if llm.replaying():
        return True
    s = my_spent()
    if s + projected > ceiling:
        print(f"STOP: phase spend est ${s:.2f} + projected ${projected:.2f} passes the ${ceiling:.2f} ceiling", flush=True)
        return False
    return True


# ---------------- planner schema (checked before the fidelity guard) ----------------
def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def validate_plan(p):
    """Simple structural schema for the planner JSON. Returns a list of problems (empty = valid)."""
    if not isinstance(p, dict):
        return ["plan is not a JSON object"]
    v = []
    for k in ("A", "B", "reason"):
        if not isinstance(p.get(k), str) or not p[k].strip():
            v.append(f"'{k}' must be a non-empty string")
    for k in ("A_code_line", "B_code_line"):
        if k in p and not isinstance(p[k], str):
            v.append(f"'{k}' must be a string")
    e = p.get("edits")
    if not isinstance(e, dict):
        v.append("'edits' must be an object with keys A and B")
    else:
        for X in ("A", "B"):
            ex = e.get(X)
            if not isinstance(ex, dict):
                v.append(f"edits.{X} must be an object")
                continue
            if ex.get("kind") not in KINDS:
                v.append(f"edits.{X}.kind must be one of {list(KINDS)}")
            st = ex.get("steps")
            if not isinstance(st, dict) or not st or not all(isinstance(k, str) and isinstance(s, str) and s.strip() for k, s in st.items()):
                v.append(f"edits.{X}.steps must be a non-empty object {{function name: complete new def (string)}}")
        bo = e.get("both_overrides", {})
        if not isinstance(bo, dict) or not all(isinstance(s, str) for s in bo.values()):
            v.append("edits.both_overrides must be an object {function name: source string}")
    d = p.get("predicted_drop_pp")
    if not isinstance(d, dict) or not all(_num(d.get(k)) for k in ("fix_A", "fix_B", "fix_both")):
        v.append("'predicted_drop_pp' must be an object with numeric fix_A, fix_B, fix_both")
    r = p.get("culprit_ranking")
    if not isinstance(r, list) or not r or not all(x in ("A", "B", "AxB") for x in r):
        v.append("'culprit_ranking' must be a non-empty list drawn from A, B, AxB")
    return v


# ---------------- SPLIT-USE-REQUIRED (preregistered rule) ----------------
FORECAST_WORDS = ("forecast", "future", "next period", "next-period", "next epoch", "later period", "later epoch",
                  "later year", "prospective", "temporal", "chronolog", "ahead", "upcoming", "unseen period")
TIME_NAME_G7 = re.compile(r"(year|date|time|month|week|period|epoch|step|^t$|_t$)", re.I)


def forecast_claim(excerpt):
    low = excerpt.lower()
    return [w for w in FORECAST_WORDS if w in low]


def temporal_markers(fn, time_cols):
    """Evidence that a function holds rows out by TIME: TimeSeriesSplit, or an inequality against a time-like column
    (directly or through a variable assigned from it), or a sort on a time-like column followed by a slice. Static only:
    the direction (train earlier, test later) is not proven, a reversed split would pass."""
    m, tc = set(), set(time_cols)

    def timey(n):
        return n in tc or bool(TIME_NAME_G7.search(n))

    def names_in(node):
        out = {x.value for x in ast.walk(node) if isinstance(x, ast.Constant) and isinstance(x.value, str)}
        return out | {x.id for x in ast.walk(node) if isinstance(x, ast.Name)} | {x.attr for x in ast.walk(node) if isinstance(x, ast.Attribute)}

    tainted = set()  # variables assigned from an expression that mentions a time-like column
    for s in ast.walk(fn):
        if isinstance(s, ast.Assign) and any(timey(n) or n in tainted for n in names_in(s.value)):
            tainted |= {t.id for t in s.targets if isinstance(t, ast.Name)}
    has_slice = any(isinstance(s, ast.Subscript) and isinstance(s.slice, ast.Slice) for s in ast.walk(fn))
    for s in ast.walk(fn):
        if isinstance(s, ast.Call):
            nm = fidelity._fname(s)
            if nm == "TimeSeriesSplit":
                m.add("TimeSeriesSplit")
            if nm in ("sort_values", "argsort", "sort", "sort_index") and has_slice and any(timey(n) or n in tainted for n in names_in(s)):
                m.add("sort by time + slice")
        if isinstance(s, ast.Compare) and any(isinstance(o, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for o in s.ops):
            if any(timey(n) or n in tainted for n in names_in(s)):
                m.add("time comparison")
    return m


def holdout_steps(train_src):
    """Top-level steps whose return value is unpacked as the (fit rows, scored rows) pair: `tr, te = step(...)`."""
    tree = ast.parse(train_src)
    local = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple)                 and len(node.targets[0].elts) == 2 and isinstance(node.value, ast.Call) and fidelity._fname(node.value) in local:
            out.add(fidelity._fname(node.value))
    return out


def check_split_required(train_src, excerpt, header_cols, plan):
    """SPLIT-USE-REQUIRED. If the excerpt states a forecasting / next-period use, the step that chooses the scored rows
    (the hold-out step: `tr, te = step(...)` in train.py; if none is found, any 'split'-kind step) must hold rows out by
    time: (1) any edit to a hold-out step must be temporal (a random, group or positional hold-out is rejected), and
    (2) unless the ORIGINAL hold-out step is already temporal, at least one edit to it must be. Edits to other steps
    (e.g. the inner tuning CV) are not constrained by this rule. Returns violations (empty = accepted). No model call."""
    words = forecast_claim(excerpt)
    if not words:
        return []
    edits = (plan or {}).get("edits") or {}
    tcols = [c for c in header_cols if TIME_NAME_G7.search(c)]
    orig_defs = fidelity._defs(ast.parse(train_src))
    hs = holdout_steps(train_src)
    hs_known = bool(hs)
    if not hs_known:
        hs = {n for n in orig_defs if n != "load"}
    orig_temporal = any(temporal_markers(orig_defs[n], tcols) for n in hs if n in orig_defs)
    v, temporal_edit = [], False
    for X in ("A", "B"):
        e = edits.get(X) or {}
        for step, src in (e.get("steps") or {}).items():
            if step not in hs or (not hs_known and e.get("kind") != "split"):
                continue
            try:
                fn, _ = fidelity.parse_replacement(step, src)
            except ValueError:
                continue
            if temporal_markers(fn, tcols):
                temporal_edit = True
            else:
                v.append(f"SPLIT-USE-REQUIRED: the excerpt states a forecasting use ({words[0]!r}) but fix {X}'s edit of the hold-out "
                         f"step '{step}' does not hold rows out by time. The control for a forecasting claim must train on EARLIER "
                         f"values of the time column ({tcols or 'the time-like column'}) and test on LATER ones (e.g. a comparison "
                         "on the time column or TimeSeriesSplit); a random, group or positional hold-out is not accepted")
    if not v and not orig_temporal and not temporal_edit:
        v.append(f"SPLIT-USE-REQUIRED: the excerpt states a forecasting use ({words[0]!r}) and the hold-out step "
                 f"({', '.join(sorted(hs))}) does not hold rows out by time, but no fix trains on earlier and tests on later "
                 f"values of the time column ({tcols or 'time-like column'}); make a temporal split one of the two fixes")
    return v


def _case_files(case_dir):
    d = Path(case_dir)
    return ((d / "train.py").read_text(encoding="utf-8"), (d / "excerpt.md").read_text(encoding="utf-8"),
            (d / "data.csv").open(encoding="utf-8").readline().strip().split(","))


def guard(case_dir, plan, rules=("justification", "split_required")):
    """G5 static fidelity (+ G6 justification, + G7 SPLIT-USE-REQUIRED per `rules`). Returns (cfgs, problems, reports)."""
    src, exc, hdr = _case_files(case_dir)
    cfgs = fidelity.build_configs(src, (plan or {}).get("edits"))
    problems, reports = [], {}
    for cfg, info in cfgs.items():
        v = list(info["violations"])
        if not v:
            sv, rep = fidelity.check_static(src, info["src"], info["kinds"], info["declared"])
            v += sv
            reports[cfg] = {"changed": rep.get("changed"), "kinds": info["kinds"]}
        problems += [f"{cfg}: {x}" for x in v]
    if "justification" in rules:
        problems += [f"plan: {x}" for x in fidelity.check_justification(src, exc, hdr, plan)]
    if "split_required" in rules:
        problems += [f"plan: {x}" for x in check_split_required(src, exc, hdr, plan)]
    return cfgs, problems, reports


# ---------------- model calls (role/model/temperature aware; schema retry) ----------------
class PlanInvalid(RuntimeError):
    pass


def _retry_msg(case_dir, rid, prev, problems):
    return (factorial_g5.user_msg(case_dir, rid) + "\n\nYOUR PREVIOUS JSON:\n" +
            json.dumps({k: (prev or {}).get(k) for k in ("A", "A_code_line", "B", "B_code_line", "edits", "predicted_drop_pp",
                                                         "culprit_ranking", "reason")}) +
            "\n\nIt was REJECTED:\n- " + "\n- ".join(problems) +
            "\nReturn the corrected complete JSON with the same schema. Change only what the rejection requires.")


def _call_plan(system, msg, tag, role, model, temperature, system_prompt=None):
    raw = llm.live_complete(system, msg, est_usd=EST["plan"], tag=tag, role=role, model=model,
                            temperature=TEMPERATURE if temperature is None else temperature)
    try:
        p = llm.parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return None, raw, [f"reply is not parseable JSON: {e!r}"[:200]]
    return p, raw, validate_plan(p)


def plan(case_dir, rid, system=SYSTEM, model=None, temperature=None, tag="g7_planner"):
    """Planner call. Schema-invalid reply => ONE schema retry (extra call) with the schema problems; still invalid =>
    PlanInvalid. Returns (plan, raw, info)."""
    model = model or llm.model_for("planner")
    msg = factorial_g5.user_msg(case_dir, rid)
    p, raw, bad = _call_plan(system, msg, tag, "planner", model, temperature)
    info = {"schema_valid_first": not bad, "schema_retry": False}
    if bad:
        if not budget_ok(EST["plan"], TOTAL_CEILING_USD):
            raise PlanInvalid("schema-invalid and no budget for the schema retry: " + "; ".join(bad))
        info["schema_retry"], info["schema_problems"] = True, bad
        p, raw, bad2 = _call_plan(system, msg + "\n\nYOUR PREVIOUS REPLY WAS NOT VALID:\n- " + "\n- ".join(bad) +
                                  "\nReturn ONLY the corrected complete JSON object with the required schema.",
                                  tag + "_schema_retry", "planner", model, temperature)
        if bad2:
            raise PlanInvalid("schema-invalid after one retry: " + "; ".join(bad2))
    p["mode"] = llm.mode_label("planner", model)
    p["prereg_sha256"] = factorial_g5.prereg_hash(p)
    return p, raw, info


def retry_plan(case_dir, rid, prev, problems, system=SYSTEM, model=None, temperature=None, tag="g7_planner_retry"):
    model = model or llm.model_for("planner")
    p, raw, bad = _call_plan(system, _retry_msg(case_dir, rid, prev, problems), tag, "planner_retry", model, temperature)
    if bad:
        raise PlanInvalid("retry reply schema-invalid: " + "; ".join(bad))
    p["mode"] = llm.mode_label("planner", model, "retry")
    p["prereg_sha256"] = factorial_g5.prereg_hash(p)
    return p, raw


def b3(case_dir, rid, model=None, temperature=None):
    model = model or llm.model_for("b3")
    raw = llm.live_complete(B3_SYSTEM, agent_view(case_dir) + f"\n\n[repeat id: {rid}]", est_usd=EST["b3"], tag="g7_b3",
                            role="b3", model=model, temperature=TEMPERATURE if temperature is None else temperature)
    return llm.parse_json(raw), raw


# ---------------- loop: plan -> verify -> act -> recover once ----------------
def _execute(case_dir, cfgs):
    from sandbox import executor
    patches = {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}
    ex = executor.run_factorial(Path(case_dir), patches, seeds=SEEDS, timeout=1500)
    if ex["status"] != "ok":
        return None, [f"EXECUTION {ex['status']}: {ex.get('stderr', '')[-1500:]}"]
    return ex["result"], fidelity.check_runtime(ex["result"], {k: cfgs[k]["kinds"] for k in ("fix_A", "fix_B", "fix_both")})


def loop_case(case_dir, rid, plan_rec, rules=("justification", "split_required"), model=None, temperature=None,
              system=SYSTEM, ceiling=TOTAL_CEILING_USD):
    from sandbox import factorial_stats
    log = [{"phase": "Plan", "utc": time.strftime("%H:%M:%SZ", time.gmtime()), "prereg_sha256": plan_rec["plan"].get("prereg_sha256")}]
    cur, retried, rec = plan_rec["plan"], False, {"retries": 0}
    while True:
        cfgs, problems, reports = guard(case_dir, cur, rules)
        log.append({"phase": "Verify (static fidelity + rules " + "+".join(rules) + ")", "verdict": "REJECT" if problems else "ACCEPT",
                    "violations": problems[:8], "changed": reports})
        raw = None
        if not problems:
            raw, problems = _execute(case_dir, cfgs)
            log.append({"phase": "Act (sandbox, 4 configs x 3 seeds)", "status": "ok" if raw is not None else "error",
                        "runtime_violations": problems[:8]})
        if not problems:
            break
        if retried:
            rec.update({"status": "INCONCLUSIVE", "reason": problems[:8], "log": log, "final_plan": cur})
            return rec
        if not budget_ok(EST["retry"], ceiling):
            rec.update({"status": "INCONCLUSIVE", "reason": ["budget ceiling: no retry"] + problems[:8], "log": log, "final_plan": cur})
            return rec
        try:
            cur, rawtxt = retry_plan(case_dir, rid, cur, problems[:8], system, model, temperature)
        except Exception as e:  # noqa: BLE001
            rec.update({"status": "INCONCLUSIVE", "reason": [f"retry failed: {e!r}"[:400]] + problems[:8], "log": log, "final_plan": cur})
            return rec
        retried, rec["retries"] = True, 1
        r = _prereg("loop_planner_retry", {k: cur.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")}, Path(case_dir).name, rid)
        log.append({"phase": "Recover (one retry with the violation text)", "prereg_sha256": r["sha256"], "retry_raw_len": len(rawtxt)})
    stats = factorial_stats.all_seeds(raw, n_boot=N_BOOT)
    rec.update({"status": "ok", "metric": raw.get("metric", "accuracy"), "stats": stats, "final_plan": cur, "log": log,
                "fidelity": {cfg: fidelity.verdict_line(cfgs[cfg], reports[cfg]) for cfg in reports},
                "sources": {k: cfgs[k]["src"] for k in ("fix_A", "fix_B", "fix_both")}})
    return rec


# ---------------- offline: replay SPLIT-USE-REQUIRED on saved plans ----------------
def replay6(args=None):
    """What would SPLIT-USE-REQUIRED have changed on the saved G6 (and G5) loop plans? $0, no model call."""
    import g4
    out = {"rule": "SPLIT-USE-REQUIRED (agent/factorial_g7.check_split_required) only; G5/G6 guards unchanged", "g6": {}, "g5": {}}
    g6cases = {c: ROOT / "real" / c for c in ("civilwar_apparent", "civilwar_temporal_clean", "esl_selection", "esl_selection_clean")}
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g6" / f"r{r}.json").read_text(encoding="utf-8"))
        for c, lr in d["loop"].items():
            fp = lr.get("final_plan")
            if not fp or lr["status"] != "ok":
                out["g6"][f"r{r}/{c}"] = {"executed": False, "status": lr["status"]}
                continue
            src, exc, hdr = _case_files(g6cases[c])
            v = check_split_required(src, exc, hdr, fp)
            kinds = {X: (fp.get("edits") or {}).get(X, {}).get("kind") for X in "AB"}
            out["g6"][f"r{r}/{c}"] = {"executed": True, "verdict": "REJECT" if v else "ACCEPT", "violations": v, "kinds": kinds,
                                      "forecast_words": forecast_claim(exc),
                                      "g6_inflation_mean": (round(sum(lr["stats"][s]["full"]["drop"]["fix_both"] for s in lr["stats"]) / len(lr["stats"]), 3)
                                                            if lr.get("stats") else None)}
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g5" / f"r{r}.json").read_text(encoding="utf-8"))
        for c, lr in d["loop"].items():
            if lr.get("status") != "ok":
                continue
            src, exc, hdr = _case_files(g4.CASES[c])
            v = check_split_required(src, exc, hdr, lr["final_plan"])
            out["g5"][f"r{r}/{c}"] = {"verdict": "REJECT" if v else "ACCEPT", "forecast_words": forecast_claim(exc)}
    rej6 = [k for k, x in out["g6"].items() if x.get("verdict") == "REJECT"]
    rej5 = [k for k, x in out["g5"].items() if x["verdict"] == "REJECT"]
    out["summary"] = {"g6_executed_plans": sum(1 for x in out["g6"].values() if x["executed"]), "g6_would_reject": rej6,
                      "g5_executed_plans": len(out["g5"]), "g5_would_reject": rej5}
    _save("replay_g6", out)
    print(json.dumps(out["summary"], indent=1))
    return out


# ---------------- offline builder reference on the disguised cases ----------------
REF_FIX = {
    "A": {"kind": "split", "steps": {"split_rows": (
        "def split_rows(df, seed):\n    idx = np.arange(len(df))\n"
        "    return idx[df['epoch'].to_numpy() < 46], idx[df['epoch'].to_numpy() >= 46]\n")}},
    "B": {"kind": "fit_scope", "steps": {"tune_mtry": (
        "def tune_mtry(X, y, seed, k=10):\n    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed + 1)\n"
        "    best, best_auc = MTRY_GRID[0], -1.0\n    for m in MTRY_GRID:\n"
        "        aucs = [roc_auc_score(y[te], forest_score(fit_forest(X[tr], y[tr], seed, m), X[te])) for tr, te in cv.split(X, y)]\n"
        "        if np.mean(aucs) > best_auc:\n            best, best_auc = m, float(np.mean(aucs))\n    return best\n")}},
    "A_code_line": "    return idx, idx", "B_code_line": "    cv = StratifiedKFold(n_splits=k, shuffle=True, random_state=seed)",
}


def _summ(stats):
    ss = sorted(stats)
    return {"orig": [round(stats[s]["full"]["acc"]["orig"], 3) for s in ss],
            "fix_both": [round(stats[s]["full"]["acc"]["fix_both"], 3) for s in ss],
            "inflation": [round(stats[s]["full"]["drop"]["fix_both"], 3) for s in ss],
            "inflation_mean": round(sum(stats[s]["full"]["drop"]["fix_both"] for s in ss) / len(ss), 3),
            "ci": [[round(x, 3) for x in stats[s]["full"]["drop_ci"]["fix_both"]] for s in ss]}


def ref(args=None):
    from sandbox import factorial_stats
    plan_ = {"edits": {"A": REF_FIX["A"], "B": REF_FIX["B"]}}
    cfgs, problems, _ = guard(CASES[LEAKY], plan_, rules=())
    if problems:
        print("REF guard notes (builder reference is not gated):", problems)
    t0 = time.time()
    raw, rv = _execute(CASES[LEAKY], cfgs)
    if raw is None:
        _save("ref", {"status": "error", "problems": rv})
        print("REF ERROR", rv)
        return
    st = factorial_stats.all_seeds(raw, n_boot=N_BOOT)
    out = {"status": "ok", "case": LEAKY, "label": "OFFLINE builder reference (temporal split = the published control), not a model result",
           "summary": _summ(st), "elapsed_s": round(time.time() - t0)}
    _save("ref", out)
    print(json.dumps(out["summary"]))


# ---------------- preregistration ----------------
PREREG = """# G7 preregistration (written BEFORE any G7 live call; sha256 of this text is logged in prereg_log.jsonl)

Date written: {date} (SLT {slt}). Phase owner: builder A. Nothing below is tuned after seeing results.

## Question
Does NullLab's loop (plan, guarded structured edits, sandbox run) still find and measure a published evaluation flaw
when the source paper cannot be recalled from the material (names, columns, domain all changed)? And does executing beat
a single reading prompt (B3)?

## Cases (same rows and numbers as the G6 civil-war case, REAL-PINNED, disguised)
- civilwar_disguised (leaky): columns f01..f90, target, epoch (= year - 1944). train.py scores the model on the rows it
  was trained on (split_rows returns the same rows for fit and score). Excerpt: a FORECASTING claim in another domain
  ('supplier-failure onset in a regional supply network', disguise version 1; versions 2, 3 are rebuilt wordings).
- civilwar_disguised_clean: the same pipeline, trained on epochs 1-45, scored on epochs 46-56.
- Truth (host only, eval/g7_truth.json): published inflation +0.36 PR-AUC (Neunhoeffer and Sternberg 2019:
  0.43 apparent vs 0.07 temporal hold-out). The builder reference port measures about +0.30 (G6 ref.json).

## Contamination probe (live, before the runs; protocol fixed here)
Per disguise version v, with the model used for the runs: (P1) full agent view, "name the dataset/paper/repository if you
recognise it, else UNKNOWN"; (P2) "what real-world domain do the numeric columns measure? one line". The version PASSES iff
P1 answer contains UNKNOWN and neither answer contains any of: war, conflict, civil, countr, nation, polit, sambanis,
muchlinski, regime, democr, cold war, hegre, fearon. If it fails, rebuild with version v+1 (wording changed, same data),
up to version 3. If version 3 still fails, the case is labelled DEV-ONLY in EVAL-7.md and the failure stated.

## Rules
- SPLIT-USE-REQUIRED (agent/factorial_g7.check_split_required): if the excerpt states a forecasting / next-period use
  (words: {words}), every 'split' fix must hold rows out by time (comparison with a time-like column, sort-by-time +
  slice, TimeSeriesSplit), and unless train.py already does so, at least one 'split' fix must. Otherwise the plan is
  REJECTED, one retry carrying the rejection text, then INCONCLUSIVE (never FALSIFIED). The planner prompt is the
  unchanged G6 prompt (the rule is NOT announced in the prompt).
- Schema: the planner JSON is validated (validate_plan) before the fidelity guard; one schema retry.
- Guards from G5/G6 unchanged (static fidelity, FEATURE-REASON, SPLIT-USE, SAMPLE SIZE).
- Measurement as G6: 4 configs x seeds 42/43/44, n_boot=1000, UNPAIRED bootstrap, metric PR-AUC; measured inflation =
  claimed (orig) minus controlled (fix_both), mean over seeds; sign per seed from the 95 percent CI; repeat sign = category of >= 2 of 3 seeds.

## Runs
{n} repeats on each of the two cases, model {model_note}, temperature {temp}; per repeat B3 x 2 (single reading prompt,
baselines FACTORIAL_SYSTEM text) and the loop planner x 2 (hashed before execution), then the guarded loop.

## Hypotheses (stated before data)
H1. Without SPLIT-USE-REQUIRED the loop would repeat the G6 behaviour (random hold-out, magnitude under-estimated);
    with it, the accepted fix is temporal, so the measured inflation approaches the builder reference (about +0.30).
H2. The loop does not false-alarm on the clean pipeline (INCONCLUSIVE possible).
H3. B3 (reading only) still names the flaw and a magnitude near +0.36 on the leaky case; if so the disguise did not
    remove what B3 needs and the loop cannot claim a win from this case. B3 false alarms on the clean case are possible (G6: 3/3).

## PASS (preregistered; computed by `score`)
PASS iff all of:
 (a) direction right (repeat sign '+') on the leaky case in >= 4 of 5 repeats,
 (b) 0 false alarms (repeat sign '+') on the clean case over 5 repeats (INCONCLUSIVE is not a false alarm),
 (c) measured inflation within 0.15 of +0.36 (|mean inflation - 0.36| <= 0.15) on >= 3 of 5 leaky repeats.
Reported alongside (not acceptance): B3 gets-it / false alarms, retries, INCONCLUSIVE counts, CIs, spend, probe results.
B3 GETS IT iff leak == true AND predicted fix_both drop >= +2 points AND |drop/100 - 0.36| <= 0.15.
B3 false alarm on clean iff leak == true.
Budget: stop at an estimated USD {ceil} for this task (call estimates summed from runs_g7/live_calls_g7.jsonl).
"""


def rule(args=None, model_note="muse-spark-1.3-contributor if the API accepts it (modelcheck), else muse-spark-1.3"):
    now = time.gmtime()
    slt = time.strftime("%Y-%m-%d %H:%M", time.gmtime(calendar.timegm(now) + 5.5 * 3600))
    text = PREREG.format(date=time.strftime("%Y-%m-%d %H:%M:%SZ", now), slt=slt, words=", ".join(FORECAST_WORDS), n=N_REPEATS,
                         model_note=model_note, temp=TEMPERATURE, ceil=f"{TASK1_CEILING_USD:.2f}")
    p = out_dir() / "PREREG.md"
    if p.exists():
        print("PREREG.md already exists: NOT overwritten (preregistration is write-once)")
        return
    p.write_text(text, encoding="utf-8")
    _prereg("g7_prereg_md", {"sha256_of_text": hashlib.sha256(text.encode()).hexdigest()})
    srcs = {x: hashlib.sha256((ROOT / x).read_bytes()).hexdigest() for x in
            ("agent/factorial_g7.py", "agent/llm.py", "agent/fidelity.py", "agent/factorial_g5.py", "agent/factorial_g6.py",
             "eval/build_g7.py", "eval/g7_truth.json", "sandbox/factorial_stats.py", "sandbox/run_factorial.py")}
    _prereg("g7_source_hashes", srcs)
    _prereg("g7_prompts", {"planner_system": SYSTEM, "b3_system": B3_SYSTEM})
    print("sha256(PREREG.md) =", hashlib.sha256(text.encode()).hexdigest())


def freeze(args=None):
    """Log the final source hashes and the frozen agent views (run after the probes, before the repeats)."""
    import g4
    _prereg("g7_source_hashes_at_freeze", {x: hashlib.sha256((ROOT / x).read_bytes()).hexdigest() for x in
            ("agent/factorial_g7.py", "agent/llm.py", "agent/fidelity.py", "eval/build_g7.py", "eval/g7_truth.json")})
    for c, d in CASES.items():
        _prereg("agent_view_frozen", g4._hashes(d), c)


# ---------------- probes ----------------
CONTAM_WORDS = ("war", "conflict", "civil", "countr", "nation", "polit", "sambanis", "muchlinski", "regime", "democr", "cold war",
                "hegre", "fearon")


def probe_pass(p1, p2):
    low = (p1 + " " + p2).lower()
    hits = [w for w in CONTAM_WORDS if w in low]
    return ("UNKNOWN" in p1.upper()) and not hits, hits


def modelcheck(args):
    m = args[0]
    out = {"model": m, "temperature": TEMPERATURE}
    try:
        ans = llm.live_complete("Answer in one word.", "Reply with the single word OK.", est_usd=EST["check"], tag="g7_modelcheck",
                                role="probe", model=m, temperature=TEMPERATURE)
        out.update({"serves_chat": True, "answer": ans[:80]})
    except Exception as e:  # noqa: BLE001
        out.update({"serves_chat": False, "error": repr(e)[:400]})
    _save("modelcheck_" + re.sub(r"[^\w.-]", "_", m), out)
    print(json.dumps(out))


def probe(args):
    v = args[0]
    case = CASES[LEAKY]
    p1 = llm.live_complete("Answer in one short line.", "If you recognise the dataset, paper or repository this material comes from, "
                           "name it; otherwise say UNKNOWN.\n\n" + agent_view(case), est_usd=EST["probe"], tag="g7_probe1",
                           role="probe", temperature=0)
    p2 = llm.live_complete("Answer in one short line.", "What real-world domain do the numeric columns f01..f90 of this data most "
                           "likely measure? Give your single best guess.\n\n" + agent_view(case), est_usd=EST["probe"], tag="g7_probe2",
                           role="probe", temperature=0)
    ok, hits = probe_pass(p1, p2)
    out = {"disguise_version": int(v), "model": llm.model_for("probe"), "P1_recognise_or_UNKNOWN": p1[:300], "P2_domain_guess": p2[:300],
           "pass": ok, "contamination_words_hit": hits, "view_sha256": {n: hashlib.sha256((case / n).read_bytes()).hexdigest() for n in ("train.py", "excerpt.md", "data.csv")}}
    _save(f"probe_v{v}", out)
    print(json.dumps(out, indent=1))


# ---------------- Task 1 runs ----------------
def _parallel(fn, items, workers=4):
    res = {}
    with ThreadPoolExecutor(workers) as ex:
        futs = {k: ex.submit(fn, *a) for k, a in items.items()}
        for k, f in futs.items():
            try:
                res[k] = f.result()
            except Exception as e:  # noqa: BLE001
                res[k] = e
    return res


def run(args):
    reps = [int(a) for a in args]
    model = llm.model_for()
    res = {r: _load(f"r{r}", {"repeat": f"g7-r{r}", "model": model, "temperature": TEMPERATURE, "b3": {}, "plan": {}, "loop": {}}) for r in reps}
    todo = [(r, c) for r in reps for c in CASES]
    need_b3 = [(r, c) for r, c in todo if c not in res[r]["b3"] or "error" in res[r]["b3"][c]]
    need_pl = [(r, c) for r, c in todo if c not in res[r]["plan"] or "error" in res[r]["plan"][c]]
    if not budget_ok(len(need_b3) * EST["b3"] + len(need_pl) * EST["plan"]):
        return
    for kind, items, fn in (("b3", need_b3, lambda r, c: b3(CASES[c], f"g7-r{r}")),
                            ("plan", need_pl, lambda r, c: plan(CASES[c], f"g7-r{r}"))):
        for (r, c), v in _parallel(fn, {k: k for k in items}).items():
            if isinstance(v, Exception):
                res[r][kind][c] = {"error": repr(v)[:600]}
                print(f"r{r} {c} {kind} ERROR", repr(v)[:300], flush=True)
                continue
            if kind == "b3":
                ans, raw = v
                rec = _prereg("b3_single_prompt", {k: ans.get(k) for k in ("leak", "A", "B", "predicted_drop_pp", "culprit_ranking")}, c, f"g7-r{r}")
                res[r]["b3"][c] = {"ans": ans, "raw": raw, "prereg_sha256": rec["sha256"]}
            else:
                p, raw, info = v
                rec = _prereg("loop_planner", {k: p.get(k) for k in ("A", "B", "edits", "predicted_drop_pp", "culprit_ranking")}, c, f"g7-r{r}")
                res[r]["plan"][c] = {"plan": p, "raw": raw, "schema": info, "prereg_sha256": rec["sha256"]}
        for r in reps:
            _save(f"r{r}", res[r])
    todo_loop = [(r, c) for r, c in todo if c not in res[r]["loop"] and "plan" in res[r]["plan"].get(c, {})]

    def one(r, c):
        t0 = time.time()
        lr = loop_case(CASES[c], f"g7-r{r}", res[r]["plan"][c], model=model)
        import g4
        sgn = g4.case_sign(lr["stats"]) if lr["status"] == "ok" else ("INCONCLUSIVE", None)
        print(f"g7-r{r} {c:26s} {lr['status']} retries={lr['retries']} sign={sgn} {time.time() - t0:.0f}s", flush=True)
        return lr

    for (r, c), lr in _parallel(one, {k: k for k in todo_loop}, workers=3).items():
        res[r]["loop"][c] = {"status": "INCONCLUSIVE", "retries": 0, "reason": [repr(lr)[:400]]} if isinstance(lr, Exception) else lr
        _save(f"r{r}", res[r])


def score(args=None):
    import numpy as np
    import g4
    rows = {LEAKY: {}, CLEAN: {}}
    for r in range(1, N_REPEATS + 1):
        d = _load(f"r{r}")
        if not d:
            continue
        for c in CASES:
            lr, row = d["loop"].get(c), {}
            if lr is None:
                row["loop"] = {"sign": "NOT RUN"}
            elif lr["status"] != "ok":
                row["loop"] = {"sign": "INCONCLUSIVE", "retries": lr["retries"], "reason": lr.get("reason")}
            else:
                st = lr["stats"]
                s, cats = g4.case_sign(st)
                infl = [st[sd]["full"]["drop"]["fix_both"] for sd in sorted(st)]
                fp = lr["final_plan"]
                row["loop"] = {"sign": s, "per_seed": cats, "retries": lr["retries"],
                               "claimed": [round(st[sd]["full"]["acc"]["orig"], 3) for sd in sorted(st)],
                               "controlled": [round(st[sd]["full"]["acc"]["fix_both"], 3) for sd in sorted(st)],
                               "inflation_mean": round(float(np.mean(infl)), 3), "inflation_per_seed": [round(x, 3) for x in infl],
                               "inflation_ci": [[round(x, 3) for x in st[sd]["full"]["drop_ci"]["fix_both"]] for sd in sorted(st)],
                               "kinds": {X: (fp.get("edits") or {}).get(X, {}).get("kind") for X in "AB"},
                               "A": fp.get("A"), "B": fp.get("B"), "planner_pred_pp": fp.get("predicted_drop_pp"),
                               "schema_retry": d["plan"][c].get("schema", {}).get("schema_retry")}
            lo = row["loop"]
            if c == LEAKY:
                lo["magnitude_ok"] = "inflation_mean" in lo and abs(lo["inflation_mean"] - PUBLISHED_INFLATION) <= TOL
                lo["direction_ok"] = lo["sign"] == "+"
                lo["published_in_ci_seeds"] = sum(ci[0] <= PUBLISHED_INFLATION <= ci[1] for ci in lo.get("inflation_ci", []))
            else:
                lo["false_alarm"] = lo["sign"] == "+"
            b = d["b3"].get(c, {})
            if "ans" in b:
                a = b["ans"]
                fb = float(a["predicted_drop_pp"]["fix_both"])
                bb = {"leak": bool(a.get("leak")), "fix_both_pp": fb, "A": a.get("A"), "B": a.get("B")}
                if c == LEAKY:
                    bb["gets_it"] = bb["leak"] and fb >= 2 and abs(fb / 100 - PUBLISHED_INFLATION) <= TOL
                else:
                    bb["false_alarm"] = bb["leak"]
                row["b3"] = bb
            else:
                row["b3"] = {"error": b.get("error", "not run")}
            rows[c][f"r{r}"] = row
    L, C = rows[LEAKY], rows[CLEAN]
    n = len(L)
    acc = {"n_leaky_repeats": n, "n_clean_repeats": len(C),
           "a_direction_right": sum(bool(x["loop"].get("direction_ok")) for x in L.values()),
           "b_clean_false_alarms": sum(bool(x["loop"].get("false_alarm")) for x in C.values()),
           "c_magnitude_within_0.15": sum(bool(x["loop"].get("magnitude_ok")) for x in L.values()),
           "leaky_inconclusive": sum(x["loop"]["sign"] == "INCONCLUSIVE" for x in L.values()),
           "clean_inconclusive": sum(x["loop"]["sign"] == "INCONCLUSIVE" for x in C.values()),
           "retries": sum(x["loop"].get("retries", 0) for x in list(L.values()) + list(C.values())),
           "b3_gets_it_leaky": sum(bool(x["b3"].get("gets_it")) for x in L.values()),
           "b3_false_alarms_clean": sum(bool(x["b3"].get("false_alarm")) for x in C.values())}
    acc["PASS"] = n == N_REPEATS and len(C) == N_REPEATS and acc["a_direction_right"] >= 4 and acc["b_clean_false_alarms"] == 0 \
        and acc["c_magnitude_within_0.15"] >= 3
    out = {"acceptance": acc, "cases": rows, "spend_estimate_usd": round(my_spent(), 2)}
    _save("score", out)
    print(json.dumps(acc, indent=1))
    for c in rows:
        for r, x in rows[c].items():
            lo, b = x["loop"], x["b3"]
            print(f"{c:26s} {r} loop {lo['sign']:12s} {lo.get('per_seed')} infl={lo.get('inflation_mean')} kinds={lo.get('kinds')} "
                  f"ret={lo.get('retries')} | B3 leak={b.get('leak')} pp={b.get('fix_both_pp')} gets={b.get('gets_it', '-')} FA={b.get('false_alarm', '-')}")


# ---------------- Task 2: muse-wonder as planner on the 8 synthetic G5 cases ----------------
def wonder(args=None):
    """One repeat of the 8 G5 cases with the planner model set by --model (default here: muse-wonder-1.0)."""
    import g4
    model = llm.model_for("planner")
    tmp_cases = g4.CASES
    res = _load("wonder", {"model": model, "temperature": 0, "plan": {}, "loop": {}})
    rid = "g7-wonder"
    todo = [c for c in tmp_cases if c not in res["plan"] or "error" in res["plan"][c]]
    if not budget_ok(len(todo) * EST["plan"], TOTAL_CEILING_USD):
        return
    for c, v in _parallel(lambda c: plan(tmp_cases[c], rid, system=factorial_g5.SYSTEM, model=model, temperature=0, tag="g7_wonder_planner"),
                          {c: (c,) for c in todo}).items():
        if isinstance(v, Exception):
            res["plan"][c] = {"error": repr(v)[:600]}
            print(c, "PLAN ERROR", repr(v)[:300], flush=True)
            continue
        p, raw, info = v
        res["plan"][c] = {"plan": p, "raw": raw, "schema": info}
    _save("wonder", res)

    def one(c):
        return loop_case(tmp_cases[c], rid, res["plan"][c], rules=(), model=model, temperature=0, system=factorial_g5.SYSTEM)

    todo_loop = [c for c in tmp_cases if c not in res["loop"] and "plan" in res["plan"].get(c, {})]
    for c, lr in _parallel(one, {c: (c,) for c in todo_loop}, workers=3).items():
        res["loop"][c] = {"status": "INCONCLUSIVE", "retries": 0, "reason": [repr(lr)[:400]]} if isinstance(lr, Exception) else lr
        sgn = g4.case_sign(res["loop"][c]["stats"]) if res["loop"][c]["status"] == "ok" else ("INCONCLUSIVE", None)
        print(f"wonder {c:26s} {res['loop'][c]['status']} retries={res['loop'][c]['retries']} sign={sgn}", flush=True)
        _save("wonder", res)


def spark5(args=None):
    """Offline: schema-validity, guard acceptance and sign per case for the saved spark G5 runs (runs_g5/r1..r3)."""
    import g4
    out = {}
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g5" / f"r{r}.json").read_text(encoding="utf-8"))
        for c, pr in d["plan"].items():
            if "plan" not in pr:
                continue
            first_valid = not validate_plan(pr["plan"])
            lr = d["loop"].get(c, {})
            sign = g4.case_sign(lr["stats"])[0] if lr.get("status") == "ok" else "INCONCLUSIVE"
            cfgs, problems, _ = guard(g4.CASES[c], pr["plan"], rules=())
            out[f"r{r}/{c}"] = {"schema_valid": first_valid, "guard_accept_first_plan": not problems,
                                "sign": sign, "retries": lr.get("retries")}
    _save("spark_g5_metrics", out)
    print(json.dumps({"n": len(out), "schema_valid": sum(x["schema_valid"] for x in out.values()),
                      "guard_accept_first": sum(x["guard_accept_first_plan"] for x in out.values())}))


TRUTH_SIGN_G5 = {"g4_freight_delay": "-", "g4_pump_inspection": "+", "g4_crop_irrigation": "0", "g4_assay_replicates": "+",
                 "clean_control": "0", "clean_group_correct": "0", "clean_wine_correct": "0", "g4_visit_history_clean": "0"}  # g5.py scoring rule
HARD_G5 = ("g4_freight_delay", "g4_pump_inspection", "g4_crop_irrigation", "g4_assay_replicates")


def _side(plans, loops, validate=True):
    import g4
    rows = {}
    for key, pr in plans.items():
        c = key.split("/")[-1]
        lr = loops.get(key, {})
        p = pr.get("plan")
        first_ok = None
        if lr.get("log"):
            first_ok = lr["log"][1]["verdict"] == "ACCEPT"
        sign = g4.case_sign(lr["stats"])[0] if lr.get("status") == "ok" else "INCONCLUSIVE"
        rows[key] = {"case": c, "schema_valid": (not validate_plan(p)) if p else False, "guard_accept_first_plan": first_ok,
                     "sign": sign, "truth": TRUTH_SIGN_G5[c], "retries": lr.get("retries"),
                     "keys": sorted(set(p) - {"both_overrides"}) if p else None}
    return rows


def wonder_score(args=None):
    """Side by side: wonder (one repeat, this phase) vs spark (runs_g5 r1..r3, same G5 prompt and guard, temperature 0)."""
    w = _load("wonder")
    wrows = _side({c: v for c, v in w["plan"].items()}, w["loop"])
    srows = {}
    for r in (1, 2, 3):
        d = json.loads((ROOT / "runs_g5" / f"r{r}.json").read_text(encoding="utf-8"))
        srows.update(_side({f"r{r}/{c}": v for c, v in d["plan"].items() if "plan" in v}, {f"r{r}/{c}": v for c, v in d["loop"].items()}))

    def agg(rows, ref=None):
        v = list(rows.values())
        hard = [x for x in v if x["case"] in HARD_G5]
        cln = [x for x in v if x["case"] not in HARD_G5]
        return {"n_plans": len(v), "schema_valid": sum(x["schema_valid"] for x in v),
                "guard_accepted_first_plan": sum(bool(x["guard_accept_first_plan"]) for x in v),
                "retries": sum(x["retries"] or 0 for x in v),
                "hard_n": len(hard), "hard_sign_correct": sum(x["sign"] == x["truth"] for x in hard),
                "hard_inconclusive": sum(x["sign"] == "INCONCLUSIVE" for x in hard),
                "clean_n": len(cln), "clean_false_alarms": sum(x["sign"] == "+" for x in cln),
                "clean_inconclusive": sum(x["sign"] == "INCONCLUSIVE" for x in cln)}
    spark_keys = {tuple(x["keys"]) for x in srows.values() if x["keys"]}
    same_keys = sum(tuple(x["keys"] or ()) in spark_keys for x in wrows.values())
    spark_r1 = {x["case"]: x["sign"] for k, x in srows.items() if k.startswith("r1/")}
    out = {"wonder_model": w.get("model"), "wonder": agg(wrows), "spark_g5_r1_r3": agg(srows),
           "verdict_keys_identical_to_spark": f"{same_keys}/{len(wrows)}",
           "sign_equals_spark_r1": f"{sum(x['sign'] == spark_r1.get(x['case']) for x in wrows.values())}/{len(wrows)}",
           "per_case_wonder": wrows, "note": "'verdict keys identical' = the plan JSON has the key set that spark's plans have, ignoring the optional 'both_overrides'; "
                                              "spark side = runs_g5 r1..r3 (3 repeats x 8 cases); wonder = 1 repeat x 8 cases (n=8)."}
    _save("wonder_score", out)
    print(json.dumps({k: v for k, v in out.items() if k != "per_case_wonder"}, indent=1))


STAGES = {"rule": rule, "replay6": replay6, "ref": ref, "modelcheck": modelcheck, "probe": probe, "freeze": freeze, "run": run,
          "score": score, "wonder": wonder, "wonder_score": wonder_score, "spark5": spark5}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="sets NULLLAB_MODEL for this process")
    ap.add_argument("--temp", type=float, help="override the repeat temperature (default 0.7)")
    ap.add_argument("--out", help="output dir (required with --replay; default runs_g7)")
    ap.add_argument("--replay", help="serve recorded replies from this traces jsonl (zero API calls)")
    ap.add_argument("stage")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    if a.replay and not a.out:
        raise SystemExit("--replay requires --out DIR (a replay must not write into runs_g7)")
    os.environ["NULLLAB_PHASE"] = "g7"
    if a.model:
        os.environ["NULLLAB_MODEL"] = a.model
    if a.temp is not None:
        global TEMPERATURE
        TEMPERATURE = a.temp
    if a.out:
        os.environ["NULLLAB_G7_OUT"] = a.out
    if a.replay:
        if not a.out:
            raise SystemExit("--replay requires --out DIR (a replay must not write into runs_g7)")
        print("replay: loaded", llm.set_replay(a.replay), "recorded replies; no API call will be made")
    STAGES[a.stage](a.args)


if __name__ == "__main__":
    main()
