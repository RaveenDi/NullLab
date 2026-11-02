"""Offline replay validation of the G9 edit DSL + behavioural guard (docs/EVAL-12-G9-DSL.md). ZERO model calls, ZERO spend, no network.
ENGINEERING result about the harness. Not a Meta score, not a live G9 run.

  .venv/Scripts/python.exe -m eval.validate_dsl_replay [--out runs_g9_offline] [--workers 3] [--translate-only] [--allow-unfrozen]

Reads (never writes) runs_g5, runs_g6, runs_g7, runs_g8 (G8 is a live run in progress: the files present at the moment of reading are used, and a
snapshot of what was read is recorded). Refuses to run unless the frozen op-list hash and the frozen file hashes in the doc match the disk."""
import argparse
import ast
import hashlib
import json
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import contract_g9 as ct, edit_dsl, factorial_g5, factorial_g7 as g7, guard_g9  # noqa: E402
import g4  # noqa: E402

DOC = ROOT / "docs" / "EVAL-12-G9-DSL.md"
FROZEN_FILES = ("agent/edit_dsl.py", "agent/guard_g9.py", "agent/contract_g9.py", "eval/validate_dsl_replay.py")
CLEAN_CASES = {"clean_control", "clean_group_correct", "clean_wine_correct", "g4_visit_history_clean", "civilwar_temporal_clean",
               "civilwar_disguised_clean", "esl_selection_clean", "ehg_disguised_clean"}
OVERSTRICT = ("FEATURE-REASON", "FEATURES changed")  # documented over-strict old-guard rejections (EVAL-5 s4, EVAL-6 s4, forensics); MODEL-on-resampler (EVAL-11 s6) had no saved plan
PROFILES = {"civilwar": {"overrides": {"N_TREES": 6}}, "ehg": {"overrides": {"N_TREES": 20}}}
ALL_RULES = ("justification", "split_required")


def profile_for(case):
    return PROFILES["civilwar"] if case.startswith("civilwar") else PROFILES["ehg"] if case.startswith("ehg") else {}


def case_dir(gen, c):
    return g4.CASES[c] if gen == "g5" else ROOT / "real" / c


def lf_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# ---------------------------------------------------------------- frozen-doc check
def check_frozen(allow):
    txt = DOC.read_text(encoding="utf-8") if DOC.exists() else ""
    problems = []
    m = re.search(r"FROZEN_OPSPEC_SHA256:\s*`?([0-9a-f]{64})", txt)
    if not m or m.group(1) != edit_dsl.spec_sha256():
        problems.append(f"op-list hash: doc {m.group(1) if m else None} != code {edit_dsl.spec_sha256()}")
    for f in FROZEN_FILES:
        m = re.search(r"FROZEN_FILE\s+" + re.escape(f) + r"\s+`?([0-9a-f]{64})", txt)
        if not m or m.group(1) != lf_sha(ROOT / f):
            problems.append(f"{f}: doc {m.group(1)[:12] if m else None} != disk {lf_sha(ROOT / f)[:12]}")
    if "PASS CRITERIA (preregistered" not in txt:
        problems.append("doc has no preregistered PASS CRITERIA section")
    if problems and not allow:
        raise SystemExit("REFUSING TO RUN: the frozen record does not match.\n" + "\n".join(problems))
    return problems


# ---------------------------------------------------------------- inventory of saved plans
def _verdicts(lr):
    return [x for x in lr.get("log", []) if x.get("phase", "").startswith("Verify")]


