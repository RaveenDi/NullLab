"""G9b continuation runner: the 8 units of the G9 preregistration (docs/EVAL-13-G9-PREREG.md) that never produced an outcome, run under the
speed-fixed behavioural guard. Preregistration: docs/EVAL-15-G9B-PREREG.md. Speed fix: docs/EVAL-14-GUARD-SPEED.md.

Imports agent.factorial_g9 as g9 and does NOT edit it (nor any other file). Everything that decides what a case is (prompts, contract, DSL, guard
logic, smoke, transport, cached sandbox, pipeline, statistics, acceptance numbers) is g9's. New here: the unit list, the own run directory
runs_g9b/ (own call log, traces, freeze log, records), the caps (40 planner-side calls, USD 4.00 ceiling), per-unit admission by projection,
the cross-checks against the G9 freeze records, and the score stage that evaluates the preregistered clauses on the UNION of the 8 recorded
G9 units and the 8 G9b units (every unit labelled with the guard version that produced it).

Units (repeat, case): civilwar_disguised (leaky) 1, 2, 3; ehg_disguised 4, 5; ehg_disguised_clean 4, 5; civilwar_disguised_clean 3. The repeat id sent
to the planner is the G9 one ("g9-r<k>"), so a G9b unit is the same prompt the stalled G9 unit would have sent.
runs_g9/ is only ever READ (to refuse recorded units, to cross-check freeze records, to build the union in `score`); nothing is written there.

Driver:  .venv/Scripts/python.exe -m agent.factorial_g9b [--model M] [--out DIR] <stage> [args]
Stages:  project | hashes | freeze | verify | run [repeat ...] | score | usage      (`run` refuses unless `verify` prints VERIFY OK)

Hash rule: sha256 of the bytes with CRLF replaced by LF; a JSON payload is hashed as sha256(json.dumps(payload, sort_keys=True))."""
import argparse
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
from agent import factorial_g8 as g8, factorial_g9 as g9, llm, transport  # noqa: E402
from agent.factorial import agent_view  # noqa: E402

DOC = "docs/EVAL-15-G9B-PREREG.md"
G9_DIR = ROOT / "runs_g9"                       # READ-ONLY, ever
CHANGELOG = ROOT / "docs" / "FROZEN-CHANGELOG.json"
EHG_L, EHG_C, CW_L, CW_C = g9.EHG_LEAKY, g9.EHG_CLEAN, g9.CW_LEAKY, g9.CW_CLEAN
CASES = g9.CASES
# the 8 units that have no record in runs_g9 (repeat, case); order = start order
UNITS = [(1, CW_L), (2, CW_L), (3, CW_L), (4, EHG_L), (5, EHG_L), (4, EHG_C), (5, EHG_C), (3, CW_C)]
# the 8 units that DO have a record in runs_g9 (checked read-only; verify fails if runs_g9 differs from this)
G9_RECORDED = [(1, EHG_L), (2, EHG_L), (3, EHG_L), (1, EHG_C), (2, EHG_C), (3, EHG_C), (1, CW_C), (2, CW_C)]
ALL_UNITS = sorted(UNITS + G9_RECORDED)
N_UNITS = 16
GUARD_G9_PRE = "4a084a1c466b1e8ff53ce3da94307796dc7475c275e0fdb889888f182fa17dba"     # guard_g9.py as the G9 live run used it (15:28-15:58 SLT)
GUARD_G9B = "983d2ffe81725ae2ed4703a287b74800270034af712185e2331218e18dce79b8"        # speed-fixed guard_g9.py (docs/EVAL-14-GUARD-SPEED.md)
G9_WINDOW = "2026-11-02 15:28-15:58 SLT (09:58-10:28 UTC)"

