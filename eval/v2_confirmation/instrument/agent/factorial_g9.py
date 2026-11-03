"""G9 live runner: the FIXED INSTRUMENT (typed edit DSL + up-front contract + behavioural guard + robust transport + smoke + cached sandbox)
on the disguised EHG pair (5 repeats) and, as a same-instrument regression check, the disguised civil-war pair (3 repeats).
Preregistration: docs/EVAL-13-G9-PREREG.md. Instrument description: docs/EVAL-12-G9-INSTRUMENT.md and docs/EVAL-12-G9-DSL.md.

Imported and NOT edited: agent/llm.py, factorial_g5/g7/g8, fidelity (not used for judging), transport, smoke, cached_exec, edit_dsl,
contract_g9, guard_g9 and the sandbox. New here: the DSL planner prompt, the pipeline (plan, contract and behavioural guard, smoke,
cached sandbox, statistics), the case groups, the call log, the caps, the acceptance numbers, the freeze/verify stages.

Pipeline per case (planner-side calls: 1 plan + at most one repair of each kind, so at most 5):
  plan -> parse (bad_json repair) -> check_plan(runtime=True) = static contract + compile + behavioural guard (guard repair)
       -> smoke on a 200-row copy (smoke repair, definitive failures only) -> cached sandbox, 4 configs x seeds 42/43/44 (crash repair)
       -> bootstrap statistics exactly as G8 (n_boot 1000).
verdict 'no_flaw' is a legal answer: no sandbox run, sign '0'. A plan with k = 1 factor is measured as ONE fix (fix_all); the frozen 3-config
sandbox is fed the same source three times (plumbing, not a factorial). k = 3 is measured on fix_all only (the scored quantity).
A transport retry is not a repair and not a harness failure; only an exhausted transport ends a case as harness failure api_error.

Driver:  .venv/Scripts/python.exe -m agent.factorial_g9 [--model M] [--out DIR] <stage> [args]
Stages:  project | hashes | freeze | verify | run <r>... | score | usage      (`run` refuses unless `verify` prints VERIFY OK)

Hash rule: sha256 of the bytes with CRLF replaced by LF; a JSON payload is hashed as sha256(json.dumps(payload, sort_keys=True))."""
import argparse
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import factorial_g5, factorial_g7 as g7, factorial_g8 as g8, llm  # noqa: E402
from agent import cached_exec, contract_g9, edit_dsl, smoke, transport  # noqa: E402
from agent.factorial import agent_view  # noqa: E402

EHG_LEAKY, EHG_CLEAN = "ehg_disguised", "ehg_disguised_clean"
CW_LEAKY, CW_CLEAN = g7.LEAKY, g7.CLEAN              # civilwar_disguised, civilwar_disguised_clean
GROUPS = {"ehg": (EHG_LEAKY, EHG_CLEAN), "civilwar": (CW_LEAKY, CW_CLEAN)}
CASES = {c: ROOT / "real" / c for g in GROUPS.values() for c in g}
REPEATS = {"ehg": 5, "civilwar": 3}
MAX_REPEAT = max(REPEATS.values())
TEMPERATURE = 0.7
DEFAULT_MODEL = g8.DEFAULT_MODEL                     # muse-spark-1.3-contributor
SEEDS, N_BOOT = g8.SEEDS, g8.N_BOOT                  # (42, 43, 44), 1000: as G8
REPAIR_KINDS = ("bad_json", "guard", "smoke", "crash")
CASE_CALL_CAP = 1 + len(REPAIR_KINDS)                # 5 planner-side calls per case
N_CASES = sum(2 * n for n in REPEATS.values())       # 16
PLANNER_CALL_CAP = 90                                # planner-side calls of the whole run (counted on our own log)
TOTAL_CALL_CAP = PLANNER_CALL_CAP + N_CASES          # + one B3 call per case; enforced by llm.MAX_G8_CALLS on OUR log
EST = {"b3": 0.08, "plan": 0.12, "repair": 0.12}     # USD per call, estimates (the contract makes the prompt longer than G8's 0.10)
CEILING_USD = float(os.environ.get("NULLLAB_G9_CEILING", "12.00"))
EXEC_TIMEOUT_S = 1500
REFERENCE = {"ehg": 0.430, "civilwar": g7.PUBLISHED_INFLATION}   # ehg: offline reference measurement of this port; civilwar: G7/G8 target
PUBLISHED_RANGE_EHG = (0.36, 0.49)
TOL = 0.15
ACCEPT = {"ehg": {"direction_min": 4, "false_alarm_max": 0, "magnitude_min": 3},
          "civilwar": {"direction_min": 2, "false_alarm_max": 0}}
