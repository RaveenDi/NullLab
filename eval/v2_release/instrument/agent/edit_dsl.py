"""G9 typed edit DSL (design: docs/EVAL-12-G9-DSL.md). The planner names an OP and its parameters; this module compiles the op into
train.py by deterministic AST templates. The planner never writes code. No model calls, no network.

Ops (FROZEN list, see OP_SPEC and its sha256 in docs/EVAL-12-G9-DSL.md):
  move_into_fold(step, call)       a whole-data resampler / selector / fitted transformer runs before the split; run it per fold on training rows only
  drop_from_eval(step, call)       remove a label-using resampler / selector from the evaluation path
  replace_split(step, kind, col)   random | group | temporal hold-out or CV splitter in `step`
  retrain_inside(step)             a model fitted once on all rows and reused across folds is refitted inside each fold

Anything a template cannot express safely raises OpError (code NOT_APPLICABLE), which is a first-class outcome, not a crash."""
import ast
import copy
import hashlib
import json

OP_SPEC = {
    "dsl": "nulllab-g9-dsl-1",
    "taxonomy_source": "Kapoor and Narayanan, Leakage and the reproducibility crisis in machine-learning-based science, arXiv 2207.07048 "
                       "(abstract verified: 'a fine-grained taxonomy of 8 types of leakage'; the per-type names below are from memory, UNVERIFIED)",
    "ops": {
        "move_into_fold": {"params": ["step", "call"], "leak_types": ["pre-processing on train and test together",
                                                                     "feature selection on train and test together",
                                                                     "resampling/oversampling before the split (published instance: arXiv 2001.06296)"]},
        "drop_from_eval": {"params": ["step", "call"], "leak_types": ["resampling or label-driven selection applied on the evaluation path"]},
        "replace_split": {"params": ["step", "kind", "col"], "kinds": ["random", "group", "temporal"],
                          "leak_types": ["no proper test set (train and score on the same rows)", "temporal leakage",
                                         "non-independence between train and test samples"]},
        "retrain_inside": {"params": ["step"], "leak_types": ["model state fitted on all rows reused to score held-out rows"]},
    },
    "not_covered": ["duplicates between train and test", "illegitimate features (no feature-edit op; the G6 FEATURE-REASON path is not reproduced)",
                    "sampling bias of the dataset itself", "metric changes", "model or hyperparameter changes"],
}


def spec_sha256():
    return hashlib.sha256(json.dumps(OP_SPEC, sort_keys=True).encode("utf-8")).hexdigest()


OPS = tuple(OP_SPEC["ops"])
KINDS = tuple(OP_SPEC["ops"]["replace_split"]["kinds"])
SPLITTER_CLASSES = {"KFold", "StratifiedKFold", "GroupKFold", "StratifiedGroupKFold", "ShuffleSplit", "StratifiedShuffleSplit",
                    "GroupShuffleSplit", "TimeSeriesSplit", "RepeatedKFold", "RepeatedStratifiedKFold"}
CONTROLLED = "\n\n\ndef controlled_eval(df, seed):\n    return claimed_eval(df, seed)\n"


class OpError(Exception):
    def __init__(self, code, msg):
        super().__init__(f"{code}: {msg}")
        self.code, self.msg = code, msg


def NA(msg):
    return OpError("NOT_APPLICABLE", msg)


HELPERS = '''
def _g9_take(x, idx):
    return x.iloc[idx] if hasattr(x, "iloc") else x[idx]


def _g9_holdout(n, kind, seed, frac, key=None):
    import numpy as np
    n = int(n)
    if kind == "random":
        perm = np.random.default_rng(seed).permutation(n)
        k = max(1, int(round(n * frac)))
        return np.sort(perm[k:]), np.sort(perm[:k])
    key = np.asarray(key)
    if kind == "temporal":
        order = np.argsort(key, kind="stable")
        cut = key[order[min(n - 1, int(n * (1 - frac)))]]
        tr, te = np.flatnonzero(key < cut), np.flatnonzero(key >= cut)
    else:
        ug = np.unique(key)
        pick = np.random.default_rng(seed).permutation(len(ug))[:max(1, int(round(len(ug) * frac)))]
        mask = np.isin(key, ug[pick])
        tr, te = np.flatnonzero(~mask), np.flatnonzero(mask)
    if len(tr) == 0 or len(te) == 0:
        raise ValueError("g9 hold-out is empty for kind " + kind)
    return tr, te
'''
SPLIT_IMPORT = "from sklearn.model_selection import KFold as _G9KFold, TimeSeriesSplit as _G9TSS, GroupKFold as _G9GKF"