TEMPERATURE = g9.TEMPERATURE
DEFAULT_MODEL = g9.DEFAULT_MODEL
EST = dict(g9.EST)
CASE_CALL_CAP = g9.CASE_CALL_CAP                 # 5 planner-side calls per case
PLANNER_CALL_CAP = 40                            # planner-side calls of the whole G9b run (on its own log)
N_B3 = 5                                         # B3 calls: 8 units minus the 3 whose B3 answer G9 already holds (see b3_in_g9)
TOTAL_CALL_CAP = PLANNER_CALL_CAP + len(UNITS)   # 48: every attempt on the own log, B3 included, enforced by llm.MAX_G8_CALLS
CEILING_USD = float(os.environ.get("NULLLAB_G9B_CEILING", "4.00"))
RETRY_MARGIN_USD = 2 * EST["plan"]               # reserved per admitted unit for transport retries (retries are not model repairs)
CODE_FILES = tuple(g9.CODE_FILES) + ("agent/factorial_g9b.py",)
_IO = threading.Lock()


# ---------------- hashing (g9's functions, same rule) ----------------
sha_file, sha_obj, sha_text = g9.sha_file, g9.sha_obj, g9.sha_text


def unit_id(r, c):
    return f"g9-r{r}:{c}"


def code_hashes(root=ROOT):
    return {x: sha_file(Path(root) / x) for x in CODE_FILES}


def prompt_hashes():
    return g9.prompt_hashes()


def rules_payload():
    return {"instrument": "g9b", "units": [[r, c] for r, c in UNITS], "g9_recorded_units_expected": [[r, c] for r, c in G9_RECORDED],
            "repeat_id_format": "g9-r<k>", "temperature": TEMPERATURE, "seeds": list(g9.SEEDS), "n_boot": g9.N_BOOT,
            "repair_kinds": list(g9.REPAIR_KINDS), "case_call_cap": CASE_CALL_CAP, "planner_call_cap": PLANNER_CALL_CAP,
            "total_call_cap": TOTAL_CALL_CAP, "est_usd": EST, "ceiling_usd": CEILING_USD, "retry_margin_usd_per_unit": RETRY_MARGIN_USD,
            "admission": "a unit starts only if est spent + reserve of units in flight + its worst case (incl. retry margin) <= ceiling; else it stays unrecorded",
            "b3": "one B3 call per unit unless the G9 record already holds a usable B3 answer for that (repeat, case); then none and the G9 answer is used",
            "no_reroll": "every recorded G9b harness failure (also an exhausted transport) stays; no unit is re-run",
            "reference": g9.REFERENCE, "published_range_ehg": list(g9.PUBLISHED_RANGE_EHG), "tolerance": g9.TOL, "acceptance": g9.ACCEPT,
            "union_denominators": g9.REPEATS, "harness_target_max": g9.HARNESS_TARGET, "exec_timeout_s": g9.EXEC_TIMEOUT_S,
            "transport": g9.transport.DEFAULTS, "smoke": {"rows": g9.smoke.SMOKE_ROWS, "timeout_s": g9.smoke.SMOKE_TIMEOUT_S},
            "guard_sha256": {"g9_units_pre_speed_fix": GUARD_G9_PRE, "g9b_units_speed_fixed": GUARD_G9B},
            "harness_inconclusive": "counted in the denominator as not-met; never a false alarm, never a no-effect"}


def view_hashes():
    return g9.view_hashes()


def all_hashes():
    return {"code": code_hashes(), "prompts": prompt_hashes(), "rules": {"payload": rules_payload(), "sha256": sha_obj(rules_payload())},
            "agent_views": view_hashes()}


# ---------------- paths / environment ----------------
FORBIDDEN_DIRS = ("runs_g9", "runs_g8", "runs_ehg", "runs_g7")


def out_dir():
    d = Path(os.environ.get("NULLLAB_G9B_OUT") or ROOT / "runs_g9b")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _check_not_forbidden(paths):
    for name in FORBIDDEN_DIRS:
        forbidden = (ROOT / name).resolve()
        for p in paths:
            q = Path(p).resolve()
            if q == forbidden or forbidden in q.parents:
                raise SystemExit(f"refusing: {p} is under {name}")