HARNESS_TARGET = 0
STDERR_LINES, STDERR_CHARS, BADREPLY_CHARS = g8.STDERR_LINES, g8.STDERR_CHARS, g8.BADREPLY_CHARS
FROZEN_OPSPEC_SHA256 = "420a97b129734bc690153ff2122592c82eb4f1acf851eeac8aef94fa2834a320"   # docs/EVAL-12-G9-DSL.md section 2
FROZEN_CONTRACT_SHA256 = "2e68292243af1d4ebab3fed2fd75ee494f7b5ec8fa33acef2a363ddfd7ac0284"  # docs/EVAL-12-G9-DSL.md section 6
DOC = "docs/EVAL-13-G9-PREREG.md"
CODE_FILES = ("agent/factorial_g9.py", "agent/transport.py", "agent/smoke.py", "agent/cached_exec.py", "agent/edit_dsl.py", "agent/guard_g9.py",
              "agent/contract_g9.py", "agent/llm.py", "agent/factorial_g8.py", "agent/factorial_g7.py", "agent/factorial_g5.py",
              "agent/factorial_g6.py", "agent/factorial.py", "agent/fidelity.py", "g4.py", "sandbox/executor.py", "sandbox/run.py",
              "sandbox/run_factorial.py", "sandbox/factorial_stats.py", "eval/build_g8_cases.py", "eval/g8_truth.json", "baselines/rulefix.py")
_IO = threading.Lock()

# ---------------- prompts ----------------
SYSTEM = (
    "You are a scientific adversary auditing how a machine-learning claim was evaluated. Read the claim excerpt, the training script "
    "(train.py) and the data head. Decide whether the reported score is higher than the claim's intended use would see because of a flaw "
    "in how the evaluation is built. You do not write code: you name ops from a fixed list and the harness compiles and checks them.\n\n"
    "THE CONTRACT (everything the harness enforces, stated up front):\n"
    + contract_g9.contract_text() +
    "\n\nHOW THIS RUN WORKS: you have no tool access, so you cannot call check_plan. The harness calls check_plan on your answer "
    "(structure, parameters, steps, columns, compile, then a behavioural check that runs every config once); if it rejects, you see the "
    "reasons once and may send one corrected plan. Afterwards the harness measures the original and each fixed config on the real "
    "data with three seeds. Before anything runs, commit your prediction: `predicted_drop_pp` is how far the metric that train.py reports "
    "falls under each fix, in percentage points of its 0 to 1 scale (0.20 on that scale is 20 pp; positive = the score falls). "
    "If the pipeline is already clean, say so with verdict 'no_flaw' and give the reason. Return ONLY the JSON object of the plan schema "
    "(no markdown, no commentary).")

B3_SYSTEM = g8.B3_SYSTEM   # unchanged single-prompt reading baseline, same agent view


def user_msg(case_dir, rid):
    return factorial_g5.user_msg(case_dir, rid)     # excerpt + train.py + data head + editable steps + repeat id (no truth anywhere)


# ---------------- hashing ----------------
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
    return {"planner_system_sha256": sha_text(SYSTEM), "b3_system_sha256": sha_text(B3_SYSTEM),
            "contract_sha256": contract_g9.contract_sha256(), "opspec_sha256": edit_dsl.spec_sha256(),
            "bundle_sha256": sha_obj({"planner_system": SYSTEM, "b3_system": B3_SYSTEM})}


def rules_payload():
    return {"repeats": REPEATS, "cases": {g: list(c) for g, c in GROUPS.items()}, "temperature": TEMPERATURE, "seeds": list(SEEDS), "n_boot": N_BOOT,
            "repair_kinds": list(REPAIR_KINDS), "case_call_cap": CASE_CALL_CAP, "planner_call_cap": PLANNER_CALL_CAP, "total_call_cap": TOTAL_CALL_CAP,
            "est_usd": EST, "ceiling_usd": CEILING_USD, "reference": REFERENCE, "published_range_ehg": list(PUBLISHED_RANGE_EHG), "tolerance": TOL,
            "acceptance": ACCEPT, "harness_target_max": HARNESS_TARGET, "exec_timeout_s": EXEC_TIMEOUT_S,
            "transport": transport.DEFAULTS, "smoke": {"rows": smoke.SMOKE_ROWS, "timeout_s": smoke.SMOKE_TIMEOUT_S},
            "harness_inconclusive": "counted in the denominator as not-met; never a false alarm, never a no-effect"}


def view_hashes():
    out = {}
    for c, d in CASES.items():
        out[c] = {"files_lf": {n: sha_file(d / n) for n in ("train.py", "data.csv", "excerpt.md")},
                  "agent_view_text_sha256": sha_text(agent_view(d)), "planner_user_msg_sha256": sha_text(user_msg(d, "RID")),
                  "forecast_words_in_excerpt": contract_g9.forecast_claim((d / "excerpt.md").read_text(encoding="utf-8"))}
    return out


def all_hashes():
    return {"code": code_hashes(), "prompts": prompt_hashes(), "rules": {"payload": rules_payload(), "sha256": sha_obj(rules_payload())},
            "agent_views": view_hashes()}


# ---------------- paths / environment ----------------
def out_dir():
    d = Path(os.environ.get("NULLLAB_G9_OUT") or ROOT / "runs_g9")
    d.mkdir(parents=True, exist_ok=True)
    return d