# ---------------- ast helpers ----------------
def fname(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def defs_of(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def params_of(fn):
    return [a.arg for a in fn.args.args]


def parse_expr(s):
    return ast.parse(s, mode="eval").body


def parse_stmts(s):
    return ast.parse(s).body


def names_in(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}


def calls_in(node, name):
    return [c for c in ast.walk(node) if isinstance(c, ast.Call) and fname(c) == name]


def holdout_steps(tree):
    local = set(defs_of(tree))
    out = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple) and len(node.targets[0].elts) == 2
                and isinstance(node.value, ast.Call) and fname(node.value) in local):
            out.add(fname(node.value))
    return out


def _fold_scopes(fn):
    """[(container_list, start_index, tr, te, kind)] inside fn: `for tr, te in ...:` loops and `tr, te = ...` unpacks."""
    out = []

    def tn(t):
        return isinstance(t, ast.Tuple) and len(t.elts) == 2 and all(isinstance(e, ast.Name) for e in t.elts)

    for node in ast.walk(fn):
        if isinstance(node, ast.For) and tn(node.target):
            out.append((node.body, 0, node.target.elts[0].id, node.target.elts[1].id, "loop"))
    for i, st in enumerate(fn.body):
        if isinstance(st, ast.Assign) and len(st.targets) == 1 and tn(st.targets[0]):
            out.append((fn.body, i + 1, st.targets[0].elts[0].id, st.targets[0].elts[1].id, "unpack"))
    return out


def _reach(tree_defs, step):
    """step and its local callees (depth 2), BFS order."""
    seen, order, frontier = {step}, [step], [step]
    for _ in range(2):
        nxt = []
        for n in frontier:
            for c in ast.walk(tree_defs[n]):
                nm = fname(c) if isinstance(c, ast.Call) else None
                if nm in tree_defs and nm not in seen:
                    seen.add(nm)
                    order.append(nm)
                    nxt.append(nm)
        frontier = nxt
    return order


def _get_step(tree, step):
    d = defs_of(tree)
    if not isinstance(step, str) or step not in d:
        raise OpError("NO_SUCH_STEP", f"'{step}' is not a top-level function of train.py (steps: {sorted(d)})")
    if step == "load":
        raise OpError("NO_SUCH_STEP", "'load' may not be edited")
    return d, d[step]


def _ensure_imports(tree, line):
    node = ast.parse(line).body[0]
    if not any(ast.dump(n) == ast.dump(node) for n in tree.body):
        pos = max([i + 1 for i, n in enumerate(tree.body) if isinstance(n, (ast.Import, ast.ImportFrom))] or [0])
        tree.body.insert(pos, node)


def _ensure_helpers(tree):
    if "_g9_holdout" not in defs_of(tree):
        pos = max([i + 1 for i, n in enumerate(tree.body) if isinstance(n, (ast.Import, ast.ImportFrom))] or [0])
        tree.body[pos:pos] = ast.parse(HELPERS).body


