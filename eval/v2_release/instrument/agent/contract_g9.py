"""G9 contract: the full rule spec as text the planner sees UP FRONT, plus check_plan(plan, case_dir), usable as a tool before committing.
The behavioural guard (agent/guard_g9.py) is the backstop for what a static check cannot know. No model calls.

Plan schema (1..3 factors; the factorial layout exists only when k >= 2):
{"verdict": "flaw" | "no_flaw",
 "factors": [{"id": "A", "flaw": str, "evidence_line": str, "ops": [ {op ...}, ... ]}, ...],
 "predicted_drop_pp": {"fix_A": n, "fix_B": n, "fix_all": n}   # k == 1: only "fix_all"
 "culprit_ranking": ["A", "B", "interaction"] (ids; "interaction" only when k >= 2),
 "reason": str}
"no_flaw" (factors == []) is a legal answer: the pipeline is already clean."""
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from agent import edit_dsl  # noqa: E402

MAX_FACTORS, MAX_OPS = 3, 3
FACTOR_IDS = ("A", "B", "C")
FORECAST_WORDS = ("forecast", "future", "next period", "next-period", "next epoch", "later period", "later epoch",
                  "later year", "prospective", "temporal", "chronolog", "ahead", "upcoming", "unseen period")  # same list as G7/G8 SPLIT-USE-REQUIRED
TIME_NAME = re.compile(r"(year|date|time|month|week|period|epoch|step|^t$|_t$)", re.I)

RULES = [
    ("R-OPS", "A fix is a list of ops from the frozen list; you never write code. Allowed ops and their parameters: "
              "move_into_fold(step, call) | drop_from_eval(step, call) | replace_split(step, kind, col) | retrain_inside(step). Unknown ops or parameters are rejected."),
    ("R-STEP", "`step` must be a top-level function of train.py (never `load`). `call` must be called by name somewhere in train.py."),
    ("R-FACTORS", "A plan has 1 to 3 factors (ids A, B, C). Give one factor per independent flaw. Do NOT invent a second factor: a one-flaw pipeline gets one factor "
                  "and is measured as a single fix (fix_all). With 2 or 3 factors each factor is also measured alone (factorial). If the pipeline is clean, answer "
                  "verdict 'no_flaw' with no factors."),
    ("R-MOVE", "move_into_fold(step, call): `call` is a resampler (`X, y = call(X, y, ...)`), a selector (`k = call(X, y, ...)` used as X[:, k]) or a fitted transformer "
               "class (`V = Cls(...).fit_transform(X)`) executed at the top level of `step` BEFORE a train/test fold scope. It is re-run inside each fold on training rows only. "
               "Precondition (checked by running the original): rows scored by the model were seen by `call`. Other statement shapes are NOT_APPLICABLE."),
    ("R-DROP", "drop_from_eval(step, call): only for a resampler or a selector that USES THE LABEL and sits on the evaluation path (its rows reach the scored rows, or "
               "synthetic rows are scored). A transformer is never dropped (use move_into_fold)."),
    ("R-SPLIT", "replace_split(step, kind, col): kind is random, group or temporal. group and temporal need `col`, a column of the data. temporal needs a TIME-LIKE column "
                "(name matches year/date/time/month/week/period/epoch/step) AND the excerpt must state a temporal intended use (forecast, future, later period, ...). "
                "A group split inside a CV step needs a `groups` parameter in that step. Postcondition (checked by running it): random = no row both fit and scored; "
                "group = no group both fit and scored; temporal = every training row strictly earlier than every scored row. Precondition: the original must violate that relation."),
    ("R-RETRAIN", "retrain_inside(step): a model fitted once before a `for tr, te in ...` loop and used to predict inside it is refitted on each fold's training rows."),
    ("R-USE-REQUIRED", "If the excerpt states a forecasting / future-period use and the original hold-out is not already temporal, one factor MUST be a temporal "
                       "replace_split of the step that chooses the scored rows. (This rule existed in G7/G8 and was taught only by the rejection text; it is stated here.)"),
    ("R-MODEL", "A fix never changes the model: the scoring model class and its hyperparameter names are compared at runtime between the original and each fixed config; "
                "values that are constants in the source must be equal (values computed by a tuner may differ). Features, the metric and `load` are untouched (no op edits them)."),
    ("R-ROWS", "The number of evaluation rows must equal the original's unless a replace_split op is present; the only other allowed change is removing synthetic rows from the scored set."),
    ("R-NOOP", "Every config must change which rows are fit, scored or seen by an upstream component, and every op must have something to fix in the original. "
               "A fix that changes nothing is rejected, not accepted."),
    ("R-RUN", "Every config is compiled and run once on the case data (smoke profile). A config that crashes, or whose row provenance cannot be traced, is rejected."),
]