def configure():
    """Point the llm/transport env-driven paths at OUR directory and set our caps. Refuses any path under runs_g8, runs_ehg or runs_g7."""
    d = out_dir()
    os.environ["NULLLAB_PHASE"] = "g8"          # llm.py has two phase switches; the g8 one gives a per-run log and cap. Paths below are G9's own.
    os.environ["NULLLAB_G8_OUT"] = str(d)
    os.environ["NULLLAB_G8_LOG"] = str(d / "live_calls_g9.jsonl")
    os.environ["NULLLAB_TRACES"] = str(d / "traces.jsonl")
    llm.MAX_G8_CALLS = TOTAL_CALL_CAP
    g8.CEILING_USD = CEILING_USD
    for name in ("runs_g8", "runs_ehg", "runs_g7"):
        forbidden = (ROOT / name).resolve()
        for p in (d, llm.g8_log(), llm.trace_file()):
            if forbidden in Path(p).resolve().parents or Path(p).resolve() == forbidden:
                raise SystemExit(f"refusing: {p} is under {name}")
    return d


def _prereg(kind, payload, case=None):
    rec = {"kind": kind, "case": case, "model": llm.model_for(), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "normalisation": "CRLF->LF before hashing", "payload": payload, "sha256": sha_obj(payload)}
    with _IO, (out_dir() / "prereg_log.jsonl").open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _save(name, obj):
    with _IO:
        (out_dir() / f"{name}.json").write_text(json.dumps(obj, indent=1), encoding="utf-8", newline="\n")


def _load(name, default=None):
    p = out_dir() / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def install_instruments():
    """Process-wide rebinding for THIS driver process only: llm.live_complete_ex -> transport (deadlines, retries, same gate and logs)."""
    transport.install()


# ---------------- spend accounting (our own log; retries counted conservatively) ----------------
def _est_for(role):
    return EST["b3"] if role == "b3" else EST["plan"]


def _read_jsonl(p):
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def my_spent():
    """Estimated USD of this run: every attempt logged before its request + one more estimate per transport retry record (an attempt that may have
    been billed twice). Estimates, not billing."""
    log = _read_jsonl(llm.g8_log())
    s = sum(r.get("est_usd", 0) for r in log)
    for r in _read_jsonl(transport.transport_log()):
        s += _est_for(r.get("role"))
    return s


def planner_calls_made():
    return sum(1 for r in _read_jsonl(llm.g8_log()) if str(r.get("role", "")).startswith("planner"))


def projected(n_cases=N_CASES):
    floor = n_cases * (EST["b3"] + EST["plan"])
    worst = floor + n_cases * len(REPAIR_KINDS) * EST["repair"]
    return {"cases": n_cases, "floor_usd": round(floor, 2), "worst_case_usd": round(worst, 2),
            "worst_case_every_call_retried_once_usd": round(2 * worst, 2), "ceiling_usd": CEILING_USD,
            "max_planner_calls_per_case": CASE_CALL_CAP, "max_planner_calls_total": n_cases * CASE_CALL_CAP,
            "planner_call_cap": PLANNER_CALL_CAP, "max_live_calls_total": n_cases * (1 + CASE_CALL_CAP), "total_call_cap": TOTAL_CALL_CAP,
            "already_spent_est_usd": round(my_spent(), 2), "within_planner_cap": n_cases * CASE_CALL_CAP <= PLANNER_CALL_CAP,
            "within_ceiling": worst <= CEILING_USD}


def print_projection(n_cases):
    pj = projected(n_cases)
    print(f"PROJECTED SPEND (estimates, not billing): floor ${pj['floor_usd']:.2f} (no repairs), WORST CASE ${pj['worst_case_usd']:.2f} "
          f"({pj['cases']} cases x (1 B3 + {pj['max_planner_calls_per_case']} planner calls); transport retries are counted by the live gate "
          f"and would add to it; ceiling ${pj['ceiling_usd']:.2f}; already spent est ${pj['already_spent_est_usd']:.2f}; "
          f"planner-side cap {PLANNER_CALL_CAP}, all-calls cap {TOTAL_CALL_CAP})", flush=True)
    return pj


# ---------------- per-case budget: every planner-side call goes through call() ----------------
class Budget9:
    def __init__(self, cap=CASE_CALL_CAP):
        self.cap, self.used, self.calls = cap, set(), []

    def take(self, kind):
        if kind in self.used:
            raise g8.HarnessFailure(kind, "its one repair attempt was already used")
        self.used.add(kind)

    def call(self, kind, system, msg, tag, model, temperature):
        if len(self.calls) >= self.cap:
            raise g8.HarnessFailure("call_cap", f"{self.cap} planner-side calls already made for this case (next would be {kind})")
        if not llm.replaying():
            if planner_calls_made() >= PLANNER_CALL_CAP:
                raise g8.HarnessFailure("call_cap", f"run-wide planner-side cap {PLANNER_CALL_CAP} reached")
            if my_spent() + EST["repair"] > CEILING_USD:
                raise g8.HarnessFailure("budget", f"spend ceiling ${CEILING_USD:.2f} reached")
        est = EST["plan"] if kind == "plan" else EST["repair"]
        raw, usage = llm.live_complete_ex(system, msg, est_usd=est, tag=tag, role="planner" if kind == "plan" else "planner_retry",
                                          model=model, temperature=TEMPERATURE if temperature is None else temperature)
        info = transport.last_info()
        self.calls.append({"kind": kind, "tag": tag, "est_usd": est, "usage": usage or {}, "real_total_tokens": (usage or {}).get("total_tokens"),
                           "reply_len": len(raw), "transport_attempts": info.get("attempts"), "transport_retries": len(info.get("retries") or [])})
        return raw