# ---------------- statement shapes for move_into_fold / drop_from_eval ----------------
def _stmt_shape(st, call):
    """-> dict(shape=R|S|T, ...) or None. R: X, y = call(X, y, ...); S: k = call(...); T: V = Cls(..).fit_transform(A)."""
    if not (isinstance(st, ast.Assign) and len(st.targets) == 1):
        return None
    t, v = st.targets[0], st.value
    if isinstance(t, ast.Tuple) and isinstance(v, ast.Call) and fname(v) == call and len(v.args) >= 2:
        a0, a1 = v.args[0], v.args[1]
        if (len(t.elts) == 2 and all(isinstance(e, ast.Name) for e in t.elts) and isinstance(a0, ast.Name) and isinstance(a1, ast.Name)
                and [e.id for e in t.elts] == [a0.id, a1.id]):
            return {"shape": "R", "call": v, "data": (a0.id, a1.id)}
        return None
    if isinstance(t, ast.Name) and isinstance(v, ast.Call):
        if fname(v) == call and not (isinstance(v.func, ast.Attribute) and v.func.attr == "fit_transform"):
            return {"shape": "S", "call": v, "var": t.id}
        if (isinstance(v.func, ast.Attribute) and v.func.attr == "fit_transform" and isinstance(v.func.value, ast.Call)
                and fname(v.func.value) == call and call[:1].isupper() and v.args and isinstance(v.args[0], ast.Name)):
            return {"shape": "T", "call": v, "var": t.id, "cls_call": v.func.value, "src": v.args[0].id, "fit_args": v.args}
    return None


def _top_stmt(fn, call, op):
    hits = [i for i, st in enumerate(fn.body) if calls_in(st, call)]
    if not hits:
        in_loop = bool(calls_in(fn, call))
        raise NA(f"{op}: call '{call}' is not at the top level of step '{fn.name}'" + (" (it is nested in a loop or branch)" if in_loop else " (not called there)"))
    if len(hits) > 1:
        raise NA(f"{op}: call '{call}' occurs in {len(hits)} top-level statements of '{fn.name}'")
    st = fn.body[hits[0]]
    shape = _stmt_shape(st, call)
    if shape is None:
        raise NA(f"{op}: statement shape not supported for '{call}' (supported: `X, y = call(X, y, ...)`, `k = call(X, y, ...)` used as X[:, k], "
                 "`V = Cls(...).fit_transform(X)`)")
    shape["index"] = hits[0]
    return shape


def _slice_has(sl, name):
    return name in names_in(sl)


def _selector_uses(fn, var, after):
    """Subscript nodes in fn.body[after+1:] whose slice mentions `var`."""
    out = []
    for st in fn.body[after + 1:]:
        out += [n for n in ast.walk(st) if isinstance(n, ast.Subscript) and _slice_has(n.slice, var)]
    return out


class _Replace(ast.NodeTransformer):
    def __init__(self, fn):
        self.fn = fn

    def visit(self, node):
        r = self.fn(node)
        return r if r is not None else self.generic_visit(node)


def _rewrite(container_nodes, fn):
    """Apply fn(node)->replacement|None over statements (children of a replacement are not revisited)."""
    t = _Replace(fn)
    return [t.visit(n) for n in container_nodes]


def _is_view(node, base, idx):
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name) and node.value.id == base
            and isinstance(node.slice, ast.Name) and node.slice.id == idx)


def _call_site(step_fn, fold_fn):
    """The Call to fold_fn in step_fn -> {stepvar: foldparam} for plain-Name args and base-Name of subscripts."""
    sites = [c for c in ast.walk(step_fn) if isinstance(c, ast.Call) and fname(c) == fold_fn.name]
    if not sites:
        raise NA(f"'{fold_fn.name}' is not called from '{step_fn.name}'")
    c = sites[0]
    ps = params_of(fold_fn)
    amap, argexp = {}, {}
    for i, a in enumerate(c.args):
        if i < len(ps):
            argexp[ps[i]] = a
    for k in c.keywords:
        if k.arg in ps:
            argexp[k.arg] = k.value
    for p, a in argexp.items():
        base = a.value if isinstance(a, ast.Subscript) else a
        if isinstance(base, ast.Name):
            amap[base.id] = p
    return amap, argexp