def configure():
    """Point g9's env-driven paths (its out_dir, the llm call log, traces) at runs_g9b and set the G9b caps on g9/llm/g8 for THIS process."""
    d = out_dir()
    _check_not_forbidden([d])
    os.environ["NULLLAB_G9_OUT"] = str(d)                 # g9.out_dir() (prereg log, r<k>.json) must resolve to OUR directory
    os.environ["NULLLAB_PHASE"] = "g8"
    os.environ["NULLLAB_G8_OUT"] = str(d)
    os.environ["NULLLAB_G8_LOG"] = str(d / "live_calls_g9b.jsonl")
    os.environ["NULLLAB_TRACES"] = str(d / "traces.jsonl")
    llm.MAX_G8_CALLS = TOTAL_CALL_CAP
    g9.PLANNER_CALL_CAP, g9.TOTAL_CALL_CAP, g9.CEILING_USD, g8.CEILING_USD = PLANNER_CALL_CAP, TOTAL_CALL_CAP, CEILING_USD, CEILING_USD
    _check_not_forbidden([g9.out_dir(), llm.g8_log(), llm.trace_file(), transport.transport_log()])
    if Path(g9.out_dir()).resolve() != d.resolve():
        raise SystemExit("refusing: g9.out_dir() does not resolve to the G9b directory")
    return d


def _read_jsonl(p):
    p = Path(p)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def _own_log():
    return out_dir() / "prereg_log.jsonl"


def _prereg(kind, payload, case=None):
    return g9._prereg(kind, payload, case)               # g9.out_dir() is runs_g9b after configure()


def _last(kind, case=None, path=None):
    recs = [r for r in _read_jsonl(path or _own_log()) if r["kind"] == kind and r.get("case") == case]
    return recs[-1] if recs else None


# ---------------- read-only access to runs_g9 ----------------
def g9_state():
    """{repeat: parsed r<k>.json of runs_g9} for the repeats that exist. Read-only."""
    out = {}
    for r in range(1, g9.MAX_REPEAT + 1):
        p = G9_DIR / f"r{r}.json"
        if p.exists():
            out[r] = json.loads(p.read_text(encoding="utf-8"))
    return out


def g9_recorded_units(state=None):
    state = g9_state() if state is None else state
    return sorted((r, c) for r, d in state.items() for c in d.get("loop", {}))


def check_units_not_in_g9(units=None, state=None):
    """Refuse (SystemExit) any unit that already has a loop record in runs_g9."""
    rec = set(g9_recorded_units(state))
    clash = [unit_id(r, c) for r, c in (UNITS if units is None else units) if (r, c) in rec]
    if clash:
        raise SystemExit("REFUSING: already recorded in runs_g9, not to be re-run: " + ", ".join(clash))


def b3_in_g9(r, c, state=None):
    state = g9_state() if state is None else state
    b = (state.get(r) or {}).get("b3", {}).get(c)
    return bool(b) and "ans" in b


def acknowledged_changes():
    ch = json.loads(CHANGELOG.read_text(encoding="utf-8")).get("changes", []) if CHANGELOG.exists() else []
    return {(c["path"], c["old_sha256"], c["new_sha256"]) for c in ch}