def _parse(raw):
    try:
        p = llm.parse_json(raw)
    except Exception as e:  # noqa: BLE001
        return None, [f"reply is not parseable JSON: {e!r}"[:240]]
    if not isinstance(p, dict):
        return None, ["reply JSON is not an object"]
    return p, []


def _bad_json_msg(base, raw, problems):
    return (base + "\n\nYOUR PREVIOUS REPLY WAS NOT USABLE:\n- " + "\n- ".join(problems) + "\n\nYOUR PREVIOUS REPLY (may be cut off):\n" +
            raw[:BADREPLY_CHARS] + "\n\nReturn ONLY the complete corrected JSON object (no markdown, no commentary) with the plan schema.")


def _get_plan(bud, kind, msg, tag, model, temperature):
    raw = bud.call(kind, SYSTEM, msg, tag, model, temperature)
    p, bad = _parse(raw)
    if bad:
        bud.take("bad_json")
        raw = bud.call("bad_json", SYSTEM, _bad_json_msg(msg, raw, bad), tag + "_json_repair", model, temperature)
        p, bad = _parse(raw)
        if bad:
            raise g8.HarnessFailure("bad_json", "; ".join(bad))
    return p, raw


def plan_hash(p):
    return sha_obj({k: p.get(k) for k in ("verdict", "factors", "predicted_drop_pp", "culprit_ranking")})


def _fb_msg(base, prev, header, items, tail):
    return (base + "\n\nYOUR PREVIOUS PLAN:\n" + json.dumps({k: (prev or {}).get(k) for k in ("verdict", "factors", "predicted_drop_pp", "culprit_ranking", "reason")}) +
            f"\n\n{header}\n- " + "\n- ".join(items) + f"\n{tail}")


GUARD_TAIL = ("Return the corrected complete plan JSON (same schema). Change only what the rejection requires; verdict 'no_flaw' remains a legal "
              "answer if you conclude the pipeline has nothing to fix.")


def stderr_tail(text):
    return g8.stderr_tail(text)


# ---------------- sandbox / guard / smoke indirections (tests stub these) ----------------
def _run_executor(case_dir, patches):
    return cached_exec.run_factorial_cached(Path(case_dir), patches, seeds=SEEDS, timeout=EXEC_TIMEOUT_S)


def _guard(plan, case_dir):
    return contract_g9.check_plan(plan, case_dir, runtime=True)


def _smoke(case_dir, patches):
    return smoke.smoke(case_dir, patches)


def sandbox_patches(comp):
    """Sources for the frozen 3-config sandbox. k == 2: factor A, factor B, both. k == 1 or 3: fix_all three times (only fix_both is scored)."""
    c = comp["configs"]
    if comp["layout"] == "factorial" and len(c) == 3:
        return edit_dsl.legacy_sources(comp)
    s = c["fix_all"]["src"]
    return {"fix_A": s, "fix_B": s, "fix_both": s}


def guard_problems(chk):
    """Turn a check_plan result that is not ok into a list of readable problems (UNVERIFIABLE counts as not accepted, with its reason)."""
    probs = list(chk.get("problems") or [])
    rt = chk.get("runtime") or {}
    if not probs and rt:
        probs = [f"{n}: {r.get('decision')} {r.get('problems') or ''}".strip() for n, r in (rt.get("configs") or {}).items() if r.get("decision") != "ACCEPT"]
    return [str(x)[:700] for x in (probs or ["the plan was not accepted (no reason given)"])][:10]


def guard_summary(chk):
    rt = chk.get("runtime") or {}
    return {"ok": bool(chk.get("ok")), "layout": chk.get("layout"), "decision": rt.get("decision", "ACCEPT" if chk.get("ok") else "REJECT"),
            "configs": {n: r.get("decision") for n, r in (rt.get("configs") or {}).items()}, "problems": [] if chk.get("ok") else guard_problems(chk)}