def _fold_view_base(container, start, tr, te):
    """Names X such that X[tr] / X[te] occur in the scope."""
    bases = set()
    for st in container[start:]:
        for n in ast.walk(st):
            if isinstance(n, ast.Subscript) and isinstance(n.value, ast.Name) and isinstance(n.slice, ast.Name) and n.slice.id in (tr, te):
                bases.add(n.value.id)
    return bases


def _map_call_args(call, name_map, fold_fn, module_names, data_views):
    """Re-express the original call's args inside the fold scope. data_views: {origName: expr-source in fold}."""
    out = []
    for a in call.args:
        if isinstance(a, ast.Name) and a.id in data_views:
            out.append(parse_expr(data_views[a.id]))
        elif isinstance(a, ast.Constant):
            out.append(copy.deepcopy(a))
        elif isinstance(a, ast.Name):
            nm = name_map.get(a.id, a.id)
            if nm in params_of(fold_fn) or nm in module_names or nm in dir(__builtins__) or nm in {t.id for t in ast.walk(fold_fn) if isinstance(t, ast.Name) and isinstance(t.ctx, ast.Store)}:
                out.append(ast.Name(id=nm, ctx=ast.Load()))
            else:
                raise NA(f"argument '{a.id}' of the call is not available inside the fold scope")
        else:
            free = names_in(a) - module_names - set(dir(__builtins__))
            if free - set(params_of(fold_fn)):
                raise NA("a call argument is a compound expression using names not available inside the fold scope")
            out.append(copy.deepcopy(a))
    kws = []
    for k in call.keywords:
        kws.append(ast.keyword(arg=k.arg, value=copy.deepcopy(k.value)))
    return out, kws


def _module_names(tree):
    s = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef)):
            s.add(n.name)
        elif isinstance(n, ast.Assign):
            s |= {t.id for t in n.targets if isinstance(t, ast.Name)}
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            s |= {(a.asname or a.name).split(".")[0] for a in n.names}
    return s


