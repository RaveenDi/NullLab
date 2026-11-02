"""Equivalence of the fast G9 guard (agent/guard_g9.py) with the ORIGINAL implementation (docs/EVAL-14-GUARD-SPEED.md).

REF_SRC below is the complete original agent/guard_g9.py (the frozen file as tagged, sha256 4a084a1c...), kept verbatim as the reference: its Python-set
`analyze`, its `behaviour_check` and its row-id-list worker. The tests compare the current module with it on
  (a) randomized synthetic traces (fixed seeds; shared objects, negative synthetic ids, None row ids, empty sets, NaN columns),
  (b) traces recorded by running BOTH workers on real cases (EHG, ESL, civil war on a subsample) and the full guard_plan result,
  (c) optionally the whole offline replay (set NULLLAB_EQ_REPLAY=1; see the doc, the decision table must match runs_g9_offline/summary.json).
Any difference in a decision, a problem text, a fact, or an analyze field is a bug in the fast guard; never change an expectation here.
"""
import copy
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from agent import guard_g9 as new  # noqa: E402

REF_SRC = r'''"""G9 behavioural guard (design: docs/EVAL-12-G9-DSL.md). Replaces the constructor-name text check of agent/fidelity.py "MODEL unchanged"
with a RUNTIME check: a compiled config is executed on the case data (smoke profile) with recording wrappers on estimators and rows
carry provenance (TracedArray). From the recording we know which rows each model was FIT on, which rows it SCORED, which rows every
upstream fitted component (selector, scaler, resampler, tuner) saw, and which rows the returned evaluation scored.

No model (LLM) calls. The code that runs is compiled by agent/edit_dsl.py from train.py (not model-written). Fail closed: if row
provenance is lost where a decision needs it, the verdict is UNVERIFIABLE (treated as reject), never a silent accept.

Entry points: trace_run, analyze, behaviour_check, guard_config. Worker mode: `python -I guard_g9.py --worker args.json out.json`."""
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent
METHODS = ("fit", "fit_transform", "predict", "predict_proba", "decision_function", "transform", "kneighbors")
SCORE_M = ("predict", "predict_proba", "decision_function")
FIT_M = ("fit", "fit_transform")
MODNAME = "train_g9"


# =====================================================================  worker (runs in a subprocess)
def _worker(args):
    import functools
    import threading
    import numpy as np
    import pandas as pd
    import warnings
    warnings.filterwarnings("ignore")

    class TA(np.ndarray):
        """ndarray carrying one original-row id per row (-1 = row created inside the pipeline)."""
        def __new__(cls, arr, rid):
            o = np.asarray(arr).view(cls)
            o.rid = np.asarray(rid)
            return o

        def __array_finalize__(self, obj):
            r = getattr(obj, "rid", None)
            self.rid = r if (r is not None and self.ndim >= 1 and len(r) == self.shape[0]) else None

        def __getitem__(self, key):
            out = super().__getitem__(key)
            if isinstance(out, TA):
                out.rid = _sel(self.rid, key)
            return out

        def __array_function__(self, func, types, a, kw):
            plain = _unwrap(a)
            kwp = _unwrap(kw)
            res = func(*plain, **kwp)
            if func in (np.concatenate, np.vstack) and a and isinstance(a[0], (list, tuple)):
                parts = a[0]
                axis = kw.get("axis", a[1] if len(a) > 1 else 0)
                if func is np.concatenate and axis not in (0, None):
                    return res
                rids = [getattr(p, "rid", None) if isinstance(p, TA) else None for p in parts]
                if all(r is not None or not isinstance(p, TA) for r, p in zip(rids, parts)):
                    full = [r if r is not None else np.full(len(np.atleast_1d(p)) if np.ndim(p) else 1, -1) for r, p in zip(rids, parts)]
                    return TA(res, np.concatenate(full))
            return res

    def _unwrap(x):
        if isinstance(x, TA):
            return x.view(np.ndarray)
        if isinstance(x, (list, tuple)):
            return type(x)(_unwrap(i) for i in x)
        if isinstance(x, dict):
            return {k: _unwrap(v) for k, v in x.items()}
        return x

    def _sel(rid, key):
        if rid is None:
            return None
        k0 = key[0] if isinstance(key, tuple) and key else key
        if isinstance(key, tuple) and key and key[0] is Ellipsis:
            return rid
        try:
            if isinstance(k0, slice):
                return rid[k0]
            if isinstance(k0, (int, np.integer)):
                return None
            k = np.asarray(_unwrap(k0))
            return rid[k] if k.dtype.kind in "biu" else None
        except Exception:
            return None

    def rids(o):
        if isinstance(o, TA):
            return o.rid
        if isinstance(o, (pd.DataFrame, pd.Series)):
            ix = np.asarray(o.index)
            return ix if ix.dtype.kind in "iu" else None
        return None

    st = threading.local()
    events = []

    def stack_names():
        out, f = [], sys._getframe(2)
        while f is not None:
            if f.f_globals.get("__name__") == MODNAME:
                out.append(f.f_code.co_name)
            f = f.f_back
        return out

    def plain(o):
        return o.view(np.ndarray) if isinstance(o, TA) else o

    def rec(kind, cls_name, obj, X, y_present, params=None, name=None):
        r = rids(X)
        events.append({"i": len(events), "kind": kind, "cls": cls_name, "obj": id(obj), "rid": None if r is None else [int(v) for v in np.asarray(r)],
                       "y": y_present, "stack": stack_names(), "params": params, "fn": name})

    class Rec:
        def __init__(self, cls, meth, orig):
            self.cls, self.meth, self.orig = cls, meth, orig

        def __set_name__(self, owner, name):
            pass

        def __get__(self, obj, owner=None):
            bound = self.orig.__get__(obj, owner) if hasattr(self.orig, "__get__") else self.orig
            if obj is None:
                return bound
            meth, cls = self.meth, self.cls

            @functools.wraps(bound)
            def w(*a, **k):
                depth = getattr(st, "d", 0)
                if depth == 0:
                    X = a[0] if a else k.get("X")
                    yv = a[1] if len(a) > 1 else k.get("y")
                    kind = "fit" if meth in FIT_M else ("score" if meth in SCORE_M else ("transform" if meth == "transform" else "query"))
                    params = None
                    if kind == "fit":
                        try:
                            params = {p: repr(v) for p, v in obj.get_params(deep=False).items()}
                        except Exception:
                            params = {}
                    rec(kind, type(obj).__name__, obj, X, yv is not None, params)
                st.d = depth + 1
                try:
                    return bound(*[plain(x) for x in a], **{kk: plain(v) for kk, v in k.items()})
                finally:
                    st.d = depth
            return w

    from sklearn.utils import all_estimators
    allc = []
    for _, c0 in all_estimators():
        for c in c0.__mro__:
            if c.__module__.startswith("sklearn") and c not in allc:
                allc.append(c)
    for cls in allc:
        for m in METHODS:
            if m in cls.__dict__ and not isinstance(cls.__dict__[m], (property, Rec)):
                try:
                    setattr(cls, m, Rec(cls, m, cls.__dict__[m]))
                except Exception:
                    pass

    def caller_is_train():
        return sys._getframe(2).f_globals.get("__name__") == MODNAME

    o_df, o_se = pd.DataFrame.to_numpy, pd.Series.to_numpy

    def to_np(orig):
        def f(self, *a, **k):
            out = orig(self, *a, **k)
            if sys._getframe(1).f_globals.get("__name__") == MODNAME:
                ix = np.asarray(self.index)
                if ix.dtype.kind in "iu" and getattr(out, "ndim", 0) >= 1 and len(ix) == out.shape[0]:
                    return TA(out, ix)
            return out
        return f
    pd.DataFrame.to_numpy = to_np(o_df)
    pd.Series.to_numpy = to_np(o_se)

    case = Path(args["case_dir"])
    df = pd.read_csv(case / "data.csv")
    src = Path(args["src_path"]).read_text(encoding="utf-8")
    mod = type(sys)(MODNAME)
    mod.__dict__["__name__"] = MODNAME
    sys.modules[MODNAME] = mod
    exec(compile(src, "train_g9.py", "exec"), mod.__dict__)
    for k, v in (args.get("overrides") or {}).items():
        if k in mod.__dict__:
            mod.__dict__[k] = v
    mr = args.get("max_rows")
    if mr and len(df) > mr:
        tgt = mod.__dict__.get("TARGET")
        rng = np.random.default_rng(0)
        pos = np.flatnonzero(df[tgt].to_numpy() == 1) if tgt in df.columns else np.array([], dtype=int)
        pos = pos[:mr // 2]
        rest = np.setdiff1d(np.arange(len(df)), pos)
        keep = np.sort(np.concatenate([pos, rng.choice(rest, mr - len(pos), replace=False)]))
        df = df.iloc[keep]
    for nm in args.get("record_fns") or []:
        if nm in mod.__dict__ and callable(mod.__dict__[nm]):
            orig = mod.__dict__[nm]

            def mk(orig, nm):
                def w(*a, **k):
                    X = a[0] if a else None
                    yv = a[1] if len(a) > 1 else None
                    rec("fn", nm, orig, X, yv is not None, None, nm)
                    return orig(*a, **k)
                return w
            mod.__dict__[nm] = mk(orig, nm)
    out = {"status": "ok", "n_rows": int(len(df))}
    try:
        res = mod.claimed_eval(df.copy(), int(args["seed"]))
        yt = res[0]
        out["E"] = None if rids(yt) is None else [int(v) for v in np.asarray(rids(yt))]
        out["n_eval"] = int(len(yt))
        ys = np.asarray(res[1])
        out["finite"] = bool(np.all(np.isfinite(ys.astype(float))))
        tgt = mod.__dict__.get("TARGET")
        try:  # row ids are trustworthy only if the scored labels equal the original rows' labels at those ids
            Ea = np.asarray(rids(yt))
            m = Ea >= 0
            ref = df[tgt].reindex(Ea[m]).to_numpy().astype(float)
            out["relabelled"] = not bool(np.array_equal(ref, np.asarray(yt).view(np.ndarray)[m].astype(float)))
        except Exception:
            out["relabelled"] = None
    except Exception as e:  # a crash of compiled code is a result, reported with its text
        import traceback
        out = {"status": "crash", "error": f"{type(e).__name__}: {e}", "tb": traceback.format_exc()[-1500:]}
    out["events"] = events
    cols = {}
    for c in args.get("cols") or []:
        if c in df.columns:
            cols[c] = [float(v) for v in df[c].to_numpy()]
    out["col_index"] = [int(v) for v in df.index]
    out["cols"] = cols
    Path(args["out_path"]).write_text(json.dumps(out), encoding="utf-8")


# =====================================================================  parent: run + analyse
_CACHE = {}
_LK = threading.Lock()
_KLOCKS = {}


def trace_run(train_src, case_dir, seed=42, profile=None, record_fns=(), cols=(), timeout=600):
    """Execute `train_src` (a compiled config or the original, with claimed_eval) in a fresh isolated interpreter and return the trace dict."""
    profile = profile or {}
    case_dir = Path(case_dir).resolve()
    key = (hashlib.sha256(train_src.encode()).hexdigest(), str(case_dir), seed, json.dumps(profile, sort_keys=True), tuple(sorted(record_fns)), tuple(sorted(cols)))
    with _LK:
        lock = _KLOCKS.setdefault(key, threading.Lock())
    with lock:
        if key in _CACHE:
            return _CACHE[key]
        t = _trace_uncached(train_src, case_dir, seed, profile, record_fns, cols, timeout)
        _CACHE[key] = t
        return t


def _trace_uncached(train_src, case_dir, seed, profile, record_fns, cols, timeout):
    with tempfile.TemporaryDirectory(prefix="g9trace_") as td:
        td = Path(td)
        (td / "src.py").write_text(train_src, encoding="utf-8")
        args = {"case_dir": str(case_dir), "src_path": str(td / "src.py"), "out_path": str(td / "out.json"), "seed": seed,
                "overrides": profile.get("overrides"), "max_rows": profile.get("max_rows"), "record_fns": list(record_fns), "cols": list(cols)}
        (td / "args.json").write_text(json.dumps(args), encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT", "WINDIR")}
        env["OMP_NUM_THREADS"] = "1"
        env["PYTHONHASHSEED"] = "0"
        try:
            r = subprocess.run([sys.executable, "-I", str(HERE), "--worker", str(td / "args.json")], cwd=str(td), env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "events": []}
        if not (td / "out.json").exists():
            return {"status": "crash", "error": "worker produced no output", "tb": (r.stderr or "")[-1200:], "events": []}
        return json.loads((td / "out.json").read_text(encoding="utf-8"))


def _arr(x):
    return None if x is None else set(v for v in x if v >= 0)


def analyze(trace):
    """Per scoring event: fit rows of the same instance, scored rows, upstream context rows. Pure function of the trace."""
    ev = trace.get("events", [])
    E = trace.get("E")
    Eset = _arr(E)
    out = {"tracked": E is not None, "n_eval": trace.get("n_eval"), "E_synth": (sum(1 for v in E if v < 0) if E else 0), "scores": [], "models": {},
           "fn_calls": {}, "untracked_events": 0}
    last_fit = {}
    prev_end = -1
    comp_latest = {}
    for e in ev:
        rows = _arr(e["rid"])
        if e["rid"] is None and e["kind"] in ("fit", "score", "fn"):
            out["untracked_events"] += 1
        if e["kind"] == "fit":
            last_fit[e["obj"]] = e
            comp_latest[("fit", e["cls"])] = e
        elif e["kind"] == "fn":
            comp_latest[("fn", e["cls"])] = e
            out["fn_calls"].setdefault(e["cls"], 0)
            out["fn_calls"][e["cls"]] += 1
        elif e["kind"] == "score":
            fit = last_fit.get(e["obj"])
            is_eval = rows is not None and Eset is not None and bool(rows & Eset)
            ctx = []
            for ee in ev[prev_end + 1:e["i"]]:
                if ee["obj"] != e["obj"] and ee["kind"] in ("fit", "fn", "score"):
                    ctx.append(ee)
            keys = {}
            for kk, ee in comp_latest.items():
                if ee["obj"] != e["obj"] and ee["i"] < e["i"]:
                    keys[kk] = ee
            for ee in ctx:
                keys.setdefault((ee["kind"], ee["cls"], ee["i"]), ee)
            ctx_rows = {}
            for kk, ee in keys.items():
                name = kk[1]
                r = _arr(ee["rid"])
                if ee["kind"] == "score":  # an upstream (tuning) model used these rows' labels via scoring too
                    continue
                ctx_rows.setdefault(name, set())
                if r is None:
                    ctx_rows[name] = None
                elif ctx_rows[name] is not None:
                    ctx_rows[name] |= r
            rec = {"i": e["i"], "obj": e["obj"], "cls": e["cls"], "eval": is_eval, "stack": e["stack"],
                   "S": rows, "S_untracked": rows is None, "R": None if fit is None else _arr(fit["rid"]), "fit_i": None if fit is None else fit["i"],
                   "params": None if fit is None else fit["params"], "ctx": ctx_rows}
            out["scores"].append(rec)
            if is_eval:
                prev_end = e["i"]
    return out


def model_signature(an):
    """{class: params} for models that scored evaluation rows (params at their latest fit)."""
    sig = {}
    for s in an["scores"]:
        if s["eval"] and s["params"] is not None:
            sig.setdefault(s["cls"], []).append(s["params"])
    return sig


def contamination(an, key=None):
    """Rows scored by an evaluation model that an upstream component (or the model itself) also saw. -> dict."""
    res = {"self": 0, "ctx": {}, "n_eval_events": 0, "untracked": 0}
    for s in an["scores"]:
        if not s["eval"]:
            continue
        res["n_eval_events"] += 1
        if s["S"] is None or (s["R"] is None and s["fit_i"] is not None):
            res["untracked"] += 1
            continue
        if s["R"] is not None:
            res["self"] += len(s["R"] & s["S"])
        for name, rows in s["ctx"].items():
            if rows is None:
                res["untracked"] += 1
            else:
                res["ctx"][name] = res["ctx"].get(name, 0) + len(rows & s["S"])
    return res


def _col(trace, name):
    ix, v = trace.get("col_index"), (trace.get("cols") or {}).get(name)
    return None if v is None else dict(zip(ix, v))


def relation_violations(an, trace, kind, col, scope_step=None):
    """Count (train, test) pairs of evaluation (or in-scope) models violating the relation implied by `kind`."""
    bad, total, untracked = 0, 0, 0
    cm = _col(trace, col) if col else None
    for s in an["scores"]:
        in_scope = (scope_step in s["stack"]) if scope_step else s["eval"]
        if not in_scope:
            continue
        if s["S"] is None or s["R"] is None:
            untracked += 1
            continue
        total += 1
        if kind == "random":
            bad += bool(s["R"] & s["S"])
        elif cm is None:
            untracked += 1
        elif kind == "group":
            bad += bool({cm[r] for r in s["R"]} & {cm[r] for r in s["S"]})
        else:
            tr_max = max((cm[r] for r in s["R"]), default=None)
            te_min = min((cm[r] for r in s["S"]), default=None)
            bad += not (tr_max is not None and te_min is not None and tr_max < te_min)
    return {"bad": bad, "total": total, "untracked": untracked}


def _ctor_consts(src):
    """{class name: {kw: is_constant}} from constructor calls in the original source (for 'tuned values may differ')."""
    out = {}
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call):
            nm = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", "")
            if nm[:1].isupper():
                out.setdefault(nm, {})
                for k in n.keywords:
                    if k.arg:
                        out[nm][k.arg] = isinstance(k.value, ast.Constant) and out[nm].get(k.arg, True)
    return out


def _structure_sig(an):
    h = lambda x: -1 if x is None else hash(frozenset(x))  # noqa: E731  the exact row sets, not only their sizes
    return sorted((s["cls"], h(s["R"]), h(s["S"]), s["eval"], tuple(sorted((k, h(v)) for k, v in s["ctx"].items()))) for s in an["scores"])


def behaviour_check(orig_trace, fix_trace, ops, orig_src, expect_resize=False, hold_steps=()):
    """Compare one fixed config with the original. -> {"decision": ACCEPT|REJECT|UNVERIFIABLE, "problems": [...], "facts": {...}}.
    expect_resize: a replace_split op is present (evaluation sample size may change)."""
    P, U, facts = [], [], {}
    if fix_trace.get("status") != "ok":
        return {"decision": "REJECT", "problems": [f"CRASH: compiled config did not run ({fix_trace.get('status')}: {fix_trace.get('error', '')[:300]})"], "facts": {}, "crash": True}
    if orig_trace.get("status") != "ok":
        return {"decision": "UNVERIFIABLE", "problems": [f"the original did not run in the smoke profile ({orig_trace.get('status')}: {orig_trace.get('error', '')[:200]})"], "facts": {}}
    a0, a1 = analyze(orig_trace), analyze(fix_trace)
    if not a0["tracked"] or not a1["tracked"]:
        U.append("row provenance of the returned evaluation rows was lost; fit/score rows cannot be verified")
    # MODEL
    s0, s1 = model_signature(a0), model_signature(a1)
    consts = _ctor_consts(orig_src)
    if set(s0) != set(s1):
        P.append(f"MODEL: scoring model class set changed {sorted(s0)} -> {sorted(s1)}")
    else:
        for cls in s0:
            keys0 = {frozenset(p) for p in s0[cls]}
            keys1 = {frozenset(p) for p in s1[cls]}
            if keys0 != keys1:
                P.append(f"MODEL: hyperparameter names of {cls} changed")
                continue
            for pn in s0[cls][0]:
                v0 = {p[pn] for p in s0[cls]}
                v1 = {p[pn] for p in s1[cls]}
                if v0 != v1 and consts.get(cls, {}).get(pn, True):
                    P.append(f"MODEL: {cls}.{pn} differs at runtime ({sorted(v0)[:2]} -> {sorted(v1)[:2]}) and is a constant in the source (not a tuned value)")
    # SAMPLE SIZE
    syn0 = a0["E_synth"]
    n0 = orig_trace.get("n_eval")
    if not expect_resize and n0 is not None and fix_trace.get("n_eval") not in (n0, n0 - syn0):
        P.append(f"SAMPLE SIZE: evaluation rows {n0} -> {fix_trace.get('n_eval')} but no replace_split op is declared "
                 f"(removing {syn0} synthetic scored rows is the only allowed change)")
    c0, c1 = contamination(a0), contamination(a1)
    facts.update({"orig_contam": c0, "fix_contam": c1, "E_synth_orig": a0["E_synth"], "E_synth_fix": a1["E_synth"],
                  "model": {k: v[0] for k, v in s1.items()}})
    if c1["untracked"] or c0["untracked"]:
        U.append(f"{c0['untracked']}+{c1['untracked']} evaluation events had untracked row provenance")
    # NOOP
    if _structure_sig(a0) == _structure_sig(a1) and a0["E_synth"] == a1["E_synth"] and orig_trace.get("n_eval") == fix_trace.get("n_eval") \
            and sorted(a0["fn_calls"].items()) == sorted(a1["fn_calls"].items()):
        P.append("NOOP: the fit/score structure is identical to the original; this fix changes which rows are fit or scored by nothing")
    # per-op postconditions
    for op in ops:
        o = op["op"]
        if o == "move_into_fold":
            name = op["call"]
            before = _ctx_over(c0, name, a0)
            after = _ctx_over(c1, name, a1)
            if before == 0 and a0["E_synth"] == 0:
                P.append(f"PRECONDITION move_into_fold({name}): in the original no evaluation row was seen by '{name}' (nothing to move; the original is already fold-clean for this step)")
            if after > 0:
                P.append(f"POST move_into_fold({name}): after the fix '{name}' still saw {after} rows that the model then scored")
            if a1["fn_calls"].get(name, 0) + _count_cls(fix_trace, name) == 0:
                P.append(f"POST move_into_fold({name}): '{name}' is never called after the fix (that is a drop, use drop_from_eval)")
            facts[f"{name}_overlap"] = {"before": before, "after": after}
        elif o == "drop_from_eval":
            name = op["call"]
            n0 = a0["fn_calls"].get(name, 0) + _count_cls(orig_trace, name)
            if n0 == 0:
                P.append(f"PRECONDITION drop_from_eval({name}): '{name}' is never called in the original run")
            else:
                evs = [e for e in orig_trace["events"] if e["cls"] == name and e["kind"] in ("fn", "fit")]
                if not any(e["y"] for e in evs):
                    P.append(f"PRECONDITION drop_from_eval({name}): '{name}' does not use the label (only a label-using resampler or selector may be dropped)")
                before = _ctx_over(c0, name, a0)
                if before == 0 and a0["E_synth"] == 0:
                    P.append(f"PRECONDITION drop_from_eval({name}): '{name}' is not on the evaluation path (no scored row passed through it and no scored row is synthetic)")
            if a1["fn_calls"].get(name, 0) + _count_cls(fix_trace, name) > 0:
                P.append(f"POST drop_from_eval({name}): '{name}' is still called after the fix")
            if a1["E_synth"] > 0:
                P.append("POST drop_from_eval: synthetic rows are still scored")
        elif o == "replace_split":
            v0 = relation_violations(a0, orig_trace, op["kind"], op.get("col"), None if op["step"] in hold_steps else op["step"])
            v1 = relation_violations(a1, fix_trace, op["kind"], op.get("col"), None if op["step"] in hold_steps else op["step"])
            facts[f"split_{op['kind']}"] = {"before": v0, "after": v1}
            if op["kind"] in ("group", "temporal") and (orig_trace.get("relabelled") is not False or fix_trace.get("relabelled") is not False):
                U.append(f"replace_split({op['kind']}): row ids were rebuilt inside the pipeline (reset_index / reordering / row drop), so column '{op.get('col')}' cannot be mapped to the scored rows")
                continue
            if v1["untracked"] or v0["untracked"]:
                U.append(f"replace_split({op['kind']}): row provenance missing for {v0['untracked']}+{v1['untracked']} events")
            if v1["total"] == 0:
                U.append("replace_split: no scored model found in scope")
            if v0["bad"] == 0 and v0["total"] > 0 and not v0["untracked"]:
                P.append(f"PRECONDITION replace_split({op['kind']}): the original split already satisfies the {op['kind']} relation in all {v0['total']} train/test pairs (nothing to replace)")
            if v1["bad"] > 0:
                P.append(f"POST replace_split({op['kind']}): {v1['bad']} of {v1['total']} train/test pairs still violate the {op['kind']} relation"
                         + (" (training rows must all be strictly earlier than the scored rows)" if op["kind"] == "temporal" else ""))
        elif o == "retrain_inside":
            if c0["self"] == 0 and not any(s["eval"] and s["R"] is None for s in a0["scores"]):
                P.append("PRECONDITION retrain_inside: in the original no scoring model had seen the rows it scored")
            if c1["self"] > 0:
                P.append(f"POST retrain_inside: {c1['self']} scored rows were still in the fitted model's training rows")
    dec = "REJECT" if P else ("UNVERIFIABLE" if U else "ACCEPT")
    return {"decision": dec, "problems": P + [f"UNVERIFIABLE: {u}" for u in U], "facts": facts}


def _ctx_over(c, name, an):
    return c["ctx"].get(name, 0)


def _count_cls(trace, name):
    return sum(1 for e in trace.get("events", []) if e["cls"] == name and e["kind"] in ("fit", "fn"))


# =====================================================================  plan-level orchestration
def _header(case_dir):
    with open(Path(case_dir) / "data.csv", encoding="utf-8") as f:
        return f.readline().strip().split(",")


def _op_cols(plan):
    return sorted({op["col"] for f in plan["factors"] for op in f["ops"] if op.get("col")})


def _op_fns(plan):
    return sorted({op["call"] for f in plan["factors"] for op in f["ops"] if op.get("call")})


def guard_plan(case_dir, plan, profile=None, seed=42):
    """Compile every config of a (statically valid) plan and run the behavioural check on each. -> dict with per-config results and an overall
    decision: ACCEPT (every config ACCEPT), REJECT (any REJECT/crash/compile error), UNVERIFIABLE (otherwise)."""
    sys.path.insert(0, str(ROOT))
    from agent import edit_dsl
    case_dir = Path(case_dir)
    src = (case_dir / "train.py").read_text(encoding="utf-8")
    comp = edit_dsl.compile_plan(src, plan)
    cols, fns = _op_cols(plan), _op_fns(plan)
    orig_src = src + edit_dsl.CONTROLLED
    orig = trace_run(src, case_dir, seed, profile, fns, cols)
    res = {"layout": comp["layout"], "configs": {}}
    worst = "ACCEPT"
    for name, c in comp["configs"].items():
        if c["error"]:
            res["configs"][name] = {"decision": "REJECT", "problems": [c["error"]], "compile_error": True}
            worst = "REJECT"
            continue
        tr = trace_run(c["src"], case_dir, seed, profile, fns, cols)
        r = behaviour_check(orig, tr, c["ops"], src, expect_resize=any(o["op"] == "replace_split" for o in c["ops"]), hold_steps=edit_dsl.holdout_steps(ast.parse(src)))
        res["configs"][name] = r
        if r["decision"] == "REJECT":
            worst = "REJECT"
        elif r["decision"] == "UNVERIFIABLE" and worst == "ACCEPT":
            worst = "UNVERIFIABLE"
    res["decision"] = worst
    res["problems"] = [f"{n}: {p}" for n, r in res["configs"].items() for p in r["problems"]]
    res["crash"] = any(r.get("crash") for r in res["configs"].values())
    return res


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--worker":
        _worker(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
'''