# ---------------- the pipeline ----------------
def pipeline(case_dir, rid, model=None, temperature=None):
    """Returns a case record: status 'ok' (stats present, or verdict 'no_flaw') or 'INCONCLUSIVE' with harness_failure in
    bad_json|guard|smoke|crash|call_cap|budget|api_error|internal_error. Never raises on a model or harness failure."""
    from sandbox import factorial_stats
    model = model or llm.model_for("planner")
    case_dir = Path(case_dir)
    bud, log, rec = Budget9(), [], {"rid": rid, "instrument": "g9"}
    base = user_msg(case_dir, rid)
    src = (case_dir / "train.py").read_text(encoding="utf-8")
    cur = None

    def finish(kind, detail):
        rec.update({"status": "INCONCLUSIVE", "harness_failure": kind, "label": g8.label("INCONCLUSIVE", kind), "reason": [str(detail)[:900]],
                    "final_plan": cur, "log": log, "calls": bud.calls, "retries": max(len(bud.calls) - 1, 0), "repairs_used": sorted(bud.used)})
        return rec

    def stamp(kind):
        cur["mode"], cur["prereg_sha256"] = llm.mode_label("planner", model, kind), plan_hash(cur)

    try:
        cur, raw = _get_plan(bud, "plan", base, "g9_planner", model, temperature)
        stamp("")
        rec["first_plan"] = json.loads(json.dumps(cur))
        rec["first_plan_prereg"] = _prereg("loop_planner", {k: cur.get(k) for k in ("verdict", "factors", "predicted_drop_pp", "culprit_ranking")}, case_dir.name)["sha256"]
        first = True
        while True:
            try:
                chk = _guard(cur, case_dir)
            except Exception as e:  # noqa: BLE001  (a bug in the guard is a harness failure, never a model verdict)
                return finish("internal_error", f"guard raised {e!r}")
            gs = guard_summary(chk)
            log.append({"phase": "Verify", "verdict": "ACCEPT" if gs["ok"] else gs["decision"], "problems": gs["problems"][:6], "configs": gs["configs"]})
            if first:
                rec["first_plan_guard"] = {"decision": gs["decision"], "problems": gs["problems"][:6]}
                first = False
            problems, crashed = None, None
            if not gs["ok"]:
                problems, kind = gs["problems"], "guard"
            elif cur.get("verdict") == "no_flaw":
                rec.update({"status": "ok", "verdict": "no_flaw", "final_plan": cur, "log": log, "calls": bud.calls, "retries": len(bud.calls) - 1,
                            "repairs_used": sorted(bud.used), "guard": gs})
                return rec
            else:
                comp = edit_dsl.compile_plan(src, cur)
                patches = sandbox_patches(comp)
                try:
                    sv = _smoke(case_dir, patches)
                except Exception as e:  # noqa: BLE001  (the pre-flight failing is logged; it is not a verdict)
                    sv = {"ok": True, "stage": "smoke_error", "message": repr(e)[:300], "definitive": False}
                log.append({"phase": "Smoke", "ok": sv.get("ok"), "stage": sv.get("stage"), "kind": sv.get("kind"), "definitive": sv.get("definitive"),
                            "message": str(sv.get("message"))[:300], "elapsed_s": sv.get("elapsed_s")})
                if not sv.get("ok") and sv.get("definitive", True):
                    problems, kind = [sv.get("repair_text") or str(sv.get("message"))], "smoke"
                else:
                    ex = _run_executor(case_dir, patches)
                    log.append({"phase": "Act", "status": ex["status"], "cached_exec": ex.get("cached_exec")})
                    if ex["status"] != "ok":
                        tail = stderr_tail(ex.get("stderr", "")) or f"(no stderr; status={ex['status']}, timeout_s={ex.get('timeout_s')})"
                        crashed, kind = f"EXECUTION {ex['status']}:\n{tail}", "crash"
                    else:
                        raw_result = ex["result"]
                        break
            bud.take(kind)
            if kind == "crash":
                msg = _fb_msg(base, cur, "YOUR PLAN PASSED THE CONTRACT AND THE SMOKE CHECK BUT CRASHED IN THE SANDBOX. Last lines of stderr:", [crashed],
                              "Fix ONLY the cause of the crash and keep the rest of the plan. Return the corrected complete plan JSON (same schema).")
            elif kind == "smoke":
                msg = _fb_msg(base, cur, "YOUR PLAN COMPILED BUT FAILED THE PRE-FLIGHT SMOKE RUN:", problems,
                              "Return the corrected complete plan JSON (same schema). Change only what the failure requires.")
            else:
                msg = _fb_msg(base, cur, "It was REJECTED by check_plan:", problems, GUARD_TAIL)
            cur, raw = _get_plan(bud, kind, msg, f"g9_planner_{kind}_repair", model, temperature)
            stamp(f"{kind} repair")
            _prereg(f"loop_planner_{kind}_repair", {k: cur.get(k) for k in ("verdict", "factors", "predicted_drop_pp", "culprit_ranking")}, case_dir.name)
            log.append({"phase": f"Recover ({kind} repair)", "calls": len(bud.calls)})
    except g8.HarnessFailure as e:
        return finish(e.kind, e.detail)
    except (llm.LiveNotAllowed, OSError) as e:   # transport exhausted / gate refusal / empty content: harness, not a model verdict
        return finish("api_error", repr(e))
    stats = factorial_stats.all_seeds(raw_result, n_boot=N_BOOT)
    rec.update({"status": "ok", "verdict": "flaw", "metric": raw_result.get("metric", "accuracy"), "stats": stats, "final_plan": cur, "log": log,
                "calls": bud.calls, "retries": len(bud.calls) - 1, "repairs_used": sorted(bud.used), "layout": comp["layout"], "guard": gs,
                "n_factors": len(cur["factors"]),
                "sources": {n: c["src"] for n, c in comp["configs"].items()}})
    return rec