def op_move_into_fold(tree, step, call):
    defs, fn = _get_step(tree, step)
    if not isinstance(call, str) or not call:
        raise OpError("BAD_PARAM", "move_into_fold needs a call name")
    sh = _top_stmt(fn, call, "move_into_fold")
    modnames = _module_names(tree)
    # fold scope reachable from the step
    scope = None
    for nm in _reach(defs, step):
        fs = _fold_scopes(defs[nm])
        if nm == step:  # the statement itself must precede an unpack scope
            fs = [s for s in fs if s[4] == "loop" or s[1] - 1 > sh["index"]]
        if fs:
            scope = (defs[nm],) + fs[0]
            break
    if scope is None:
        raise NA(f"no train/test fold scope (`for tr, te in ...` or `tr, te = ...`) reachable from '{step}' after the call")
    ffn, container, start, tr, te, skind = scope
    if ffn is fn:
        name_map, argexp = {}, {}
    else:
        name_map, argexp = _call_site(fn, ffn)
    shape = sh["shape"]
    if shape == "R":
        a, b = sh["data"]
        fits = []
        for i, st in enumerate(container[start:], start):
            for c in ast.walk(st):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute) and c.func.attr == "fit" and len(c.args) >= 2:
                    fits.append((i, c))
        if not fits:
            raise NA("no `.fit(X, y)` call with two data arguments inside the fold scope")
        done = set()
        for i, c in sorted(fits, key=lambda t: -t[0]):
            P, Q = c.args[0], c.args[1]
            views = {a: ast.unparse(P), b: ast.unparse(Q)}
            args, kws = _map_call_args(sh["call"], name_map, ffn, modnames, views)
            n1, n2 = f"_g9_{a}_{i}", f"_g9_{b}_{i}"
            new = ast.Assign(targets=[ast.Tuple(elts=[ast.Name(id=n1, ctx=ast.Store()), ast.Name(id=n2, ctx=ast.Store())], ctx=ast.Store())],
                             value=ast.Call(func=copy.deepcopy(sh["call"].func), args=args, keywords=kws), lineno=0)
            c.args[0], c.args[1] = ast.Name(id=n1, ctx=ast.Load()), ast.Name(id=n2, ctx=ast.Load())
            if i not in done:
                container.insert(i, new)
                done.add(i)
            else:
                container.insert(i, new)
        del fn.body[sh["index"]]
    else:
        # S / T: rewrite fold views of the data variable that the call's output feeds
        if shape == "S":
            uses = _selector_uses(fn, sh["var"], sh["index"])
            if not uses:
                raise NA(f"selector output '{sh['var']}' is not used as a column index afterwards")
            base_names = set()
            for u in uses:
                if not isinstance(u.value, ast.Name):
                    raise NA("selector output is used on a compound expression")
                base_names.add(u.value.id)
            if len(base_names) != 1:
                raise NA("selector output indexes more than one array")
            base = base_names.pop()
            fold_base = name_map.get(base, base)
        else:  # T
            base = sh["var"]
            fold_base = name_map.get(base, base)
        if fold_base not in _fold_view_base(container, start, tr, te):
            raise NA(f"inside the fold scope '{fold_base}' is not split with [{tr}]/[{te}]")
        # every other use of fold_base inside the scope must be a view
        for st in container[start:]:
            for n in ast.walk(st):
                if isinstance(n, ast.Name) and n.id == fold_base and isinstance(n.ctx, ast.Load):
                    pass
        for st in container[start:]:
            parents = {}
            for p in ast.walk(st):
                for ch in ast.iter_child_nodes(p):
                    parents[id(ch)] = p
            for n in ast.walk(st):
                if isinstance(n, ast.Name) and n.id == fold_base:
                    par = parents.get(id(n))
                    if not (par is not None and _is_view(par, fold_base, tr) or par is not None and _is_view(par, fold_base, te)):
                        raise NA(f"'{fold_base}' is used inside the fold scope other than as {fold_base}[{tr}] / {fold_base}[{te}]")
        data_views = {}
        yname = None
        if shape == "S":
            cargs = sh["call"].args
            for a in cargs:
                if isinstance(a, ast.Name):
                    fb = name_map.get(a.id, a.id)
                    if fb in _fold_view_base(container, start, tr, te):
                        data_views[a.id] = f"{fb}[{tr}]"
            if not data_views:
                raise NA("no argument of the call is a row-aligned array that the fold scope splits")
            args, kws = _map_call_args(sh["call"], name_map, ffn, modnames, data_views)
            init = ast.Assign(targets=[ast.Name(id="_g9_k", ctx=ast.Store())],
                              value=ast.Call(func=copy.deepcopy(sh["call"].func), args=args, keywords=kws), lineno=0)
            slice0 = copy.deepcopy(uses[0].slice)

            def swap(n):
                if isinstance(n, ast.Name) and n.id == sh["var"]:
                    return ast.Name(id="_g9_k", ctx=ast.Load())
                return None
            slice1 = _rewrite([slice0], swap)[0]

            def wrap(n):
                if _is_view(n, fold_base, tr) or _is_view(n, fold_base, te):
                    return ast.Subscript(value=n, slice=copy.deepcopy(slice1), ctx=ast.Load())
                return None
            container[start:] = _rewrite(container[start:], wrap)
            container.insert(start, init)
            # step side: drop the selector and unwrap its uses
            del fn.body[sh["index"]]

            def unwrap(n):
                if isinstance(n, ast.Subscript) and any(n is u for u in uses):
                    return n.value
                return None
            fn.body[:] = _rewrite(fn.body, unwrap)
        else:
            src_view = sh["src"]
            fb_src = name_map.get(src_view, src_view)
            if fb_src not in _fold_view_base(container, start, tr, te):
                raise NA(f"transformer input '{src_view}' is not an array the fold scope splits")
            cls_call = copy.deepcopy(sh["cls_call"])
            fit_args = [parse_expr(f"{fb_src}[{tr}]")] + [copy.deepcopy(a) for a in sh["fit_args"][1:]]
            init = ast.Assign(targets=[ast.Name(id="_g9_t", ctx=ast.Store())],
                              value=ast.Call(func=ast.Attribute(value=cls_call, attr="fit", ctx=ast.Load()), args=fit_args, keywords=[]), lineno=0)

            def wrapT(n):
                if _is_view(n, fold_base, tr) or _is_view(n, fold_base, te):
                    return ast.Call(func=ast.Attribute(value=ast.Name(id="_g9_t", ctx=ast.Load()), attr="transform", ctx=ast.Load()), args=[n], keywords=[])
                return None
            container[start:] = _rewrite(container[start:], wrapT)
            container.insert(start, init)
            fn.body[sh["index"]] = ast.Assign(targets=[ast.Name(id=sh["var"], ctx=ast.Store())], value=ast.Name(id=sh["src"], ctx=ast.Load()), lineno=0)
    if not fn.body:
        fn.body.append(ast.Pass())
    return tree