def collect():
    rows, snap = [], {"g8_files": []}
    for gen in ("g5", "g6", "g7", "g8"):
        for p in sorted((ROOT / f"runs_{gen}").glob("r[0-9].json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:  # g8 may be mid-write
                snap.setdefault("unreadable", []).append(f"{gen}/{p.name}: {e!r}"[:120])
                continue
            if gen == "g8":
                snap["g8_files"].append(p.name)
            for c, lr in d.get("loop", {}).items():
                vs = _verdicts(lr)
                first = (d.get("plan", {}).get(c) or {}).get("plan")
                final = lr.get("final_plan")
                if gen == "g8":
                    first = G8_FIRST.get((c, d.get("repeat")))
                insts = []
                if first:
                    insts.append(("first", first, vs[0] if vs else None))
                if final and (not first or json.dumps(final, sort_keys=True) != json.dumps(first, sort_keys=True)):
                    insts.append(("final", final, vs[-1] if vs else None))
                for which, pl, v in insts:
                    if not isinstance(pl, dict) or not isinstance(pl.get("edits"), dict):
                        continue
                    rows.append({"id": f"{gen}/{p.stem}/{c}/{which}", "gen": gen, "file": p.name, "case": c, "which": which, "plan": pl,
                                 "stored_verdict": (v or {}).get("verdict"), "stored_violations": (v or {}).get("violations") or []})
    return rows, snap


G8_FIRST = {}


def load_g8_first(snap):
    """First planner replies of G8 from runs_g8/traces.jsonl, matched to (case, repeat) by recomputing the exact planner user message."""
    p = ROOT / "runs_g8" / "traces.jsonl"
    if not p.exists():
        return
    snap["g8_traces_sha256"] = lf_sha(p)
    traces = []
    for l in p.read_text(encoding="utf-8").splitlines():
        try:
            traces.append(json.loads(l))
        except Exception:
            pass
    from agent import llm
    users = {}
    for c in (g7.LEAKY, g7.CLEAN):
        for i in range(1, 8):
            users[factorial_g5.user_msg(ROOT / "real" / c, f"g8-r{i}")] = (c, f"g8-r{i}")
    for t in traces:
        if t.get("role") == "planner" and t.get("user") in users:
            try:
                pl = llm.parse_json(t["reply"])
            except Exception:
                continue
            if isinstance(pl, dict) and isinstance(pl.get("edits"), dict) and users[t["user"]] not in G8_FIRST:
                G8_FIRST[users[t["user"]]] = pl


# ---------------------------------------------------------------- legacy -> DSL translation
CALLS_RANDOM = {"train_test_split", "StratifiedShuffleSplit", "ShuffleSplit", "permutation", "shuffle", "default_rng", "RandomState", "choice"}
CALLS_GROUP = {"GroupShuffleSplit", "GroupKFold", "StratifiedGroupKFold", "LeaveOneGroupOut"}


def _calls(node):
    return {edit_dsl.fname(c) for c in ast.walk(node) if isinstance(c, ast.Call)}


_CONSTS = {}


def _lits(node):
    """String literals in node, plus the values of module-level string constants the node refers to (e.g. df[PUMP])."""
    out = {n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    out |= {_CONSTS[n.id] for n in ast.walk(node) if isinstance(n, ast.Name) and n.id in _CONSTS}
    return out


def _time_col(fn, header):
    tcols = [c for c in header if ct.TIME_NAME.search(c)]
    hit = [c for c in _lits(fn) if c in tcols]
    if len(hit) == 1:
        return hit[0]
    if not hit and len(tcols) == 1:
        return tcols[0]
    return None


def _group_col(fn, header, target):
    hit = [c for c in _lits(fn) if c in header and c != target]
    return hit[0] if len(hit) == 1 else None


def _temporal_evidence(fn, header):
    tcols = {c for c in header if ct.TIME_NAME.search(c)}
    if "TimeSeriesSplit" in _calls(fn):
        return True
    tainted = set()
    for s in ast.walk(fn):
        if isinstance(s, ast.Assign) and (_lits(s.value) & tcols or {x.id for x in ast.walk(s.value) if isinstance(x, ast.Name)} & tainted):
            tainted |= {t.id for t in s.targets if isinstance(t, ast.Name)}

    def mentions(n):
        return bool(_lits(n) & tcols or {x.id for x in ast.walk(n) if isinstance(x, ast.Name)} & tainted)
    for s in ast.walk(fn):
        if isinstance(s, ast.Compare) and any(isinstance(o, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for o in s.ops) and mentions(s):
            return True
    has_slice = any(isinstance(s, ast.Subscript) and isinstance(s.slice, ast.Slice) for s in ast.walk(fn))
    return bool(has_slice and any(isinstance(c, ast.Call) and edit_dsl.fname(c) in ("sort_values", "argsort", "sort") and mentions(c) for c in ast.walk(fn)))


def _shuffle_false(fn):
    return any(k.arg == "shuffle" and isinstance(k.value, ast.Constant) and k.value.value is False for c in ast.walk(fn) if isinstance(c, ast.Call) for k in c.keywords)


def translate_step(orig_tree, header, step, kind, new_src):
    """-> (ops|None, reason). Heuristic classification of what a free-written legacy edit does; the table records the reason either way."""
    defs = edit_dsl.defs_of(orig_tree)
    if kind == "feature":
        return None, "feature edit: the frozen op list has no feature op (illegitimate-feature leakage is out of scope)"
    if step not in defs:
        return None, f"step '{step}' is not a function of the original"
    try:
        nt = ast.parse(new_src)
        new_fn = next(n for n in nt.body if isinstance(n, ast.FunctionDef))
    except Exception as e:
        return None, f"unparseable legacy step ({type(e).__name__})"
    orig_fn = defs[step]
    hold = edit_dsl.holdout_steps(orig_tree)
    oc, nc = _calls(orig_fn), _calls(new_fn)
    orig_has_split = bool(oc & edit_dsl.SPLITTER_CLASSES) or "train_test_split" in oc
    if step in hold or (orig_has_split and step not in ("claimed_eval",)) or (kind == "split" and orig_has_split):
        if _temporal_evidence(new_fn, header):
            col = _time_col(new_fn, header)
            if col is None:
                return None, "temporal edit but the time column is not identifiable from the plan"
            return [{"op": "replace_split", "step": step, "kind": "temporal", "col": col}], "temporal hold-out/CV -> replace_split(temporal)"
        if nc & CALLS_GROUP:
            gc = _group_col(new_fn, header, _CONSTS.get("TARGET"))
            if gc is None:
                return None, "group split: the grouping column is not identifiable from the plan"
            return [{"op": "replace_split", "step": step, "kind": "group", "col": gc}], "group hold-out -> replace_split(group)"
        if _shuffle_false(new_fn) or (step not in hold and "KFold" in " ".join(nc) and not (nc & CALLS_RANDOM)):
            return None, "contiguous (unshuffled) folds/hold-out: the DSL has no such kind (only random, group, temporal)"
        if step in hold and (nc & CALLS_RANDOM or nc & edit_dsl.SPLITTER_CLASSES):
            return [{"op": "replace_split", "step": step, "kind": "random", "col": None}], "random hold-out -> replace_split(random) (stratification is dropped)"
        if step not in hold and nc & edit_dsl.SPLITTER_CLASSES:
            return None, "CV splitter replaced by another non-temporal splitter; no DSL kind for that"
        return None, "split edit that is not a recognised random/group/temporal replacement"
    # scope edits: a call that ran on all rows before the split now runs inside a fold loop
    removed = [c for c in defs if c in oc and c not in nc and c != step]
    loops = [n for n in ast.walk(new_fn) if isinstance(n, ast.For) and isinstance(n.target, ast.Tuple) and len(n.target.elts) == 2]
    for r in removed:
        learners = {c for c in _calls(defs[r]) if c[:1].isupper()}
        if learners and any(learners & _calls(lp) for lp in loops):
            return [{"op": "move_into_fold", "step": step, "call": r}], f"'{r}' ran before the split and its learners now run inside the fold loop -> move_into_fold"
    if kind == "fit_scope" and not removed and any(c in oc for c in defs if c != step and c != "load" and any(isinstance(n, ast.For) for n in ast.walk(defs[c]))):
        return None, "rewrite of a step that has no statement the DSL could move (already fold-scoped or structural rewrite)"
    return None, "free-form rewrite not expressible with the frozen ops"


def translate_plan(case_dir_, plan):
    src = (Path(case_dir_) / "train.py").read_text(encoding="utf-8")
    hdr = (Path(case_dir_) / "data.csv").open(encoding="utf-8").readline().strip().split(",")
    tree = ast.parse(src)
    _CONSTS.clear()
    _CONSTS.update({t.id: n.value.value for n in tree.body if isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
                    for t in n.targets if isinstance(t, ast.Name)})
    per, facs = {}, []
    for X in ("A", "B"):
        e = (plan.get("edits") or {}).get(X) or {}
        ops, reasons, ok = [], [], True
        for step, ns in (e.get("steps") or {}).items():
            o, why = translate_step(tree, hdr, step, e.get("kind"), ns)
            reasons.append(f"{step}: {why}")
            if o is None:
                ok = False
            else:
                ops += o
        per[X] = {"kind": e.get("kind"), "expressible": ok and bool(ops), "ops": ops if ok else [], "reasons": reasons}
        if ok and ops:
            facs.append({"id": "ABC"[len(facs)], "flaw": str(plan.get(X) or "legacy factor"), "evidence_line": str(plan.get(f"{X}_code_line") or "legacy"),
                         "ops": list({json.dumps(o, sort_keys=True): o for o in ops}.values()), "_legacy": X})
    n = len(facs)
    cov = "none" if n == 0 else ("full" if n == sum(1 for X in "AB" if (plan.get("edits") or {}).get(X)) else "partial")
    dsl = None
    if n:
        pdp = {"fix_all": 1} if n == 1 else {**{f"fix_{f['id']}": 1 for f in facs}, "fix_all": 1}
        dsl = {"verdict": "flaw", "factors": [{k: v for k, v in f.items() if k != "_legacy"} for f in facs], "predicted_drop_pp": pdp,
               "culprit_ranking": ["A"] if n == 1 else ["A", "interaction"], "reason": "replay of a legacy plan"}
    return {"coverage": cov, "per_edit": per, "dsl_plan": dsl}


# ---------------------------------------------------------------- decisions
def old_decision(cdir, plan):
    try:
        _, problems, _ = g7.guard(cdir, plan, rules=ALL_RULES)
    except Exception as e:  # noqa: BLE001
        return {"decision": "ERROR", "problems": [repr(e)[:200]]}
    return {"decision": "REJECT" if problems else "ACCEPT", "problems": problems}


def new_decision(cdir, case, dsl_plan, runtime=True):
    if dsl_plan is None:
        return {"decision": "NOT_EXPRESSIBLE", "problems": [], "crash": False}
    try:
        r = ct.check_plan(dsl_plan, cdir, runtime=runtime, profile=profile_for(case))
    except Exception as e:  # noqa: BLE001  an exception here is a harness crash and is counted as one
        return {"decision": "HARNESS_CRASH", "problems": [repr(e)[:300]], "crash": True}
    if r["runtime"] is None:
        return {"decision": "REJECT" if not r["ok"] else "STATIC_OK", "problems": r["problems"], "stage": "static", "crash": False}
    rt = r["runtime"]
    return {"decision": rt["decision"], "problems": rt["problems"], "stage": "runtime", "crash": bool(rt.get("crash")),
            "internal": any("INTERNAL" in p for p in rt["problems"]), "facts": rt["configs"].get("fix_all", {}).get("facts")}


def evaluate_row(row):
    cdir = case_dir(row["gen"], row["case"])
    tr = translate_plan(cdir, row["plan"])
    row = {k: v for k, v in row.items() if k != "plan"}
    row["translation"] = {"coverage": tr["coverage"], "per_edit": tr["per_edit"], "dsl_ops": tr["dsl_plan"] and [f["ops"] for f in tr["dsl_plan"]["factors"]]}
    return row, tr["dsl_plan"], cdir


# known-correct fixes (design cases: used while building the ops, so this is a regression test, not held out)
KNOWN_CORRECT = [
    ("ehg_disguised", "EHG oversampling moved into the fold", {"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}),
    ("ehg_disguised", "EHG oversampler dropped from evaluation", {"op": "drop_from_eval", "step": "claimed_eval", "call": "oversample"}),
    ("civilwar_disguised", "civil-war temporal hold-out", {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "epoch"}),
    ("civilwar_apparent", "civil-war temporal hold-out (year)", {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "year"}),
    ("esl_selection", "ESL screen moved into the fold", {"op": "move_into_fold", "step": "claimed_eval", "call": "screen"}),
]
# the same ops on the matching clean pipelines must NOT be accepted (specificity)
KNOWN_WRONG = [
    ("ehg_disguised_clean", "EHG clean: move oversampling", {"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}),
    ("ehg_disguised_clean", "EHG clean: drop oversampling", {"op": "drop_from_eval", "step": "claimed_eval", "call": "oversample"}),
    ("civilwar_disguised_clean", "civil-war clean: temporal split again", {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "epoch"}),
    ("civilwar_temporal_clean", "civil-war temporal_clean: temporal split again", {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "year"}),
    ("esl_selection_clean", "ESL clean: move screen", {"op": "move_into_fold", "step": "cv_predict", "call": "screen"}),
]


def one_factor(op):
    return {"verdict": "flaw", "factors": [{"id": "A", "flaw": "known", "evidence_line": "known", "ops": [op]}], "predicted_drop_pp": {"fix_all": 1},
            "culprit_ranking": ["A"], "reason": "known-correct reference"}


def md_table(rows):
    cols = ["id", "clean?", "old stored", "old today", "coverage", "new", "crash"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(x) for x in (r["id"], "Y" if r["clean_case"] else "", r["stored_verdict"], r["old_today"]["decision"], r["translation"]["coverage"],
                                                         r["new"]["decision"], "Y" if r["new"].get("crash") else "")) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "runs_g9_offline"))
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--translate-only", action="store_true")
    ap.add_argument("--allow-unfrozen", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    unfrozen = check_frozen(a.allow_unfrozen or a.translate_only)
    t0 = time.time()
    snap = {}
    load_g8_first(snap)
    rows, snap2 = collect()
    snap.update(snap2)
    prepared = [evaluate_row(r) for r in rows]
    for (row, dsl, cdir), r0 in zip(prepared, rows):
        row["clean_case"] = row["case"] in CLEAN_CASES
        row["old_today"] = old_decision(cdir, r0["plan"])
        row["old_rightly_rejected"] = (row["old_today"]["decision"] == "REJECT" and row["clean_case"] and
                                       any(not any(t in p for t in OVERSTRICT) for p in row["old_today"]["problems"]))
    if a.translate_only:
        (out / "translation_only.json").write_text(json.dumps([p[0] for p in prepared], indent=1, default=str), encoding="utf-8")
        print("translate-only:", Counter(p[0]["translation"]["coverage"] for p in prepared))
        return

    def run(item):
        row, dsl, cdir = item
        row["new"] = new_decision(cdir, row["case"], dsl)
        print(f"[{time.time() - t0:6.0f}s] {row['id']:45s} {row['translation']['coverage']:8s} old={row['old_today']['decision']:7s} new={row['new']['decision']}", flush=True)
        return row
    with ThreadPoolExecutor(a.workers) as ex:
        results = list(ex.map(run, prepared))
    # known-correct / known-wrong
    kc, kw = [], []
    for lst, dst in ((KNOWN_CORRECT, kc), (KNOWN_WRONG, kw)):
        for case, label, op in lst:
            cdir = ROOT / "real" / case
            nd = new_decision(cdir, case, one_factor(op))
            dst.append({"case": case, "label": label, "op": op, "new": nd})
            print(f"[{time.time() - t0:6.0f}s] {'KNOWN-CORRECT' if lst is KNOWN_CORRECT else 'KNOWN-WRONG':14s} {label:50s} {nd['decision']}", flush=True)
    # counts
    expr = [r for r in results if r["translation"]["coverage"] != "none"]
    full = [r for r in results if r["translation"]["coverage"] == "full"]
    cross = Counter((r["old_today"]["decision"], r["new"]["decision"]) for r in results)
    cross_expr = Counter((r["old_today"]["decision"], r["new"]["decision"]) for r in expr)
    crashes = [r["id"] for r in results if r["new"].get("crash")] + [f"KC:{k['label']}" for k in kc + kw if k["new"].get("crash")]
    newly = [r["id"] for r in results if r["old_rightly_rejected"] and r["new"]["decision"] == "ACCEPT"]
    kc_false_reject = [k["label"] for k in kc if k["new"]["decision"] != "ACCEPT"]
    kw_false_accept = [k["label"] for k in kw if k["new"]["decision"] == "ACCEPT"]
    summary = {
        "label": "ENGINEERING result: offline replay, no model, no spend; NOT a Meta score and NOT a live G9 run",
        "n_plans": len(results), "by_gen": dict(Counter(r["gen"] for r in results)), "clean_case_plans": sum(r["clean_case"] for r in results),
        "coverage": dict(Counter(r["translation"]["coverage"] for r in results)),
        "old_today": dict(Counter(r["old_today"]["decision"] for r in results)), "new": dict(Counter(r["new"]["decision"] for r in results)),
        "crosstab_old_new_all": {f"{k[0]} -> {k[1]}": v for k, v in sorted(cross.items())},
        "crosstab_old_new_expressible": {f"{k[0]} -> {k[1]}": v for k, v in sorted(cross_expr.items())}, "n_expressible_any": len(expr), "n_expressible_full": len(full),
        "P1_crashes_on_compiled_code": {"n": len(crashes), "ids": crashes},
        "P2_known_correct": {"n": len(kc), "false_rejects": kc_false_reject}, "P2b_known_wrong_on_clean": {"n": len(kw), "false_accepts": kw_false_accept},
        "P3_clean_plans_newly_accepted_that_old_rightly_rejected": {"n_candidates": sum(r["old_rightly_rejected"] for r in results), "newly_accepted": newly},
        "old_overstrict_clean_rejections": [{"id": r["id"], "new": r["new"]["decision"]} for r in results if r["clean_case"] and r["old_today"]["decision"] == "REJECT" and not r["old_rightly_rejected"]],
        "snapshot": snap, "unfrozen_mismatches": unfrozen, "wall_s": round(time.time() - t0),
        "file_sha256_lf": {f: lf_sha(ROOT / f) for f in FROZEN_FILES}, "op_spec_sha256": edit_dsl.spec_sha256(), "contract_sha256": ct.contract_sha256(),
    }
    summary["PASS"] = {"P1": not crashes, "P2": not kc_false_reject, "P3": not newly, "ALL": not crashes and not kc_false_reject and not newly}
    (out / "decisions.json").write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    (out / "known_cases.json").write_text(json.dumps({"known_correct": kc, "known_wrong_on_clean": kw}, indent=1, default=str), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (out / "table.md").write_text(md_table(results) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("n_plans", "coverage", "old_today", "new", "P1_crashes_on_compiled_code", "P2_known_correct", "P2b_known_wrong_on_clean",
                                                 "P3_clean_plans_newly_accepted_that_old_rightly_rejected", "PASS")}, indent=1))


if __name__ == "__main__":
    main()