# ---------------- stages: project / hashes / freeze / verify ----------------
def project(args=None):
    configure()
    pj = projected()
    print_projection(N_CASES)
    print(json.dumps(pj))
    return pj


def hashes(args=None):
    print(json.dumps(all_hashes(), indent=1))


def freeze(args=None):
    configure()
    h = all_hashes()
    _prereg("g9_source_hashes", h["code"])
    _prereg("g9_prompts", h["prompts"])
    _prereg("g9_rules", h["rules"]["payload"])
    for c, v in h["agent_views"].items():
        _prereg("g9_agent_view_frozen", v, c)
    doc = ROOT / DOC
    _prereg("g9_prereg_doc", {"path": DOC, "sha256_lf": sha_file(doc) if doc.exists() else None})
    print("frozen ->", out_dir() / "prereg_log.jsonl")


def _last(kind, case=None):
    recs = [r for r in _read_jsonl(out_dir() / "prereg_log.jsonl") if r["kind"] == kind and r.get("case") == case]
    return recs[-1] if recs else None


def verify_problems():
    h, bad = all_hashes(), []
    if edit_dsl.spec_sha256() != FROZEN_OPSPEC_SHA256:
        bad.append("edit_dsl op spec differs from the value frozen in EVAL-12")
    if contract_g9.contract_sha256() != FROZEN_CONTRACT_SHA256:
        bad.append("contract text differs from the value frozen in EVAL-12")
    checks = [("g9_source_hashes", None, h["code"]), ("g9_prompts", None, h["prompts"]), ("g9_rules", None, h["rules"]["payload"])]
    checks += [("g9_agent_view_frozen", c, v) for c, v in h["agent_views"].items()]
    for kind, case, now in checks:
        rec = _last(kind, case)
        if rec is None:
            bad.append(f"{kind} {case or ''}: no freeze record")
        elif rec["payload"] != now or rec["sha256"] != sha_obj(now) or rec["sha256"] != sha_obj(rec["payload"]):
            diff = [k for k in now if isinstance(now, dict) and rec["payload"].get(k) != now[k]] if isinstance(rec["payload"], dict) else []
            bad.append(f"{kind} {case or ''}: differs from the freeze record {diff}")
    doc = _last("g9_prereg_doc")
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


# ---------------- live: B3 + the pipeline per case ----------------
def units_for(reps):
    """(repeat, case) pairs: the EHG pair for every repeat, the civil-war pair for repeats <= 3."""
    return [(r, c) for r in reps for g, cs in GROUPS.items() if r <= REPEATS[g] for c in cs]


def run(args):
    configure()
    bad = verify_problems()
    if bad:
        raise SystemExit("REFUSING TO RUN: freeze missing or code/prompts/views changed since freeze:\n- " + "\n- ".join(bad))
    reps = sorted({int(a) for a in args})
    if not reps or any(r < 1 or r > MAX_REPEAT for r in reps):
        raise SystemExit(f"repeats must be in 1..{MAX_REPEAT}")
    model = llm.model_for()
    install_instruments()
    res = {r: _load(f"r{r}", {"repeat": f"g9-r{r}", "model": model, "temperature": TEMPERATURE, "b3": {}, "loop": {}}) for r in reps}
    for r in reps:  # a case whose only record is an exhausted transport (no reply ever observed) selects nothing when re-run; listed, not hidden
        p = out_dir() / f"r{r}.json"
        if p.exists():
            gone = transport.forget_transport_failures(p)
            if gone:
                res[r] = _load(f"r{r}")
                _prereg("g9_transport_failure_forgotten", {"repeat": r, "cases": gone})
    todo = [(r, c) for r, c in units_for(reps) if c not in res[r]["loop"]]   # any other recorded harness failure is NOT re-rolled
    pj = print_projection(len(todo))
    if not llm.replaying() and my_spent() + pj["worst_case_usd"] > CEILING_USD:
        print(f"STOP: est spent ${my_spent():.2f} + worst case ${pj['worst_case_usd']:.2f} passes ceiling ${CEILING_USD:.2f}", flush=True)
        return
    lock = threading.Lock()

    def commit(r, section, case, value):
        with lock:
            res[r][section][case] = value
            _save(f"r{r}", res[r])

    def one(r, c):
        t0 = time.time()
        if c not in res[r]["b3"] or "error" in res[r]["b3"][c]:
            try:
                raw, usage = llm.live_complete_ex(B3_SYSTEM, agent_view(CASES[c]) + f"\n\n[repeat id: g9-r{r}]", est_usd=EST["b3"], tag="g9_b3",
                                                  role="b3", model=llm.model_for("b3"), temperature=TEMPERATURE)
                commit(r, "b3", c, {"ans": llm.parse_json(raw), "raw": raw, "usage": usage})
            except Exception as e:  # noqa: BLE001
                commit(r, "b3", c, {"error": repr(e)[:400]})
        lr = pipeline(CASES[c], f"g9-r{r}", model=model)
        print(f"g9-r{r} {c:26s} {outcome_label(lr)} calls={len(lr.get('calls', []))} {time.time() - t0:.0f}s", flush=True)
        return lr

    with ThreadPoolExecutor(3) as ex:
        futs = {ex.submit(one, *k): k for k in todo}
        for f in as_completed(futs):
            r, c = futs[f]
            try:
                lr = f.result()
            except Exception as e:  # noqa: BLE001
                lr = {"status": "INCONCLUSIVE", "harness_failure": "internal_error", "label": g8.label("INCONCLUSIVE", "internal_error"),
                      "reason": [repr(e)[:400]], "calls": [], "retries": 0}
            commit(r, "loop", c, lr)