def op_drop_from_eval(tree, step, call):
    defs, fn = _get_step(tree, step)
    if not isinstance(call, str) or not call:
        raise OpError("BAD_PARAM", "drop_from_eval needs a call name")
    sh = _top_stmt(fn, call, "drop_from_eval")
    if sh["shape"] == "T":
        raise OpError("PRECONDITION", f"drop_from_eval: '{call}' is a fitted transformer, not a label-using resampler or selector; "
                                      "removing it changes the pipeline. Use move_into_fold to fit it on training rows only")
    if sh["shape"] == "S":
        uses = _selector_uses(fn, sh["var"], sh["index"])
        if not uses or any(not isinstance(u.value, ast.Name) for u in uses):
            raise NA("selector output is not used as a plain column index")
        del fn.body[sh["index"]]
        fn.body[:] = _rewrite(fn.body, lambda n: n.value if isinstance(n, ast.Subscript) and any(n is u for u in uses) else None)
    else:
        del fn.body[sh["index"]]
    if not fn.body:
        fn.body.append(ast.Pass())
    return tree


# ---------------- replace_split ----------------
def op_replace_split(tree, step, kind, col):
    defs, fn = _get_step(tree, step)
    if kind not in KINDS:
        raise OpError("BAD_PARAM", f"replace_split kind must be one of {list(KINDS)}")
    if kind in ("group", "temporal") and (not isinstance(col, str) or not col):
        raise OpError("BAD_PARAM", f"replace_split kind {kind} needs col (a column of the data)")
    ps = params_of(fn)
    seed = "seed" if "seed" in ps else "0"
    ts_default = None
    for a, d in zip(fn.args.args[len(fn.args.args) - len(fn.args.defaults):], fn.args.defaults):
        if a.arg == "test_size":
            ts_default = ast.unparse(d)
    splitters = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and fname(c) in SPLITTER_CLASSES]
    tts = [c for c in ast.walk(fn) if isinstance(c, ast.Call) and fname(c) == "train_test_split"]
    is_hold = step in holdout_steps(tree)

    def keyexpr():
        if "df" not in ps:
            raise NA(f"step '{step}' has no `df` parameter to read column '{col}' from")
        return f"df[{col!r}].to_numpy()"

    if is_hold and not splitters and not tts:  # H: the step returns (train rows, test rows)
        if not ps or ps[0] != "df":
            raise NA(f"hold-out step '{step}' must take `df` as its first parameter")
        frac = ts_default or "0.2"
        key = keyexpr() if kind != "random" else "None"
        _ensure_helpers(tree)
        fn.body[:] = parse_stmts(f"return _g9_holdout(len(df), {kind!r}, {seed}, {frac}, {key})")
        return tree
    if tts and not splitters:  # H2
        if len(tts) != 1:
            raise NA("more than one train_test_split call")
        c = tts[0]
        if len(c.args) != 1 or not (isinstance(c.args[0], ast.Call) and fname(c.args[0]) == "arange" and len(c.args[0].args) == 1):
            raise NA("train_test_split must be applied to a single `np.arange(n)` argument")
        frac = "0.25"
        for k in c.keywords:
            if k.arg == "test_size":
                frac = ast.unparse(k.value)
        if "df" not in ps and kind != "random":
            raise NA(f"step '{step}' has no `df` parameter to read column '{col}' from")
        key = keyexpr() if kind != "random" else "None"
        n = ast.unparse(c.args[0].args[0])
        _ensure_helpers(tree)
        new = parse_expr(f"_g9_holdout({n}, {kind!r}, {seed}, {frac}, {key})")
        fn.body[:] = _rewrite(fn.body, lambda x: new if x is c else None)
        return tree
    if splitters:  # C: CV splitter constructed in the step
        if len(splitters) != 1:
            raise NA(f"{len(splitters)} splitter constructions in '{step}' (ambiguous)")
        c = splitters[0]
        n = "5"
        for i, a in enumerate(c.args[:1]):
            n = ast.unparse(a)
        for k in c.keywords:
            if k.arg == "n_splits":
                n = ast.unparse(k.value)
        if fname(c) in ("ShuffleSplit", "StratifiedShuffleSplit", "GroupShuffleSplit"):
            raise NA("single-split shuffle splitters are not replaced by CV splitters in v1")
        _ensure_imports(tree, SPLIT_IMPORT)
        if kind == "random":
            new = parse_expr(f"_G9KFold(n_splits={n}, shuffle=True, random_state={seed})")
        elif kind == "temporal":
            if col is None:
                raise OpError("BAD_PARAM", "temporal needs col")
            new = parse_expr(f"_G9TSS(n_splits={n})")
        else:
            if "groups" not in ps:
                raise NA(f"group splitting inside '{step}' needs a `groups` parameter to pass to .split(); none exists")
            new = parse_expr(f"_G9GKF(n_splits={n})")
            sp = [x for x in ast.walk(fn) if isinstance(x, ast.Call) and isinstance(x.func, ast.Attribute) and x.func.attr == "split"]
            for x in sp:
                if not any(k.arg == "groups" for k in x.keywords):
                    x.keywords.append(ast.keyword(arg="groups", value=ast.Name(id="groups", ctx=ast.Load())))
        fn.body[:] = _rewrite(fn.body, lambda x: new if x is c else None)
        return tree
    raise NA(f"step '{step}' holds no recognisable split (not a `tr, te = step(...)` hold-out step, no splitter or train_test_split call)")