def crosscheck_g9(h):
    """Compare what this run will use with the G9 freeze records (read-only). Returns problems."""
    bad, p = [], G9_DIR / "prereg_log.jsonl"
    if not p.exists():
        return ["runs_g9/prereg_log.jsonl missing: cannot cross-check against the G9 freeze"]
    for c, v in h["agent_views"].items():
        rec = _last("g9_agent_view_frozen", c, p)
        if rec is None:
            bad.append(f"G9 freeze has no agent view record for {c}")
        elif rec["payload"] != v:
            bad.append(f"agent view {c} differs from the G9 freeze record")
    rec = _last("g9_prompts", None, p)
    if rec is None or rec["payload"] != h["prompts"]:
        bad.append("prompts differ from the G9 freeze record")
    rec = _last("g9_source_hashes", None, p)
    if rec is None:
        bad.append("G9 freeze has no source hash record")
    else:
        ack = acknowledged_changes()
        for f in g9.CODE_FILES:
            old, new = rec["payload"].get(f), h["code"].get(f)
            if old != new and (f, old, new) not in ack:
                bad.append(f"{f} differs from the G9 freeze and the change is not in docs/FROZEN-CHANGELOG.json")
        if rec["payload"].get("agent/guard_g9.py") != GUARD_G9_PRE:
            bad.append("the G9 freeze record of guard_g9.py is not the pre-speed-fix hash 4a084a1c...")
    if h["code"].get("agent/guard_g9.py") != GUARD_G9B:
        bad.append("agent/guard_g9.py on disk is not the speed-fixed hash 983d2ffe...")
    return bad


def unit_problems(state=None):
    bad, rec = [], g9_recorded_units(state)
    if rec != sorted(G9_RECORDED):
        bad.append(f"runs_g9 records {[unit_id(r, c) for r, c in rec]}, expected {[unit_id(r, c) for r, c in sorted(G9_RECORDED)]}")
    if set(rec) & set(UNITS):
        bad.append("a G9b unit already has a record in runs_g9")
    if sorted(set(UNITS) | set(G9_RECORDED)) != sorted(g9.units_for(range(1, g9.MAX_REPEAT + 1))) or len(set(UNITS) | set(G9_RECORDED)) != N_UNITS:
        bad.append("G9b units + G9 recorded units are not exactly the 16 preregistered units")
    return bad


# ---------------- projection ----------------
def unit_worst(r, c, state=None):
    return (0 if b3_in_g9(r, c, state) else EST["b3"]) + CASE_CALL_CAP * EST["plan"]   # plan and repair estimates are both 0.12


def projected(state=None):
    n_b3 = sum(0 if b3_in_g9(r, c, state) else 1 for r, c in UNITS)
    floor = n_b3 * EST["b3"] + len(UNITS) * EST["plan"]
    worst = n_b3 * EST["b3"] + len(UNITS) * CASE_CALL_CAP * EST["plan"]
    one_rep = floor + len(UNITS) * EST["repair"]
    two_rep = floor + 2 * len(UNITS) * EST["repair"]
    return {"units": len(UNITS), "b3_calls": n_b3, "floor_usd": round(floor, 2), "one_repair_per_unit_usd": round(one_rep, 2),
            "two_repairs_per_unit_usd": round(two_rep, 2), "worst_case_usd": round(worst, 2),
            "worst_case_every_call_retried_once_usd": round(2 * worst, 2), "ceiling_usd": CEILING_USD,
            "max_planner_calls_per_case": CASE_CALL_CAP, "max_planner_calls_total": len(UNITS) * CASE_CALL_CAP, "planner_call_cap": PLANNER_CALL_CAP,
            "max_live_calls_total": n_b3 + len(UNITS) * CASE_CALL_CAP, "total_call_cap": TOTAL_CALL_CAP,
            "already_spent_est_usd": round(g9.my_spent(), 2), "within_planner_cap": len(UNITS) * CASE_CALL_CAP <= PLANNER_CALL_CAP,
            "worst_case_within_ceiling": worst <= CEILING_USD,
            "admission": "per unit: spent + in-flight reserve + unit worst case + retry margin must fit under the ceiling, else the unit is not started"}