def contract_text():
    ops = edit_dsl.OP_SPEC["ops"]
    head = ("You fix an evaluation by naming OPS, not by writing code. The harness compiles each op into train.py and checks the result by running it.\n"
            f"Frozen op list (sha256 {edit_dsl.spec_sha256()}): " + ", ".join(f"{k}({', '.join(v['params'])})" for k, v in ops.items()) + ".\n"
            "Not covered (do not ask for them): " + "; ".join(edit_dsl.OP_SPEC["not_covered"]) + ".\n\nRULES (all enforced; call check_plan before you answer):\n")
    return head + "\n".join(f"{i}. [{r}] {t}" for i, (r, t) in enumerate(RULES, 1)) + "\n\n" + __doc__.split("Plan schema", 1)[1].join(["Plan schema", ""]) if False else \
        head + "\n".join(f"{i}. [{r}] {t}" for i, (r, t) in enumerate(RULES, 1)) + "\n\nPlan schema" + __doc__.split("Plan schema", 1)[1]


def contract_sha256():
    return hashlib.sha256(contract_text().encode("utf-8")).hexdigest()


def forecast_claim(excerpt):
    low = excerpt.lower()
    signals = []
    # Scope negation to a short coordinated phrase, not an entire sentence.
    # 'no group or chronological structure' is negative; 'not X, but forecast Y' is positive.
    coordination = r"(?:a|an|any|group|grouped|entity|spatial|temporal|chronological|forecast|forecasting|prospective|future|or|and|time|based|use)"
    negative = re.compile(r"\b(?:no|not|never|without)\s+(?:" + coordination + r"[\s/-]+){0,6}$")
    for word in FORECAST_WORDS:
        for match in re.finditer(r"\b" + re.escape(word), low):
            prefix = re.split(r"[.;\n]|\b(?:but|however|yet)\b", low[:match.start()])[-1]
            if negative.search(prefix) and not re.search(r"\bnot\s+only\s+", prefix):
                continue
            signals.append(word)
            break
    return signals


def _case(case_dir):
    d = Path(case_dir)
    exc = (d / "excerpt.md").read_text(encoding="utf-8") if (d / "excerpt.md").exists() else ""
    return (d / "train.py").read_text(encoding="utf-8"), exc, (d / "data.csv").open(encoding="utf-8").readline().strip().split(",")


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _orig_temporal(tree, hold_steps):
    """Static hint: a hold-out step of the original already orders by time (compare against a time-like name, TimeSeriesSplit, sort + slice)."""
    d = edit_dsl.defs_of(tree)
    for nm in hold_steps or d:
        fn = d.get(nm)
        if fn is None or nm == "load":
            continue
        for s in ast.walk(fn):
            if isinstance(s, ast.Call) and edit_dsl.fname(s) == "TimeSeriesSplit":
                return True
            if isinstance(s, ast.Compare) and any(isinstance(o, (ast.Lt, ast.LtE, ast.Gt, ast.GtE)) for o in s.ops):
                names = {x.value for x in ast.walk(s) if isinstance(x, ast.Constant) and isinstance(x.value, str)} | {x.id for x in ast.walk(s) if isinstance(x, ast.Name)}
                if any(TIME_NAME.search(n) for n in names):
                    return True
    return False


def check_schema(plan):
    v = []
    if not isinstance(plan, dict):
        return ["R-OPS: plan is not a JSON object"]
    verdict = plan.get("verdict", "flaw")
    if verdict not in ("flaw", "no_flaw"):
        v.append("R-FACTORS: verdict must be 'flaw' or 'no_flaw'")
    facs = plan.get("factors")
    if not isinstance(facs, list):
        return v + ["R-FACTORS: 'factors' must be a list"]
    if verdict == "no_flaw":
        if facs:
            v.append("R-FACTORS: verdict 'no_flaw' must have no factors")
        if not isinstance(plan.get("reason"), str) or not plan["reason"].strip():
            v.append("'reason' must be a non-empty string")
        return v
    if not 1 <= len(facs) <= MAX_FACTORS:
        v.append(f"R-FACTORS: a plan has 1 to {MAX_FACTORS} factors (got {len(facs)})")
    ids = []
    for i, f in enumerate(facs):
        if not isinstance(f, dict):
            v.append(f"factor {i} is not an object")
            continue
        ids.append(f.get("id"))
        if f.get("id") != FACTOR_IDS[i if i < len(FACTOR_IDS) else -1]:
            v.append(f"R-FACTORS: factor {i} must have id {FACTOR_IDS[min(i, 2)]!r}")
        for k in ("flaw", "evidence_line"):
            if not isinstance(f.get(k), str) or not f[k].strip():
                v.append(f"factor {f.get('id')}: '{k}' must be a non-empty string")
        ops = f.get("ops")
        if not isinstance(ops, list) or not 1 <= len(ops) <= MAX_OPS:
            v.append(f"factor {f.get('id')}: 'ops' must be a list of 1 to {MAX_OPS} ops")
        elif not all(isinstance(o, dict) for o in ops):
            v.append(f"factor {f.get('id')}: every op must be an object")
    if not isinstance(plan.get("reason"), str) or not plan["reason"].strip():
        v.append("'reason' must be a non-empty string")
    k = len(facs)
    pd_ = plan.get("predicted_drop_pp")
    need = ["fix_all"] if k == 1 else [f"fix_{i}" for i in ids] + ["fix_all"]
    if not isinstance(pd_, dict) or not all(_num(pd_.get(n)) for n in need):
        v.append(f"R-FACTORS: 'predicted_drop_pp' must be an object with numeric {need}")
    cr = plan.get("culprit_ranking")
    allowed = set(ids) | ({"interaction"} if k >= 2 else set())
    if not isinstance(cr, list) or not cr or not all(x in allowed for x in cr):
        v.append(f"'culprit_ranking' must be a non-empty list drawn from {sorted(allowed)}")
    return v