# ---------------- retrain_inside ----------------
def op_retrain_inside(tree, step):
    defs, fn = _get_step(tree, step)
    loops = [(i, st) for i, st in enumerate(fn.body) if isinstance(st, ast.For) and isinstance(st.target, ast.Tuple) and len(st.target.elts) == 2
             and all(isinstance(e, ast.Name) for e in st.target.elts)]
    if not loops:
        raise NA(f"step '{step}' has no top-level `for tr, te in ...:` loop")
    li, loop = loops[0]
    tr = loop.target.elts[0].id
    for i, st in enumerate(fn.body[:li]):
        call = fit_call = var = None
        if isinstance(st, ast.Expr) and isinstance(st.value, ast.Call) and isinstance(st.value.func, ast.Attribute) and st.value.func.attr == "fit" \
                and isinstance(st.value.func.value, ast.Name):
            var, fit_call = st.value.func.value.id, st.value
        elif (isinstance(st, ast.Assign) and len(st.targets) == 1 and isinstance(st.targets[0], ast.Name) and isinstance(st.value, ast.Call)
              and isinstance(st.value.func, ast.Attribute) and st.value.func.attr == "fit" and isinstance(st.value.func.value, ast.Call)):
            var, fit_call = st.targets[0].id, st.value
        if fit_call is None:
            continue
        used = any(isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == var
                   and n.attr in ("predict", "predict_proba", "decision_function", "score") for n in ast.walk(loop))
        if not used:
            continue
        if not all(isinstance(a, ast.Name) for a in fit_call.args):
            raise NA("the outer .fit(...) arguments must be plain array names")
        refit = ast.Expr(value=ast.Call(func=ast.Attribute(value=ast.Name(id=var, ctx=ast.Load()), attr="fit", ctx=ast.Load()),
                                        args=[parse_expr(f"_g9_take({a.id}, {tr})") for a in fit_call.args], keywords=[]), lineno=0)
        if isinstance(st, ast.Assign):  # keep the constructor binding
            fn.body[i] = ast.Assign(targets=st.targets, value=copy.deepcopy(fit_call.func.value), lineno=0)
        else:
            del fn.body[i]
        loop.body.insert(0, refit)
        _ensure_helpers(tree)
        return tree
    raise NA(f"no model fitted once before the fold loop and used to predict inside it in '{step}'")