def print_projection():
    pj = projected()
    print(f"PROJECTED SPEND G9b (estimates, not billing): floor ${pj['floor_usd']:.2f}, one repair per unit ${pj['one_repair_per_unit_usd']:.2f}, "
          f"two ${pj['two_repairs_per_unit_usd']:.2f}, WORST CASE ${pj['worst_case_usd']:.2f} ({pj['units']} units, {pj['b3_calls']} B3 calls, up to "
          f"{pj['max_planner_calls_per_case']} planner calls each); ceiling ${pj['ceiling_usd']:.2f} enforced per unit by admission and per call by the gate; "
          f"already spent est ${pj['already_spent_est_usd']:.2f}; planner-side cap {PLANNER_CALL_CAP}, all-calls cap {TOTAL_CALL_CAP}"
          + ("" if pj["worst_case_within_ceiling"] else "; NOTE the all-repairs worst case exceeds the ceiling, so late units may be left unstarted"), flush=True)
    return pj


# ---------------- stages: project / hashes / freeze / verify ----------------
def project(args=None):
    configure()
    pj = print_projection()
    print(json.dumps(pj))
    return pj


def hashes(args=None):
    print(json.dumps(all_hashes(), indent=1))


def freeze(args=None):
    configure()
    h = all_hashes()
    _prereg("g9b_source_hashes", h["code"])
    _prereg("g9b_prompts", h["prompts"])
    _prereg("g9b_rules", h["rules"]["payload"])
    for c, v in h["agent_views"].items():
        _prereg("g9b_agent_view_frozen", v, c)
    doc = ROOT / DOC
    _prereg("g9b_prereg_doc", {"path": DOC, "sha256_lf": sha_file(doc) if doc.exists() else None})
    print("frozen ->", _own_log())


def verify_problems():
    h, bad = all_hashes(), []
    if g9.edit_dsl.spec_sha256() != g9.FROZEN_OPSPEC_SHA256:
        bad.append("edit_dsl op spec differs from the value frozen in EVAL-12")
    if g9.contract_g9.contract_sha256() != g9.FROZEN_CONTRACT_SHA256:
        bad.append("contract text differs from the value frozen in EVAL-12")
    checks = [("g9b_source_hashes", None, h["code"]), ("g9b_prompts", None, h["prompts"]), ("g9b_rules", None, h["rules"]["payload"])]
    checks += [("g9b_agent_view_frozen", c, v) for c, v in h["agent_views"].items()]
    for kind, case, now in checks:
        rec = _last(kind, case)
        if rec is None:
            bad.append(f"{kind} {case or ''}: no freeze record")
        elif rec["payload"] != now or rec["sha256"] != sha_obj(now) or rec["sha256"] != sha_obj(rec["payload"]):
            diff = [k for k in now if isinstance(now, dict) and rec["payload"].get(k) != now[k]] if isinstance(rec["payload"], dict) else []
            bad.append(f"{kind} {case or ''}: differs from the freeze record {diff}")
    doc = _last("g9b_prereg_doc")
    if doc is None or not (ROOT / DOC).exists():
        bad.append("prereg doc: no freeze record or file missing")
    elif doc["payload"]["sha256_lf"] != sha_file(ROOT / DOC):
        bad.append("prereg doc changed after the freeze")
    bad += crosscheck_g9(h)
    bad += unit_problems()
    return bad


def verify(args=None):
    configure()
    bad = verify_problems()
    print("VERIFY OK: every hash recomputed from disk equals its freeze record" if not bad else "VERIFY FAILED:\n- " + "\n- ".join(bad))
    return not bad


# ---------------- live: B3 + the g9 pipeline per unit ----------------
class Admission:
    """Reserves the worst case of every unit in flight so that admitted units can all finish inside the ceiling."""

    def __init__(self):
        self.lock, self.reserved = threading.Lock(), 0.0

    def admit(self, need):
        with self.lock:
            if not llm.replaying() and g9.my_spent() + self.reserved + need > CEILING_USD:
                return False
            self.reserved += need
            return True

    def release(self, need):
        with self.lock:
            self.reserved = max(0.0, self.reserved - need)