@pytest.fixture(scope="session")
def ref(tmp_path_factory):
    d = tmp_path_factory.mktemp("guard_ref")
    f = d / "guard_g9.py"
    f.write_text(REF_SRC, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("guard_g9_reference", f)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m.ROOT = ROOT  # guard_plan imports agent.edit_dsl from the repo
    return m


# ------------------------------------------------------------------ helpers
def fs(x):
    return None if x is None else frozenset(int(v) for v in x)


def norm(an):
    """Plain, order-preserving form of an analyze() result (row sets -> frozensets; dict key ORDER kept as a list)."""
    out = {k: v for k, v in an.items() if k != "scores"}
    out["scores"] = [{**s, "S": fs(s["S"]), "R": fs(s["R"]), "ctx": [(k, fs(v)) for k, v in s["ctx"].items()]} for s in an["scores"]]
    return out


def norm_noobj(an):
    n = norm(an)
    n["scores"] = [{k: v for k, v in s.items() if k != "obj"} for s in n["scores"]]
    return n


def as_worker_trace(tr, mode):
    """The same trace in the form the new worker ships ('packed': pooled bitsets) or with numpy id arrays ('ndarray'); 'list' = unchanged."""
    if mode == "list":
        return tr
    tr = dict(tr)
    pool, evs = {}, []
    for e in tr["events"]:
        e = dict(e)
        r = e["rid"]
        if r is not None:
            if mode == "ndarray":
                e["rid"] = np.asarray(r, dtype=np.int64)
            else:
                ids = sorted({int(v) for v in r if v >= 0})
                pres = np.zeros(max(ids) + 1 if ids else 0, np.uint8)
                if ids:
                    pres[ids] = 1
                bits = np.packbits(pres, bitorder="little")
                key = bits.tobytes()
                if key not in pool:
                    pool[key] = new._Packed(bits)
                e["rid"] = pool[key]
        evs.append(e)
    tr["events"] = evs
    return tr


def run(fn, *a, **k):
    try:
        return ("ok", fn(*a, **k))
    except Exception as ex:  # noqa: BLE001  the exception itself is part of the behaviour
        return ("raise", type(ex).__name__)  # the message may name an arbitrary one of several missing keys (set order)


CLS = ["M", "N", "sel", "over", "T"]
STACKS = [[], ["s"], ["claimed_eval", "s"], ["claimed_eval"]]


def rand_rows(rng, U, scale, shared):
    r = rng.random()
    if r < 0.08:
        return None
    if shared and r < 0.3:
        return shared[int(rng.integers(len(shared)))]
    if r < 0.35:
        return []
    ids = [int(v) * scale for v in rng.choice(U, size=int(rng.integers(0, U + 1)), replace=False)]
    if rng.random() < 0.25:
        ids += [-1] * int(rng.integers(1, 4))
    rng.shuffle(ids)
    return ids


def gen_trace(seed, nan_col=False):
    rng = np.random.default_rng(seed)
    U = int(rng.choice([6, 20, 70, 150]))
    scale = int(rng.choice([1, 1, 1, 17]))
    n_obj = int(rng.integers(1, 7))
    obj_cls = {o: CLS[int(rng.integers(0, 3))] if rng.random() < 0.8 else CLS[o % len(CLS)] for o in range(n_obj)}
    evs, shared = [], []
    for i in range(int(rng.integers(0, 45))):
        kind = str(rng.choice(["fit", "score", "fn", "transform", "query"], p=[0.3, 0.32, 0.15, 0.13, 0.1]))
        if kind == "fn":
            obj, cls = 100 + int(rng.integers(0, 3)), str(rng.choice(["sel", "over"]))
        else:
            obj = int(rng.integers(0, n_obj))
            cls = obj_cls[obj]
        rid = rand_rows(rng, U, scale, shared)
        if rid is not None:
            shared.append(rid)
        evs.append({"i": i, "kind": kind, "cls": cls, "obj": obj, "rid": rid, "y": bool(rng.integers(0, 2)),
                    "stack": list(STACKS[int(rng.integers(0, len(STACKS)))]), "params": {"a": str(int(rng.integers(0, 2)))} if kind == "fit" else None, "fn": None})
    r = rng.random()
    E = None if r < 0.05 else ([] if r < 0.1 else rand_rows(rng, U, scale, []) or [0])
    idx = [i * scale for i in range(U)]
    t = [float(rng.integers(0, 12)) for _ in idx]
    if nan_col:
        t[int(rng.integers(0, U))] = float("nan")
    return {"status": "ok", "events": evs, "E": E, "n_eval": int(rng.integers(0, 40)) if E is None else len(E), "relabelled": False,
            "col_index": idx, "cols": {"t": t, "g": [float(int(rng.integers(0, 4))) for _ in idx]}}


def mutate(tr, seed):
    rng = np.random.default_rng(seed)
    out = copy.deepcopy(tr)
    if rng.random() < 0.3:
        return out
    U = max(8, len(tr["col_index"]))
    for e in out["events"]:
        if rng.random() < 0.3:
            e["rid"] = rand_rows(rng, U, 1, []) if e["rid"] is None or rng.random() < 0.7 else e["rid"]
    if rng.random() < 0.5:
        out["E"] = rand_rows(rng, U, 1, []) or [0]
        out["n_eval"] = len(out["E"])
    return out


OPS = [{"op": "move_into_fold", "step": "s", "call": "sel"}, {"op": "move_into_fold", "step": "s", "call": "over"},
       {"op": "drop_from_eval", "step": "s", "call": "over"}, {"op": "drop_from_eval", "step": "s", "call": "sel"},
       {"op": "replace_split", "step": "s", "kind": "random", "col": None}, {"op": "replace_split", "step": "claimed_eval", "kind": "group", "col": "g"},
       {"op": "replace_split", "step": "s", "kind": "temporal", "col": "t"}, {"op": "replace_split", "step": "claimed_eval", "kind": "temporal", "col": "t"},
       {"op": "retrain_inside", "step": "s"}]


def check_analysis(ref, tr, label):
    want = run(ref.analyze, tr)
    for mode in ("list", "packed", "ndarray"):
        got = run(new.analyze, as_worker_trace(tr, mode))
        assert want[0] == got[0], (label, mode, want[:3], got[:3])
        if want[0] == "ok":
            assert norm(want[1]) == norm(got[1]), (label, mode)
            a_ref, a_new = want[1], got[1]
            assert ref.model_signature(a_ref) == new.model_signature(a_new), (label, mode)
            assert ref.contamination(a_ref) == new.contamination(a_new), (label, mode)
            for kind, col, scope in (("random", None, None), ("group", "g", None), ("temporal", "t", None), ("temporal", "t", "s"), ("group", "g", "claimed_eval")):
                r1, r2 = run(ref.relation_violations, a_ref, tr, kind, col, scope), run(new.relation_violations, a_new, tr, kind, col, scope)
                assert r1 == r2, (label, mode, kind, scope, r1, r2)


# ------------------------------------------------------------------ (a) synthetic traces
def test_analyze_equivalent_on_random_traces(ref):
    for seed in range(400):
        check_analysis(ref, gen_trace(seed), f"seed {seed}")


def test_analyze_equivalent_with_nan_column_and_missing_ids(ref):
    for seed in range(120):
        check_analysis(ref, gen_trace(10_000 + seed, nan_col=True), f"nan seed {seed}")
    for seed in range(60):  # a row id that is not in the column index: both raise the same KeyError
        tr = gen_trace(20_000 + seed)
        tr["col_index"], tr["cols"] = tr["col_index"][:-3], {k: v[:-3] for k, v in tr["cols"].items()}
        check_analysis(ref, tr, f"missing seed {seed}")


def test_behaviour_check_equivalent_on_random_pairs(ref):
    counts = {}
    for seed in range(500):
        a = gen_trace(30_000 + seed)
        b = mutate(a, seed)
        rng = np.random.default_rng(seed)
        ops = [OPS[int(i)] for i in rng.choice(len(OPS), size=int(rng.integers(0, 3)), replace=False)]
        kw = {"expect_resize": bool(rng.integers(0, 2)), "hold_steps": ({"s"} if rng.random() < 0.5 else set())}
        want = run(ref.behaviour_check, a, b, ops, "M(a=1)\nN(b=v)\n", **kw)
        for mode in ("list", "packed", "ndarray"):
            got = run(new.behaviour_check, as_worker_trace(a, mode), as_worker_trace(b, mode), ops, "M(a=1)\nN(b=v)\n", **kw)
            assert want == got, (seed, mode, want, got)
        d = want[1]["decision"] if want[0] == "ok" else want[1]
        counts[d] = counts.get(d, 0) + 1
    assert counts.get("ACCEPT", 0) > 0 and counts.get("REJECT", 0) > 0, counts  # the generator reaches the interesting decisions
    print("random pair decisions:", counts)


def test_special_decisions_and_fallback_paths(ref):
    # row ids above the packed-universe limit and event indices that differ from positions take the original set implementation
    big = 60_000_000
    tr = {"status": "ok", "events": [{"i": 0, "kind": "fit", "cls": "M", "obj": 1, "rid": [1, 2, big], "y": True, "stack": [], "params": {"a": "1"}, "fn": None},
                                     {"i": 1, "kind": "score", "cls": "M", "obj": 1, "rid": [2, big], "y": True, "stack": [], "params": None, "fn": None}],
          "E": [2, big], "n_eval": 2, "relabelled": False, "col_index": [], "cols": {}}
    assert norm(ref.analyze(tr)) == norm(new.analyze(tr))
    tr2 = copy.deepcopy(gen_trace(5))
    for e in tr2["events"]:
        e["i"] += 3
    assert norm(ref.analyze(tr2)) == norm(new.analyze(tr2))


def test_rowset_behaves_like_a_set():
    rng = np.random.default_rng(1)
    for _ in range(200):
        a, b = (set(int(v) for v in rng.choice(90, size=int(rng.integers(0, 60)), replace=False)) for _ in range(2))

        def rs(s):
            pres = np.zeros(int(rng.integers(max(s, default=0) + 1, max(s, default=0) + 40)), np.uint8)
            pres[list(s)] = 1
            return new.RowSet(np.packbits(pres, bitorder="little"))
        x, y = rs(a), rs(b)
        assert len(x) == len(a) and set(x) == a and bool(x) == bool(a)
        assert (x & y) == (a & b) and (x | y) == (a | b) and set(x & y) == a & b and len(x & y) == len(a & b)
        assert (x == y) == (a == b) and (x == a) and (hash(x) == hash(rs(a)))
        assert all((v in x) == (v in a) for v in range(100)) and -1 not in x and (x & b) == (a & b) and (a & y) == (a & b)


# ------------------------------------------------------------------ (b) real worker traces
def canon_trace(tr):
    """Trace fields the analysis can read, with object ids renumbered by first appearance and row ids as frozensets."""
    omap = {}
    evs = []
    for e in tr["events"]:
        r = e["rid"]
        if r is not None and not isinstance(r, list):
            r = list(new.RowSet(r.b))
        e = {**e, "params": e["params"] and {k: re.sub(r" at 0x[0-9A-Fa-f]+", "", v) for k, v in e["params"].items()}}  # repr() of a function holds its address
        evs.append({**{k: v for k, v in e.items() if k not in ("obj", "rid")}, "obj": omap.setdefault(e["obj"], len(omap)),
                    "rid": None if r is None else frozenset(int(v) for v in r if v >= 0)})
    return {**{k: v for k, v in tr.items() if k not in ("events", "rid_pool")}, "events": evs}


REAL = ROOT / "real"
HAVE = all((REAL / c / "data.csv").exists() for c in ("ehg_disguised", "ehg_disguised_clean", "esl_selection", "civilwar_disguised", "civilwar_disguised_clean"))
MOVE = {"op": "move_into_fold", "step": "claimed_eval", "call": "oversample"}
DROP = {"op": "drop_from_eval", "step": "claimed_eval", "call": "oversample"}
TEMP = {"op": "replace_split", "step": "split_rows", "kind": "temporal", "col": "epoch"}
RAND = {"op": "replace_split", "step": "split_rows", "kind": "random", "col": None}
SCREEN = {"op": "move_into_fold", "step": "claimed_eval", "call": "screen"}
REAL_CASES = [("ehg_disguised", MOVE, {"overrides": {"N_TREES": 10}}), ("ehg_disguised", DROP, {"overrides": {"N_TREES": 10}}),
              ("ehg_disguised_clean", MOVE, {"overrides": {"N_TREES": 10}}), ("esl_selection", SCREEN, {"overrides": {"N_TREES": 10}}),
              ("civilwar_disguised", TEMP, {"overrides": {"N_TREES": 4}, "max_rows": 1500}), ("civilwar_disguised", RAND, {"overrides": {"N_TREES": 4}, "max_rows": 1500}),
              ("civilwar_disguised_clean", TEMP, {"overrides": {"N_TREES": 4}, "max_rows": 1500})]


def facts_compatible(w, g):
    """Equal, except that a `ctx` mapping of the new guard may hold extra components or larger counts. The original keys objects by id(), which CPython reuses after a
    temporary estimator is freed, so a run could silently drop a component (e.g. NearestNeighbors) from the context; the new worker never reuses keys."""
    if isinstance(w, dict) and isinstance(g, dict):
        if w.keys() != g.keys():
            return False
        return all((set(w[k]) <= set(g[k]) and all(w[k][c] <= g[k][c] for c in w[k])) if k == "ctx" and isinstance(w[k], dict) else facts_compatible(w[k], g[k]) for k in w)
    return w == g


@pytest.mark.skipif(not HAVE, reason="gitignored real/*/data.csv absent")
@pytest.mark.parametrize("case,op,prof", REAL_CASES, ids=[f"{c}-{o['op']}-{o.get('kind', '')}" for c, o, _ in REAL_CASES])
def test_real_traces_and_guard_plan_equivalent(ref, case, op, prof):
    d = REAL / case
    plan = {"factors": [{"id": "A", "ops": [op]}]}
    want, got = ref.guard_plan(d, plan, prof), new.guard_plan(d, plan, prof)
    assert (want["decision"], want["problems"], want["crash"], want["layout"]) == (got["decision"], got["problems"], got["crash"], got["layout"])
    assert want["configs"].keys() == got["configs"].keys()
    for name, rw in want["configs"].items():
        rg = got["configs"][name]
        assert (rw["decision"], rw["problems"]) == (rg["decision"], rg["problems"])
        assert facts_compatible(rw.get("facts"), rg.get("facts")), (rw.get("facts"), rg.get("facts"))
    # the traces themselves: both workers record the same events and the same row sets; analyze() agrees on both representations
    from agent import edit_dsl
    src = (d / "train.py").read_text(encoding="utf-8")
    cols, fns = new._op_cols(plan), new._op_fns(plan)
    comp = edit_dsl.compile_plan(src, plan)
    for text in [src] + [c["src"] for c in comp["configs"].values() if not c["error"]]:
        t_ref = ref.trace_run(text, d, 42, prof, fns, cols)
        t_new = new.trace_run(text, d, 42, prof, fns, cols)
        c_ref, c_new = canon_trace(t_ref), canon_trace(t_new)
        assert [{k: v for k, v in e.items() if k != "obj"} for e in c_ref["events"]] == [{k: v for k, v in e.items() if k != "obj"} for e in c_new["events"]]
        assert {k: v for k, v in c_ref.items() if k != "events"} == {k: v for k, v in c_new.items() if k != "events"}
        # object identity: the original keys objects by id(), which the interpreter REUSES once a temporary estimator is freed (two models then look like
        # one). The new worker's keys are never reused, so its partition may only be FINER than the original's, and the analysis must still agree.
        for i, e in enumerate(c_ref["events"]):
            for j in range(i):
                assert not (c_new["events"][i]["obj"] == c_new["events"][j]["obj"] and e["obj"] != c_ref["events"][j]["obj"])
        a_ref, a_new = norm_noobj(ref.analyze(t_ref)), norm_noobj(new.analyze(t_new))
        assert {k: v for k, v in a_ref.items() if k != "scores"} == {k: v for k, v in a_new.items() if k != "scores"}
        assert len(a_ref["scores"]) == len(a_new["scores"])
        for x, y in zip(a_ref["scores"], a_new["scores"]):
            assert {k: v for k, v in x.items() if k != "ctx"} == {k: v for k, v in y.items() if k != "ctx"}
            cx, cy = dict(x["ctx"]), dict(y["ctx"])  # events the original's reused ids hid may only ADD rows / components to the new context
            assert set(cx) <= set(cy) and all((cx[k] is None and cy[k] is None) if cx[k] is None else (cy[k] is None or cx[k] <= cy[k]) for k in cx)
        assert norm_noobj(ref.analyze(t_ref)) == norm_noobj(new.analyze(t_ref))  # the new analyze on the original list-format trace too
    print(case, op["op"], want["decision"], "events", len(t_new["events"]))


# ------------------------------------------------------------------ (c) offline replay (every saved plan); slow, opt-in
@pytest.mark.skipif(os.environ.get("NULLLAB_EQ_REPLAY") != "1" or not HAVE, reason="set NULLLAB_EQ_REPLAY=1 (about 3-6 min)")
def test_offline_replay_decisions_reproduced(tmp_path):
    import subprocess
    out = tmp_path / "replay"
    r = subprocess.run([sys.executable, "-m", "eval.validate_dsl_replay", "--out", str(out), "--allow-unfrozen"], cwd=str(ROOT), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    want = json.loads((ROOT / "runs_g9_offline" / "summary.json").read_text(encoding="utf-8"))
    got = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    for k in ("n_plans", "coverage", "old_today", "new", "crosstab_old_new_all", "crosstab_old_new_expressible", "P1_crashes_on_compiled_code", "P2_known_correct",
              "P2b_known_wrong_on_clean", "P3_clean_plans_newly_accepted_that_old_rightly_rejected", "PASS"):
        assert got[k] == want[k], k
    w = {x["id"]: (x["new"]["decision"], x["new"]["problems"]) for x in json.loads((ROOT / "runs_g9_offline" / "decisions.json").read_text(encoding="utf-8"))}
    g = {x["id"]: (x["new"]["decision"], x["new"]["problems"]) for x in json.loads((out / "decisions.json").read_text(encoding="utf-8"))}
    assert w == g