# ---------------- compile ----------------
def apply_op(tree, op):
    if not isinstance(op, dict) or op.get("op") not in OPS:
        raise OpError("UNKNOWN_OP", f"op must be one of {list(OPS)} (got {op.get('op') if isinstance(op, dict) else op!r})")
    o = op["op"]
    want = set(OP_SPEC["ops"][o]["params"]) | {"op"}
    extra = set(op) - want
    if extra:
        raise OpError("BAD_PARAM", f"{o}: unexpected parameter(s) {sorted(extra)} (allowed: {sorted(want - {'op'})})")
    if o == "move_into_fold":
        return op_move_into_fold(tree, op.get("step"), op.get("call"))
    if o == "drop_from_eval":
        return op_drop_from_eval(tree, op.get("step"), op.get("call"))
    if o == "replace_split":
        return op_replace_split(tree, op.get("step"), op.get("kind"), op.get("col"))
    return op_retrain_inside(tree, op.get("step"))


def compile_ops(train_src, ops):
    """Apply ops in order to the ORIGINAL train.py text; returns new source (with controlled_eval appended). Raises OpError."""
    tree = ast.parse(train_src)
    for op in ops:
        tree = apply_op(copy.deepcopy(tree), op) if False else apply_op(tree, op)
    ast.fix_missing_locations(tree)
    src = ast.unparse(tree)
    try:
        compile(src, "<g9>", "exec")
    except SyntaxError as e:  # a template bug, never a model error
        raise OpError("INTERNAL", f"compiled source does not parse: {e}") from e
    return src + CONTROLLED


def factor_ids(plan):
    return [f.get("id") for f in plan["factors"]]


def compile_plan(train_src, plan):
    """-> {"layout": "single"|"factorial", "configs": {name: {"src"|None, "ops", "error"|None}}}.
    k == 1: one config 'fix_all'. k >= 2: fix_<id> for each factor plus fix_all (factorial layout only when k >= 2)."""
    facs = plan["factors"]
    k = len(facs)
    cfgs = {}
    sets = {"fix_all": [op for f in facs for op in f["ops"]]} if k == 1 else {**{f"fix_{f['id']}": list(f["ops"]) for f in facs},
                                                                               "fix_all": [op for f in facs for op in f["ops"]]}
    for name, ops in sets.items():
        try:
            cfgs[name] = {"src": compile_ops(train_src, ops), "ops": ops, "error": None}
        except OpError as e:
            cfgs[name] = {"src": None, "ops": ops, "error": f"{e.code}: {e.msg}"}
    return {"layout": "single" if k == 1 else "factorial", "configs": cfgs}


def legacy_sources(compiled):
    """Adapter for the frozen 2x2 sandbox (fix_A/fix_B/fix_both). k == 2 maps directly; k == 1 gives the SAME source to all three
    (an adapter for plumbing only: it is not a factorial). k >= 3 is refused."""
    c = compiled["configs"]
    if compiled["layout"] == "single":
        s = c["fix_all"]["src"]
        return {"fix_A": s, "fix_B": s, "fix_both": s}
    ids = [n[4:] for n in c if n != "fix_all"]
    if len(ids) != 2:
        raise OpError("BAD_PARAM", "the legacy 2x2 sandbox takes at most 2 factors")
    return {"fix_A": c[f"fix_{ids[0]}"]["src"], "fix_B": c[f"fix_{ids[1]}"]["src"], "fix_both": c["fix_all"]["src"]}