def run(args):
    configure()
    bad = verify_problems()
    if bad:
        raise SystemExit("REFUSING TO RUN: freeze missing or code/prompts/views changed since freeze, or G9 state unexpected:\n- " + "\n- ".join(bad))
    state = g9_state()
    check_units_not_in_g9(UNITS, state)
    reps = sorted({int(a) for a in args}) if args else sorted({r for r, _ in UNITS})
    if any(r not in {u[0] for u in UNITS} for r in reps):
        raise SystemExit(f"repeats must be among {sorted({u[0] for u in UNITS})}")
    model = llm.model_for()
    g9.install_instruments()
    res = {r: g9._load(f"r{r}", {"repeat": f"g9-r{r}", "instrument": "g9b", "model": model, "temperature": TEMPERATURE, "b3": {}, "loop": {}}) for r in reps}
    pending = [(r, c) for r, c in UNITS if r in reps and c not in res[r]["loop"]]   # a recorded harness failure is NOT re-rolled
    print_projection()
    adm, lock = Admission(), threading.Lock()

    def commit(r, section, case, value):
        with lock:
            res[r][section][case] = value
            g9._save(f"r{r}", res[r])

    def one(r, c):
        need = unit_worst(r, c, state) + RETRY_MARGIN_USD
        if not adm.admit(need):
            return None
        t0 = time.time()
        try:
            if not b3_in_g9(r, c, state) and (c not in res[r]["b3"] or "error" in res[r]["b3"][c]):
                try:
                    raw, usage = llm.live_complete_ex(g9.B3_SYSTEM, agent_view(CASES[c]) + f"\n\n[repeat id: g9-r{r}]", est_usd=EST["b3"], tag="g9b_b3",
                                                      role="b3", model=llm.model_for("b3"), temperature=TEMPERATURE)
                    commit(r, "b3", c, {"ans": llm.parse_json(raw), "raw": raw, "usage": usage})
                except Exception as e:  # noqa: BLE001
                    commit(r, "b3", c, {"error": repr(e)[:400]})
            lr = g9.pipeline(CASES[c], f"g9-r{r}", model=model)
        finally:
            adm.release(need)
        lr["instrument"] = "g9b"
        print(f"g9b {unit_id(r, c):40s} {g9.outcome_label(lr)} calls={len(lr.get('calls', []))} {time.time() - t0:.0f}s", flush=True)
        return lr

    while pending:
        skipped = []
        with ThreadPoolExecutor(3) as ex:
            futs = {ex.submit(one, *k): k for k in pending}
            for f in as_completed(futs):
                r, c = futs[f]
                try:
                    lr = f.result()
                except Exception as e:  # noqa: BLE001
                    lr = {"status": "INCONCLUSIVE", "harness_failure": "internal_error", "label": g8.label("INCONCLUSIVE", "internal_error"),
                          "reason": [repr(e)[:400]], "calls": [], "retries": 0, "instrument": "g9b"}
                if lr is None:
                    skipped.append((r, c))
                else:
                    commit(r, "loop", c, lr)
        if len(skipped) == len(pending):
            for r, c in skipped:
                print(f"NOT STARTED (admission: est spent ${g9.my_spent():.2f} + worst case would pass ceiling ${CEILING_USD:.2f}): {unit_id(r, c)}", flush=True)
            break
        pending = skipped


# ---------------- scoring: the union of the G9 and G9b units ----------------
def guard_label(source):
    return ({"source": "g9", "guard_sha256": GUARD_G9_PRE, "guard_version": "G9 live run guard, before the speed fix (hash 4a084a1c...)", "ran": G9_WINDOW}
            if source == "g9" else
            {"source": "g9b", "guard_sha256": GUARD_G9B, "guard_version": "speed-fixed guard (hash 983d2ffe..., decisions identical per EVAL-14)", "ran": "G9b run"})


