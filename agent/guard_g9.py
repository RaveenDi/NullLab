"""G9 behavioural guard (design: docs/EVAL-12-G9-DSL.md). Replaces the constructor-name text check of agent/fidelity.py "MODEL unchanged"
with a RUNTIME check: a compiled config is executed on the case data (smoke profile) with recording wrappers on estimators and rows
carry provenance (TracedArray). From the recording we know which rows each model was FIT on, which rows it SCORED, which rows every
upstream fitted component (selector, scaler, resampler, tuner) saw, and which rows the returned evaluation scored.

No model (LLM) calls. The code that runs is compiled by agent/edit_dsl.py from train.py (not model-written). Fail closed: if row
provenance is lost where a decision needs it, the verdict is UNVERIFIABLE (treated as reject), never a silent accept.

Entry points: trace_run, analyze, behaviour_check, guard_config. Worker mode: `python -I guard_g9.py --worker args.json out.json`."""
import ast
import base64
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
    import importlib.util
    _sp = importlib.util.spec_from_file_location("nulllab_sandbox_run", ROOT / "sandbox" / "run.py")  # by path: -I keeps the repo off sys.path
    _sbx = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_sbx)
    _sbx.preload_heavy()  # library imports first; the compiled source is NOT executed yet
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

    pool, pool_ix = [], {}

    def pack_rows(r):
        """Row ids of one event as an index into a pool of identical-content packed bitsets (little bit order, bit k = row id k). Only the SET of
        non-negative ids is kept (that is all the analysis reads). Fallback: a plain list."""
        a = np.asarray(r)
        if a.size == 0:
            bits = b""
        else:
            if a.dtype.kind not in "iu":
                return [int(v) for v in a]
            a = a[a >= 0]
            if a.size == 0:
                bits = b""
            else:
                mx = int(a.max())
                if mx > 50_000_000:
                    return sorted(set(int(v) for v in a))
                pres = np.zeros(mx + 1, np.uint8)
                pres[a] = 1
                bits = np.packbits(pres, bitorder="little").tobytes()
        ix = pool_ix.get(bits)
        if ix is None:
            ix = pool_ix[bits] = len(pool)
            pool.append(bits)
        return ix

    import weakref
    uids = {}

    def objkey(o):
        """A key that identifies an object for as long as it lives and is NEVER reused by a later object (id() is: once a temporary estimator is
        freed, a new one can get its address, and two different models would then look like one). Dead objects drop out of the table."""
        i = id(o)
        hit = uids.get(i)
        if hit is not None and hit[0]() is o:
            return hit[1]
        n = len(uids_seen)
        uids_seen.append(None)
        try:
            ref = weakref.ref(o, lambda _r, i=i: uids.pop(i, None))
        except TypeError:  # not weak-referenceable: keep it alive instead
            ref = (lambda o=o: o)
        uids[i] = (ref, n)
        return n
    uids_seen = []

    def rec(kind, cls_name, obj, X, y_present, params=None, name=None):
        r = rids(X)
        events.append({"i": len(events), "kind": kind, "cls": cls_name, "obj": objkey(obj), "rid": None if r is None else pack_rows(r),
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
    code = compile(src, "train_g9.py", "exec")
    _sbx._block_network()  # everything the worker itself needs is read; now no network, no files outside cwd, no spawn / ctypes loads
    exec(code, mod.__dict__)
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
    out["rid_pool"] = [base64.b64encode(b).decode("ascii") for b in pool]
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
        from sandbox.limits import run_limited  # parent side only (the `-I` worker has no repo on sys.path)
        try:
            r = run_limited([sys.executable, "-I", str(HERE), "--worker", str(td / "args.json")], cwd=str(td), env=env, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"status": "timeout", "events": []}
        if not (td / "out.json").exists():
            return {"status": "crash", "error": "worker produced no output" + (f" ({r.limit_hit})" if getattr(r, "limit_hit", None) else ""), "tb": (r.stderr or "")[-1200:], "events": []}
        return _decode_trace(json.loads((td / "out.json").read_text(encoding="utf-8")))


# ---- compact row sets. The worker ships each event's row ids as a pooled, interned packed bitset (bit k = row id k); analyze() keeps them packed
# and does the set algebra with numpy bit operations. RowSet is an immutable set-like view (len, iteration, &, |, ==, in, bool) so code written
# for Python sets of ints (contamination, relation_violations, the tests) keeps working unchanged.
_POP = None
_MAX_UNIVERSE = 50_000_000


def _pop_table():
    global _POP
    if _POP is None:
        import numpy as np
        _POP = np.array([bin(i).count("1") for i in range(256)], dtype=np.int32)
    return _POP


class _Packed:
    """A row-id set as shipped by the worker (little bit order); `b` is a uint8 array."""
    __slots__ = ("b",)

    def __init__(self, b):
        self.b = b


def _decode_trace(out):
    import numpy as np
    pool = out.pop("rid_pool", None)
    if pool is not None:
        objs = [_Packed(np.frombuffer(base64.b64decode(x), dtype=np.uint8)) for x in pool]
        for e in out.get("events", ()):
            if isinstance(e.get("rid"), int):
                e["rid"] = objs[e["rid"]]
    return out


class RowSet:
    """Immutable set of non-negative row ids stored as a packed bit array (uint8, little bit order)."""
    __slots__ = ("b", "_n", "_c")

    def __init__(self, b):
        self.b, self._n, self._c = b, None, None

    def ids(self):
        import numpy as np
        return np.flatnonzero(np.unpackbits(self.b, bitorder="little"))

    def __len__(self):
        if self._n is None:
            self._n = int(_pop_table()[self.b].sum())
        return self._n

    def __bool__(self):
        return bool(self.b.any())

    def __iter__(self):
        return iter(self.ids().tolist())

    def __contains__(self, v):
        try:
            i = int(v)
        except (TypeError, ValueError):
            return False
        if i < 0 or i >= len(self.b) * 8 or i != v:
            return False
        return bool((self.b[i >> 3] >> (i & 7)) & 1)

    def canon(self):
        if self._c is None:
            self._c = self.b.tobytes().rstrip(b"\x00")
        return self._c

    def _pair(self, o):
        import numpy as np
        a, b = self.b, o.b
        if len(a) < len(b):
            a = np.concatenate([a, np.zeros(len(b) - len(a), np.uint8)])
        elif len(b) < len(a):
            b = np.concatenate([b, np.zeros(len(a) - len(b), np.uint8)])
        return a, b

    def __and__(self, o):
        if isinstance(o, RowSet):
            a, b = self._pair(o)
            return RowSet(a & b)
        if isinstance(o, (set, frozenset)):
            return set(self) & o
        return NotImplemented

    def __or__(self, o):
        if isinstance(o, RowSet):
            a, b = self._pair(o)
            return RowSet(a | b)
        if isinstance(o, (set, frozenset)):
            return set(self) | o
        return NotImplemented

    __rand__, __ror__ = __and__, __or__

    def __eq__(self, o):
        if isinstance(o, RowSet):
            return self.canon() == o.canon()
        if isinstance(o, (set, frozenset)):
            return set(self) == o
        return NotImplemented

    def __ne__(self, o):
        r = self.__eq__(o)
        return r if r is NotImplemented else not r

    def __hash__(self):
        return hash(self.canon())

    def __repr__(self):
        return f"RowSet(n={len(self)})"


def _canon(x):
    """Canonical bytes of a row set (RowSet or any iterable of ints): equal sets give equal bytes."""
    if isinstance(x, RowSet):
        return x.canon()
    import numpy as np
    ids = np.fromiter(x, dtype=np.int64)
    if ids.size == 0:
        return b""
    pres = np.zeros(int(ids.max()) + 1, np.uint8)
    pres[ids] = 1
    return np.packbits(pres, bitorder="little").tobytes().rstrip(b"\x00")


def _arr(x):
    """Reference semantics: the set of non-negative ids, None if untracked (plain Python set)."""
    if x is None:
        return None
    if isinstance(x, _Packed):
        return set(RowSet(x.b))
    return set(v for v in x if v >= 0)


class _Fallback(Exception):
    pass


def _analyze_sets(trace):
    """Original set-based implementation (kept for traces the packed path does not cover: event index != position, huge row ids)."""
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


def _analyze_packed(trace):
    """Same output as _analyze_sets with RowSet values, in one pass: bit-level set algebra, interned results, and an incremental "context window"
    (events since the previous evaluation-scoring event, minus the scoring object's own) instead of rescanning it for every score event."""
    import numpy as np
    ev = trace.get("events", [])
    E = trace.get("E")
    for k, e in enumerate(ev):
        if e["i"] != k:
            raise _Fallback("event index differs from position")

    def rid_max(r):
        if isinstance(r, _Packed):
            return len(r.b) * 8 - 1
        a = np.asarray(r)
        if a.size == 0:
            return -1
        if a.dtype.kind not in "iu":
            raise _Fallback("non-integer row ids")
        return int(a.max())
    mx, seen = -1, set()
    for e in ev:
        r = e["rid"]
        if r is not None and e["kind"] in ("fit", "score", "fn") and (isinstance(r, list) or id(r) not in seen):
            seen.add(id(r))
            mx = max(mx, rid_max(r))
    if E is not None:
        mx = max(mx, rid_max(E))
    if mx + 1 > _MAX_UNIVERSE:
        raise _Fallback("row ids too large")
    nb = max(1, (mx + 1 + 7) // 8)
    nbits = nb * 8
    cache, intern = {}, {}

    def mk(b):
        key = b.tobytes()
        rs = intern.get(key)
        if rs is None:
            rs = intern[key] = RowSet(b)
        return rs

    def to_rs(r):
        if r is None:
            return None
        if isinstance(r, _Packed):
            hit = cache.get(id(r))
            if hit is None:
                b = r.b
                if len(b) != nb:
                    b = np.concatenate([b, np.zeros(nb - len(b), np.uint8)])
                hit = cache[id(r)] = (r, mk(b))
            return hit[1]
        if not isinstance(r, list):
            hit = cache.get(id(r))
            if hit is not None:
                return hit[1]
        a = np.asarray(r)
        if a.size:
            a = a[a >= 0]
        pres = np.zeros(nbits, np.uint8)
        if a.size:
            pres[a] = 1
        rs = mk(np.packbits(pres, bitorder="little"))
        if not isinstance(r, list):
            cache[id(r)] = (r, rs)
        return rs
    Eset = to_rs(E)
    n_syn = 0
    if E is not None and len(E):
        n_syn = int(np.count_nonzero(np.asarray(E) < 0))
    out = {"tracked": E is not None, "n_eval": trace.get("n_eval"), "E_synth": n_syn if E else 0, "scores": [], "models": {}, "fn_calls": {}, "untracked_events": 0}
    zero = mk(np.zeros(nb, np.uint8))
    eval_memo = {}
    last_fit, comp_latest = {}, {}
    # window of fit/fn events since the last evaluation-scoring event, aggregated per component name
    w_objs, w_none, w_A, w_T, w_cnt = {}, {}, {}, {}, {}

    def unpack(b):
        return np.unpackbits(b, bitorder="little")

    def window_reset():
        for d in (w_objs, w_none, w_A, w_T, w_cnt):
            d.clear()

    def window_add(e, rows):
        name, obj = e["cls"], e["obj"]
        w_objs.setdefault(name, set()).add(obj)
        if rows is None:
            w_none.setdefault(name, set()).add(obj)
            return
        A = w_A.setdefault(name, {})
        old = A.get(obj)
        delta = rows.b if old is None else rows.b & ~old
        A[obj] = rows.b if old is None else old | rows.b
        w_T[name] = rows.b if name not in w_T else w_T[name] | rows.b
        if delta.any():
            cnt = w_cnt.get(name)
            if cnt is None:
                cnt = w_cnt[name] = np.zeros(nbits, np.int32)
            cnt += unpack(delta)

    for e in ev:
        kind = e["kind"]
        if e["rid"] is None and kind in ("fit", "score", "fn"):
            out["untracked_events"] += 1
        if kind not in ("fit", "score", "fn"):
            continue
        rows = to_rs(e["rid"])
        if kind == "fit":
            last_fit[e["obj"]] = e
            comp_latest[("fit", e["cls"])] = e
            window_add(e, rows)
        elif kind == "fn":
            comp_latest[("fn", e["cls"])] = e
            out["fn_calls"][e["cls"]] = out["fn_calls"].get(e["cls"], 0) + 1
            window_add(e, rows)
        else:
            o = e["obj"]
            fit = last_fit.get(o)
            is_eval = False
            if rows is not None and Eset is not None:
                is_eval = eval_memo.get(id(rows))
                if is_eval is None:
                    is_eval = eval_memo[id(rows)] = bool((rows.b & Eset.b).any())
            parts = {}  # name -> [has_untracked, OR of bits or None]
            for kk, ee in comp_latest.items():
                if ee["obj"] != o:
                    ent = parts.setdefault(kk[1], [False, None])
                    r = to_rs(ee["rid"])
                    if r is None:
                        ent[0] = True
                    else:
                        ent[1] = r.b if ent[1] is None else ent[1] | r.b
            for name, objs in w_objs.items():
                if len(objs) <= (1 if o in objs else 0):
                    continue
                ent = parts.setdefault(name, [False, None])
                nn = w_none.get(name)
                if nn and len(nn) > (1 if o in nn else 0):
                    ent[0] = True
                A = w_A.get(name)
                if not A:
                    continue
                if o in A:
                    if len(A) == 1:
                        continue
                    cnt = w_cnt.get(name)
                    if cnt is None:  # no row id was ever seen for this component in the window
                        continue
                    wb = np.packbits((cnt - unpack(A[o])) > 0, bitorder="little")
                else:
                    wb = w_T[name]
                ent[1] = wb if ent[1] is None else ent[1] | wb
            ctx_rows = {name: (None if ent[0] else (zero if ent[1] is None else mk(ent[1]))) for name, ent in parts.items()}
            out["scores"].append({"i": e["i"], "obj": o, "cls": e["cls"], "eval": is_eval, "stack": e["stack"], "S": rows, "S_untracked": rows is None,
                                  "R": None if fit is None else to_rs(fit["rid"]), "fit_i": None if fit is None else fit["i"],
                                  "params": None if fit is None else fit["params"], "ctx": ctx_rows})
            if is_eval:
                window_reset()
    return out


def analyze(trace):
    """Per scoring event: fit rows of the same instance, scored rows, upstream context rows. Pure function of the trace. Row sets are RowSet objects
    (set-like); the result is value-identical to the original set-based implementation (tests/test_guard_g9_equivalence.py)."""
    try:
        return _analyze_packed(trace)
    except _Fallback:
        return _analyze_sets(trace)


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


def _col_arrays(cm, nb):
    """(values, present) arrays indexed by row id for the vectorised relation check, or None when the plain-dict path must be used (NaN values,
    ids outside the column index, negative or huge ids): the dict path reproduces the original exceptions and NaN ordering exactly."""
    import numpy as np
    try:
        ids = np.fromiter(cm.keys(), dtype=np.int64, count=len(cm))
        vals = np.fromiter(cm.values(), dtype=np.float64, count=len(cm))
    except (TypeError, ValueError, OverflowError):
        return None
    if len(ids) and (ids.min() < 0 or ids.max() > _MAX_UNIVERSE or np.isnan(vals).any()):
        return None
    size = max(nb * 8, 1, int(ids.max()) + 1 if len(ids) else 1)
    v = np.zeros(size, np.float64)
    present = np.zeros(size, bool)
    v[ids] = vals
    present[ids] = True
    return v, present


def relation_violations(an, trace, kind, col, scope_step=None):
    """Count (train, test) pairs of evaluation (or in-scope) models violating the relation implied by `kind`."""
    bad, total, untracked = 0, 0, 0
    cm = _col(trace, col) if col else None
    arrs, memo = None, {}
    for s in an["scores"]:
        in_scope = (scope_step in s["stack"]) if scope_step else s["eval"]
        if not in_scope:
            continue
        if s["S"] is None or s["R"] is None:
            untracked += 1
            continue
        total += 1
        R, S = s["R"], s["S"]
        if kind == "random":
            bad += bool(R & S)
        elif cm is None:
            untracked += 1
        else:
            fast = isinstance(R, RowSet) and isinstance(S, RowSet)
            if fast and arrs is None:
                arrs = _col_arrays(cm, len(R.b)) or False
            fast = fast and arrs is not False
            if fast:
                v, present = arrs

                def vals(rs):
                    hit = memo.get(id(rs))
                    if hit is None:
                        ids = rs.ids()
                        hit = memo[id(rs)] = (rs, ids, bool(present[ids].all()), v[ids])
                    return hit
                hr, hs = vals(R), vals(S)
                fast = hr[2] and hs[2]
            if fast:
                if kind == "group":
                    bad += bool(len(hr[3]) and len(hs[3]) and np_intersects(hr[3], hs[3]))
                else:
                    tr_max = hr[3].max() if len(hr[3]) else None
                    te_min = hs[3].min() if len(hs[3]) else None
                    bad += not (tr_max is not None and te_min is not None and tr_max < te_min)
            elif kind == "group":
                bad += bool({cm[r] for r in R} & {cm[r] for r in S})
            else:
                tr_max = max((cm[r] for r in R), default=None)
                te_min = min((cm[r] for r in S), default=None)
                bad += not (tr_max is not None and te_min is not None and tr_max < te_min)
    return {"bad": bad, "total": total, "untracked": untracked}


def np_intersects(a, b):
    import numpy as np
    return bool(np.intersect1d(a, b).size)


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
    h = lambda x: (0, b"") if x is None else (1, _canon(x))  # noqa: E731  the exact row sets, not only their sizes
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