def check_plan(plan, case_dir, runtime=False, profile=None):
    """Static contract check (fast, no execution) and, with runtime=True, the full behavioural guard (runs every config once).
    -> {"ok": bool, "problems": [str], "layout": str|None, "configs": [names], "notes": [str], "runtime": dict|None}"""
    out = {"ok": False, "problems": [], "layout": None, "configs": [], "notes": [], "runtime": None}
    v = check_schema(plan)
    if v:
        out["problems"] = v
        return out
    if plan.get("verdict") == "no_flaw":
        out.update(ok=True, notes=["no_flaw: no factors; nothing is compiled or run"])
        return out
    src, exc, hdr = _case(case_dir)
    tree = ast.parse(src)
    defs = edit_dsl.defs_of(tree)
    hold = edit_dsl.holdout_steps(tree)
    fc = forecast_claim(exc)
    seen = set()
    temporal_on_hold = False
    for f in plan["factors"]:
        for op in f["ops"]:
            o = op.get("op")
            if o not in edit_dsl.OPS:
                v.append(f"R-OPS: factor {f['id']}: unknown op {o!r} (allowed {list(edit_dsl.OPS)})")
                continue
            want = set(edit_dsl.OP_SPEC["ops"][o]["params"]) | {"op"}
            miss, extra = want - set(op) - ({"col"} if (o == "replace_split" and op.get("kind") == "random") else set()), set(op) - want
            if miss or extra:
                v.append(f"R-OPS: factor {f['id']}: {o} takes {sorted(want - {'op'})}" + (f", missing {sorted(miss)}" if miss else "") + (f", unexpected {sorted(extra)}" if extra else ""))
                continue
            key = json.dumps(op, sort_keys=True)
            if key in seen:
                v.append(f"R-NOOP: factor {f['id']}: the same op appears twice: {key}")
            seen.add(key)
            st = op.get("step")
            if st not in defs or st == "load":
                v.append(f"R-STEP: factor {f['id']}: step {st!r} is not an editable top-level function (steps: {sorted(n for n in defs if n != 'load')})")
                continue
            if "call" in want:
                if not isinstance(op.get("call"), str) or not edit_dsl.calls_in(tree, op["call"]):
                    v.append(f"R-STEP: factor {f['id']}: call {op.get('call')!r} is not called anywhere in train.py")
            if o == "replace_split":
                kd, col = op.get("kind"), op.get("col")
                if kd not in edit_dsl.KINDS:
                    v.append(f"R-SPLIT: factor {f['id']}: kind must be one of {list(edit_dsl.KINDS)}")
                elif kd in ("group", "temporal"):
                    if col not in hdr:
                        v.append(f"R-SPLIT: factor {f['id']}: col {col!r} is not a column of the data (columns: {hdr[:12]}{'...' if len(hdr) > 12 else ''})")
                    elif kd == "temporal":
                        if not TIME_NAME.search(col):
                            v.append(f"R-SPLIT: factor {f['id']}: temporal needs a time-like column; {col!r} is not (no time column, no temporal split)")
                        if not fc:
                            v.append(f"R-SPLIT: factor {f['id']}: the excerpt states no temporal intended use, so a temporal split is not allowed (SPLIT-USE)")
                        if st in hold:
                            temporal_on_hold = True
    if fc and not _orig_temporal(tree, hold) and not temporal_on_hold:
        v.append(f"R-USE-REQUIRED: the excerpt states a forecasting use ({fc[0]!r}) and the original hold-out is not temporal, but no factor is a temporal replace_split "
                 f"of the hold-out step ({sorted(hold) or 'the step that chooses the scored rows'})")
    if v:
        out["problems"] = v
        return out
    comp = edit_dsl.compile_plan(src, plan)
    out["layout"], out["configs"] = comp["layout"], list(comp["configs"])
    for n, c in comp["configs"].items():
        if c["error"]:
            v.append(f"{n}: {c['error']}")
    if v:
        out["problems"] = v
        return out
    out["ok"] = True
    if runtime:
        from agent import guard_g9
        rt = guard_g9.guard_plan(case_dir, plan, profile)
        out["runtime"] = rt
        out["ok"] = rt["decision"] == "ACCEPT"
        out["problems"] = rt["problems"]
    else:
        out["notes"].append("static contract only; the behavioural guard (runtime=True) still runs before any measurement")
    return out