def expected_units():
    return sorted(g9.units_for(range(1, g9.MAX_REPEAT + 1)))


def union_score(g9_loop, g9b_loop, g9_b3=None, g9b_b3=None, g9_stalled_b3=None):
    """Pure. *_loop = {case: {'r1': loop record}}; *_b3 = {case: {'r1': b3 row}}. g9_stalled_b3 = B3 rows G9 holds for units it never finished; a G9b unit
    without its own B3 row uses that one (a B3 answer already observed is not asked for again). Evaluates the EVAL-13 clauses (g9.score_cases) on the union."""
    recs, source, b3, b3_from = {c: {} for c in CASES}, {}, {c: {} for c in CASES}, {}
    for src, loop in (("g9", g9_loop), ("g9b", g9b_loop)):
        for c in CASES:
            for r, rec in (loop.get(c) or {}).items():
                if r in recs[c]:
                    raise ValueError(f"unit {r}:{c} is recorded in both G9 and G9b")
                recs[c][r] = rec
                source[(c, r)] = src
    for c in CASES:
        for r in recs[c]:
            own = ((g9_b3 if source[(c, r)] == "g9" else g9b_b3) or {}).get(c, {}).get(r)
            if own is not None:
                b3[c][r], b3_from[(c, r)] = own, source[(c, r)]
            elif source[(c, r)] == "g9b" and r in ((g9_stalled_b3 or {}).get(c) or {}):
                b3[c][r], b3_from[(c, r)] = g9_stalled_b3[c][r], "g9"
    s = g9.score_cases(recs, b3)
    per_unit, by_source = [], {}
    for (r, c) in expected_units():
        k = f"r{r}"
        if k not in recs[c]:
            per_unit.append({"unit": unit_id(r, c), "case": c, "repeat": k, "present": False, **guard_label("g9b" if (r, c) in UNITS else "g9"),
                             "outcome": "MISSING"})
            continue
        row = dict(s["cases"][c][k])
        per_unit.append({"unit": unit_id(r, c), "case": c, "repeat": k, "present": True, **guard_label(source[(c, k)]),
                         "outcome": row["label"], "sign": row["sign"], "calls": row["calls"], "repairs_used": row.get("repairs_used"),
                         "inflation_mean": row.get("inflation_mean"), "magnitude_ok": row.get("magnitude_ok"), "b3": row.get("b3"),
                         "b3_from": b3_from.get((c, k)), "first_plan_guard": row.get("first_plan_guard")})
    for src in ("g9", "g9b"):
        for g, (lk, cl) in g9.GROUPS.items():
            us = [u for u in per_unit if u["present"] and u["source"] == src and u["case"] in (lk, cl)]
            by_source.setdefault(src, {})[g] = {
                "units": len(us), "leaky_units": sum(u["case"] == lk for u in us), "clean_units": sum(u["case"] == cl for u in us),
                "direction_right": sum(u["case"] == lk and u["sign"] == "+" for u in us),
                "clean_false_alarms": sum(u["case"] == cl and u["sign"] == "+" for u in us),
                "no_effect_or_no_flaw": sum(u["sign"] == "0" for u in us),
                "harness_inconclusive": sum(u["sign"] == "INCONCLUSIVE" for u in us),
                "magnitude_within_0.15": sum(bool(u["magnitude_ok"]) for u in us if u["case"] == lk)}
    present = [u for u in per_unit if u["present"]]
    complete = len(present) == N_UNITS
    verdict = lambda ok: ("PASS" if ok else "FAIL") if complete else "NOT EVALUABLE (fewer than 16 units exist)"   # noqa: E731
    return {"instrument": "g9b", "complete": complete, "units_expected": N_UNITS, "units_present": len(present),
            "units_present_g9": sum(u["source"] == "g9" for u in present), "units_present_g9b": sum(u["source"] == "g9b" for u in present),
            "missing": [u["unit"] for u in per_unit if not u["present"]],
            "union_result": {"EHG": verdict(s["ehg"]["PASS"]), "CIVILWAR_REGRESSION": verdict(s["civilwar"]["PASS"]),
                             "harness_target_met": s["overall"]["harness_target_met"] if complete else None},
            "union": {g: s[g] for g in ("ehg", "civilwar", "overall")}, "harness_failures": s["harness_failures"],
            "by_source": by_source, "per_unit": per_unit, "guard_versions": {"g9": guard_label("g9"), "g9b": guard_label("g9b")},
            "label_note": ("Decisions of the two guard versions are identical per docs/EVAL-14-GUARD-SPEED.md, so the union is valid; the label stays visible. "
                           "Counts, not rates; stalled G9 units had no observed outcome; EHG is not held out for the DSL; any G9b harness failure is recorded, not re-rolled.")}