# ---------------- scoring ----------------
def group_of(case):
    return "ehg" if case in GROUPS["ehg"] else "civilwar"


def is_leaky(case):
    return case in (EHG_LEAKY, CW_LEAKY)


def sign_of(rec):
    if rec.get("status") == "ok" and rec.get("verdict") == "no_flaw":
        return "0"
    return g8.sign_of(rec)


def outcome_label(rec):
    if rec.get("status") == "ok" and rec.get("verdict") == "no_flaw":
        return "no flaw reported (model verdict, nothing run)"
    return g8.outcome_label(rec)


def b3_row(rec_b3, case):
    if "ans" not in (rec_b3 or {}):
        return {"error": (rec_b3 or {}).get("error", "not run")}
    a = rec_b3["ans"]
    try:
        fb = float(a["predicted_drop_pp"]["fix_both"])
    except (KeyError, TypeError, ValueError):
        return {"error": "unusable B3 answer"}
    row = {"leak": bool(a.get("leak")), "fix_both_pp": fb}
    if is_leaky(case):
        row["gets_it"] = row["leak"] and fb >= 2 and abs(fb / 100 - REFERENCE[group_of(case)]) <= TOL
    else:
        row["false_alarm"] = row["leak"]
    return row


def _case_rows(records):
    import numpy as np
    rows, harness = {}, []
    for c, d in records.items():
        rows[c] = {}
        g = group_of(c)
        for r, rec in sorted(d.items()):
            row = {"label": outcome_label(rec), "sign": sign_of(rec), "calls": len(rec.get("calls", [])), "retries": rec.get("retries"),
                   "verdict": rec.get("verdict"), "n_factors": rec.get("n_factors"), "repairs_used": rec.get("repairs_used"),
                   "transport_retries": sum(x.get("transport_retries", 0) or 0 for x in rec.get("calls", [])),
                   "first_plan_guard": (rec.get("first_plan_guard") or {}).get("decision")}
            if rec.get("status") == "ok" and rec.get("verdict") != "no_flaw":
                infl = [rec["stats"][s]["full"]["drop"]["fix_both"] for s in sorted(rec["stats"])]
                row["inflation_mean"] = round(float(np.mean(infl)), 3)
                row["inflation_ci"] = [[round(x, 3) for x in rec["stats"][s]["full"]["drop_ci"]["fix_both"]] for s in sorted(rec["stats"])]
                if is_leaky(c):
                    row["magnitude_ok"] = abs(row["inflation_mean"] - REFERENCE[g]) <= TOL
                    if g == "ehg":
                        row["within_published_range"] = PUBLISHED_RANGE_EHG[0] - 0.005 <= row["inflation_mean"] <= PUBLISHED_RANGE_EHG[1] + 0.005
            elif rec.get("status") != "ok":
                harness.append({"case": c, "repeat": r, "failure": rec.get("harness_failure"), "reason": (rec.get("reason") or [""])[0][:200]})
            rows[c][r] = row
    return rows, harness