def _loop_and_b3(data):
    loop, b3 = {c: {} for c in CASES}, {c: {} for c in CASES}
    for r, d in data.items():
        for c in CASES:
            if c in d.get("loop", {}):
                loop[c][f"r{r}"] = d["loop"][c]
                if c in d.get("b3", {}):
                    b3[c][f"r{r}"] = g9.b3_row(d["b3"][c], c)
    return loop, b3


def score(args=None):
    configure()
    gs = g9_state()
    g9_loop, g9_b3 = _loop_and_b3(gs)
    stalled = {c: {f"r{r}": g9.b3_row(d["b3"][c], c) for r, d in gs.items() if c in d.get("b3", {}) and c not in d.get("loop", {})} for c in CASES}
    own = {r: g9._load(f"r{r}") for r in range(1, g9.MAX_REPEAT + 1)}
    g9b_loop, g9b_b3 = _loop_and_b3({r: d for r, d in own.items() if d})
    out = union_score(g9_loop, g9b_loop, g9_b3, g9b_b3, stalled)
    out["comparison_reported_next_to_this"] = {
        "G7": "FAILED its preregistered acceptance (docs/EVAL-7.md); not merged, not re-scored",
        "G8": "civil-war pair, 5 repeats: direction 4/5, clean false alarms 0/5, inflation within 0.15 of +0.36 in 4/5, harness-INCONCLUSIVE 1/10 (docs/EVAL-9-G8-RESULT.md)",
        "EHG_offline_rule_baseline": "no rule fires on either EHG case, inflation 0.000, direction right 0/1, false alarms 0 (docs/EVAL-11-EHG-PREREG.md section 5)",
        "reading_only_B3_on_EHG": "matched the loop in the 3 recorded G9 repeats (see b3 fields per unit); reported, not a clause"}
    out["usage_g9b"] = g9.usage_summary()
    out["note"] = ("inflation = claimed minus controlled metric (fix_both / fix_all), mean over seeds 42/43/44. EHG reference +0.430, published range +0.36..+0.49; "
                   "civil war +0.36. 'no_flaw' on a leaky unit counts as direction not right, on a clean unit as no false alarm.")
    g9._save("score", out)
    print(json.dumps({"complete": out["complete"], "units_present": out["units_present"], "union_result": out["union_result"],
                      "by_source": out["by_source"]}, indent=1))
    for h in out["harness_failures"]:
        print("HARNESS FAILURE", h)
    return out


STAGES = {"project": project, "hashes": hashes, "freeze": freeze, "verify": verify, "run": run, "score": score,
          "usage": lambda a=None: (configure(), print(json.dumps(g9.usage_summary())))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--out")
    ap.add_argument("stage", choices=sorted(STAGES))
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    os.environ["NULLLAB_MODEL"] = a.model or os.environ.get("NULLLAB_MODEL") or DEFAULT_MODEL
    if a.out:
        os.environ["NULLLAB_G9B_OUT"] = a.out
    STAGES[a.stage](a.args)


if __name__ == "__main__":
    main()