def score_cases(records, b3=None):
    """Pure. records = {case: {'r1': loop record, ...}} for all four cases. Acceptance fixed in the prereg; harness failures stay in the denominator."""
    rows, harness = _case_rows(records)
    if b3:
        for c in rows:
            for r in rows[c]:
                if r in b3.get(c, {}):
                    rows[c][r]["b3"] = b3[c][r]
    out = {"cases": rows, "harness_failures": harness}
    for g, (lk, cl) in GROUPS.items():
        n = REPEATS[g]
        L, C = rows.get(lk, {}), rows.get(cl, {})
        a = {"n_leaky": len(L), "n_clean": len(C), "denominator_each": n,
             "direction_right": sum(x["sign"] == "+" for x in L.values()),
             "clean_false_alarms": sum(x["sign"] == "+" for x in C.values()),
             "no_effect_or_no_flaw_leaky": sum(x["sign"] == "0" for x in L.values()),
             "no_effect_or_no_flaw_clean": sum(x["sign"] == "0" for x in C.values()),
             "harness_inconclusive": sum(1 for h in harness if h["case"] in (lk, cl)),
             "magnitude_within_0.15": sum(bool(x.get("magnitude_ok")) for x in L.values()),
             "reference": REFERENCE[g], "rule": ACCEPT[g]}
        a["guard_harness_failures"] = sum(1 for h in harness if h["case"] in (lk, cl) and h["failure"] == "guard")
        a["first_plan_guard_rejected"] = sum(1 for x in list(L.values()) + list(C.values()) if x.get("first_plan_guard") not in (None, "ACCEPT"))
        ok = len(L) == n and len(C) == n and a["direction_right"] >= ACCEPT[g]["direction_min"] and a["clean_false_alarms"] <= ACCEPT[g]["false_alarm_max"]
        if g == "ehg":
            ok = ok and a["magnitude_within_0.15"] >= ACCEPT[g]["magnitude_min"]
            a["within_published_range"] = sum(bool(x.get("within_published_range")) for x in L.values())
        a["PASS"] = ok
        b3s = [x["b3"] for d in (L, C) for x in d.values() if "b3" in x]
        a["b3_gets_it_leaky"] = sum(bool(x["b3"].get("gets_it")) for x in L.values() if "b3" in x)
        a["b3_false_alarms_clean"] = sum(bool(x["b3"].get("false_alarm")) for x in C.values() if "b3" in x)
        a["b3_errors"] = sum("error" in x for x in b3s)
        out[g] = a
    n_h = len(harness)
    out["overall"] = {"harness_inconclusive": n_h, "cases_scored": sum(len(v) for v in rows.values()), "cases_planned": N_CASES,
                      "harness_target_met": n_h == HARNESS_TARGET and sum(len(v) for v in rows.values()) == N_CASES,
                      "EHG_PASS": out["ehg"]["PASS"], "CIVILWAR_REGRESSION_PASS": out["civilwar"]["PASS"]}
    return out


def score(args=None):
    configure()
    recs, b3 = {c: {} for c in CASES}, {c: {} for c in CASES}
    for r in range(1, MAX_REPEAT + 1):
        d = _load(f"r{r}")
        for c in CASES:
            if d and c in d.get("loop", {}):
                recs[c][f"r{r}"] = d["loop"][c]
                b3[c][f"r{r}"] = b3_row(d.get("b3", {}).get(c), c)
    out = score_cases(recs, b3)
    out["comparison_reported_next_to_this"] = {
        "G7": "FAILED its preregistered acceptance (docs/EVAL-7.md); not merged, not re-scored",
        "G8": "civil-war pair, 5 repeats: direction 4/5, clean false alarms 0/5, inflation within 0.15 of +0.36 in 4/5, harness-INCONCLUSIVE 1/10 (api_error timeout); docs/EVAL-9-G8-RESULT.md",
        "EHG_offline_rule_baseline": "no rule fires on either EHG case, inflation 0.000, direction right 0/1, false alarms 0 (runs_ehg/rules.json, docs/EVAL-11-EHG-PREREG.md section 5)"}
    out["usage"] = usage_summary()
    out["note"] = ("inflation = claimed minus controlled metric (fix_both / fix_all), mean over seeds 42/43/44. EHG reference +0.430 (offline measurement of this port), "
                   "published range +0.36..+0.49; civil war +0.36. 'no_flaw' on a leaky case counts as direction not right, on a clean case as no false alarm.")
    _save("score", out)
    print(json.dumps({g: out[g] for g in ("ehg", "civilwar", "overall")}, indent=1))
    for h in out["harness_failures"]:
        print("HARNESS FAILURE", h)
    return out


def usage_summary():
    """Estimated USD and real tokens: from the saved case records (planner side) and the usage log (every call, B3 included)."""
    est = tok = n = 0
    for r in range(1, MAX_REPEAT + 1):
        for rec in (_load(f"r{r}") or {}).get("loop", {}).values():
            for cl in rec.get("calls", []):
                est += cl["est_usd"]
                tok += cl.get("real_total_tokens") or 0
                n += 1
    ul = _read_jsonl(llm.g8_log().with_suffix(".usage.jsonl"))
    return {"planner_side_calls_in_records": n, "planner_estimated_usd": round(est, 2), "planner_real_total_tokens": tok,
            "all_calls_in_usage_log": len(ul), "all_real_total_tokens": sum((u.get("usage") or {}).get("total_tokens", 0) for u in ul),
            "run_estimated_usd_incl_transport_retries": round(my_spent(), 2), "transport_retry_records": len(_read_jsonl(transport.transport_log()))}


STAGES = {"project": project, "hashes": hashes, "freeze": freeze, "verify": verify, "run": run, "score": score,
          "usage": lambda a=None: (configure(), print(json.dumps(usage_summary())))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--out")
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    os.environ["NULLLAB_MODEL"] = a.model or os.environ.get("NULLLAB_MODEL") or DEFAULT_MODEL
    if a.out:
        os.environ["NULLLAB_G9_OUT"] = a.out
    STAGES[a.stage](a.args)


if __name__ == "__main__":
    main()
