"""G5 patch-fidelity guard (design: docs/EVAL-5.md section 1). Deterministic, no model calls.

A planner fix is a STRUCTURED EDIT against named steps (top-level functions) of the ORIGINAL train.py:
    {"kind": "split" | "fit_scope" | "feature", "steps": {"<function name>": "<complete new def source>"}}
Code applies it (apply_edits); the model never writes a whole file. The controlled pipeline of a config is the edited
module's claimed_eval(df, seed), so everything the planner did not name is byte-identical to the claim's code.

check_static() then compares the claimed pipeline and the controlled one (code reachable from claimed_eval /
controlled_eval, `train.X` resolved to train.py) on protected invariants:
  LOCALITY  only the declared steps differ at top level (AST diff); a declared step must really change.
  MODEL     learned components (estimator / transformer / selector / tuner constructors, with their arguments) and
            label-driven selection calls (corrcoef, corr, f_classif, mutual_info, feature_importances_, ...): the
            SET must be IDENTICAL (nothing added, removed or re-parameterised). No kind may change the model; a fix may only move where a component is fit.
  FEATURES  the feature-list step (feats) and every column-filter comprehension / .drop(columns=...): unchanged
            unless the fix declares kind 'feature'.
  SPLIT     the evaluation splitter calls and test_size defaults: unchanged unless the fix declares kind 'split'.
            Adding KFold / StratifiedKFold / GroupKFold (out-of-fold statistics inside training rows) is allowed.
  METRIC    fixed by construction: the sandbox computes accuracy from the returned (y_true, y_pred).
check_runtime() after execution: SAMPLE SIZE, the test n per seed must equal the original's unless kind 'split'.
Any violation REJECTS the patch. Legacy whole-file patches (G4 and earlier) can be replayed with check_static(...,
patch_src=...) for the invariants; they always also fail the STRUCTURE rule."""
import ast
import re
from collections import Counter

KINDS = ("split", "fit_scope", "feature")
LEARNER_SUFFIX = ("Classifier", "Regressor", "Regression", "SVC", "SVR", "NB", "PCA", "SVD", "Scaler", "Imputer",
                  "Encoder", "SelectKBest", "SelectPercentile", "SelectFromModel", "RFE", "RFECV", "GridSearchCV",
                  "RandomizedSearchCV", "VarianceThreshold", "Normalizer", "NMF", "ICA", "Discriminant", "Analysis",
                  "Perceptron", "Neighbors", "MLP", "Booster", "Lasso", "Ridge", "ElasticNet", "Transformer")
WRAPPERS = {"Pipeline", "make_pipeline", "ColumnTransformer", "make_column_transformer", "FunctionTransformer"}
SELECTION = {"corrcoef", "corr", "corrwith", "f_classif", "f_regression", "mutual_info_classif",
             "mutual_info_regression", "chi2", "r_regression", "feature_importances_", "coef_", "permutation_importance"}
SPLITTERS = {"train_test_split", "KFold", "StratifiedKFold", "GroupKFold", "StratifiedGroupKFold", "ShuffleSplit",
             "StratifiedShuffleSplit", "GroupShuffleSplit", "LeaveOneGroupOut", "LeavePGroupsOut", "LeaveOneOut",
             "TimeSeriesSplit", "PredefinedSplit", "RepeatedKFold", "RepeatedStratifiedKFold", "cross_val_predict",
             "cross_val_score", "cross_validate"}
OOF_OK = {"KFold", "StratifiedKFold", "GroupKFold"}  # may be ADDED by a fit_scope fix (out-of-fold stats on training rows)
FORBIDDEN_STEPS = {"load"}  # data loading is shared by every config


class _StripTrain(ast.NodeTransformer):
    """train.X -> X, so a patch that reuses train's objects compares equal to train.py itself."""
    def visit_Attribute(self, node):
        self.generic_visit(node)
        if isinstance(node.value, ast.Name) and node.value.id == "train":
            return ast.copy_location(ast.Name(id=node.attr, ctx=node.ctx), node)
        return node


def _norm(node):
    return ast.unparse(_StripTrain().visit(ast.parse(ast.unparse(node))))


def _fname(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _call_sig(call):
    """Order-insensitive normalised text of a call: name(sorted args; sorted kwargs)."""
    args = sorted(_norm(a) for a in call.args)
    kws = sorted((k.arg or "**") + "=" + _norm(k.value) for k in call.keywords)
    return f"{_fname(call)}({', '.join(args + kws)})"


def _is_learner(name):
    return bool(name) and name[0].isupper() and name not in WRAPPERS and (name.endswith(LEARNER_SUFFIX) or name in {"PCA", "SVC", "SVR"})


def _defs(tree):
    return {n.name: n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _reachable(start, local_defs, train_defs):
    """Function defs reachable from `start` (a def node). Bare names resolve to local defs first, then train;
    train.X resolves to train. Each def is counted once (keyed by origin and name)."""
    seen, stack = {}, [("local", start)]
    while stack:
        origin, node = stack.pop()
        key = (origin, node.name)
        if key in seen:
            continue
        seen[key] = node
        for sub in ast.walk(node):
            if isinstance(sub, ast.Attribute) and isinstance(sub.value, ast.Name) and sub.value.id == "train":
                if sub.attr in train_defs:
                    stack.append(("train", train_defs[sub.attr]))
            elif isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
                pool = local_defs if origin == "local" else train_defs
                if sub.id in pool and sub.id != node.name:
                    stack.append((origin, pool[sub.id]))
                elif origin == "local" and sub.id in train_defs and sub.id not in local_defs:
                    stack.append(("train", train_defs[sub.id]))
    return seen


def fingerprint(defs):
    """Protected invariants over a set of reachable function defs {(origin, name): node}."""
    model, selection, split, feat_filters, test_sizes, feats_src = Counter(), Counter(), Counter(), Counter(), Counter(), []
    feats_comps = set()
    for (origin, name), node in defs.items():
        if name == "feats":
            feats_src.append(_norm(node))
            feats_comps |= {_norm(sub) for sub in ast.walk(node) if isinstance(sub, (ast.ListComp, ast.GeneratorExp))}
        for a, d in zip(node.args.args[len(node.args.args) - len(node.args.defaults):], node.args.defaults):
            if a.arg in ("test_size", "n_splits", "train_size"):
                test_sizes[f"{a.arg}={_norm(d)}"] += 1
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                fn = _fname(sub)
                if _is_learner(fn):
                    model[_call_sig(sub)] += 1
                if fn in SPLITTERS:
                    split[_call_sig(sub)] += 1
                if fn == "drop" and any(k.arg == "columns" for k in sub.keywords):
                    feat_filters[_norm(sub)] += 1
            if isinstance(sub, ast.Name) and sub.id in SELECTION:
                selection[sub.id] += 1
            elif isinstance(sub, ast.Attribute) and sub.attr in SELECTION:
                selection[sub.attr] += 1
            if name != "feats" and isinstance(sub, (ast.ListComp, ast.GeneratorExp)):
                if any(isinstance(c, ast.Compare) for g in sub.generators for i in g.ifs for c in ast.walk(i)):
                    feat_filters[_norm(sub)] += 1
    return {"model": model, "selection": selection, "split": split, "feature_filters": feat_filters,
            "test_size_defaults": test_sizes, "feats": sorted(feats_src), "feats_comps": sorted(feats_comps)}


def _counter_diff(a, b):
    """Set semantics: the SAME component reached twice (e.g. a legacy patch with a fixed and an unfixed branch) is
    not a change; a new or altered component, or a missing one, is."""
    return {"removed": sorted(set(a) - set(b)), "added": sorted(set(b) - set(a))}


def _differ(a, b):
    return set(a) != set(b)


def compare(orig_fp, new_fp, kinds):
    """Violations of the protected invariants given the declared kinds of this config."""
    kinds, v = set(kinds), []
    if _differ(orig_fp["model"], new_fp["model"]):
        v.append(f"MODEL changed (no fix may change the model): {_counter_diff(orig_fp['model'], new_fp['model'])}")
    if _differ(orig_fp["selection"], new_fp["selection"]):
        v.append("MODEL changed: label-driven feature selection / importance calls differ "
                 f"{_counter_diff(orig_fp['selection'], new_fp['selection'])} (choosing columns by their association "
                 "with the label is a modelling change, not an evaluation fix)")
    if "feature" not in kinds:
        inline_only = (not new_fp["feats"] and orig_fp.get("feats_comps")
                       and set(orig_fp["feats_comps"]) <= set(new_fp["feature_filters"]))  # G6: feats inlined verbatim
        if _differ(orig_fp["feats"], new_fp["feats"]) and not inline_only:
            v.append("FEATURES changed: the feature-list step differs but no declared step has kind 'feature'")
        ff = _counter_diff(orig_fp["feature_filters"], new_fp["feature_filters"])
        inlined = set(orig_fp.get("feats_comps", ()))  # G6: a verbatim inline of feats' own comprehension is not a change
        if ff["removed"] or [a for a in ff["added"] if a not in inlined]:
            v.append(f"FEATURES changed: column filters differ {_counter_diff(orig_fp['feature_filters'], new_fp['feature_filters'])} "
                     "but no declared step has kind 'feature'")
    if "split" not in kinds:
        d = _counter_diff(orig_fp["split"], new_fp["split"])
        bad_add = [s for s in d["added"] if s.split("(")[0] not in OOF_OK]
        if d["removed"] or bad_add:
            v.append(f"SPLIT changed: evaluation splitter calls differ (removed {d['removed']}, added {bad_add}) "
                     "but no declared step has kind 'split'")
        if _differ(orig_fp["test_size_defaults"], new_fp["test_size_defaults"]):
            v.append("SAMPLE SIZE changed: test_size / n_splits defaults differ but no declared step has kind 'split'")
    return v


# ---------------- structured edits ----------------
def parse_replacement(step, src):
    """-> (FunctionDef, [import nodes]) or raises ValueError with a guard message."""
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise ValueError(f"STRUCTURE: replacement for step '{step}' does not parse: {e}") from e
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    other = [n for n in tree.body if not isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))
             and not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    if len(fns) != 1 or fns[0].name != step or other:
        raise ValueError(f"STRUCTURE: replacement for step '{step}' must be exactly one top-level def named '{step}' "
                         f"(got defs {[f.name for f in fns]} and {len(other)} other top-level statements)")
    for imp in imports:
        mod = imp.module if isinstance(imp, ast.ImportFrom) else imp.names[0].name
        if not re.match(r"^(numpy|pandas|sklearn)(\.|$)", mod or ""):
            raise ValueError(f"STRUCTURE: replacement for step '{step}' imports '{mod}' (only numpy/pandas/sklearn)")
    return fns[0], imports


def apply_edits(train_src, steps):
    """Replace the named top-level defs of train_src. Returns (new_src, violations). Code does the edit, not the model."""
    tree = ast.parse(train_src)
    defs = _defs(tree)
    violations, new_nodes, imports = [], {}, []
    for step, src in steps.items():
        if step in FORBIDDEN_STEPS:
            violations.append(f"STRUCTURE: step '{step}' (data loading) may not be edited")
            continue
        if step not in defs:
            violations.append(f"STRUCTURE: '{step}' is not a step of train.py (steps: {sorted(defs)})")
            continue
        try:
            fn, imps = parse_replacement(step, src)
        except ValueError as e:
            violations.append(str(e))
            continue
        new_nodes[step], imports = fn, imports + imps
    body = []
    for n in tree.body:
        body.append(new_nodes.get(n.name, n) if isinstance(n, ast.FunctionDef) else n)
    first_def = next((i for i, n in enumerate(body) if not isinstance(n, (ast.Import, ast.ImportFrom, ast.Expr))), 0)
    body[first_def:first_def] = imports
    tree.body = body
    return ast.unparse(ast.fix_missing_locations(tree)), violations


def changed_steps(orig_src, new_src):
    """Top-level AST diff: names of defs that differ, plus any non-def top-level change other than added imports."""
    a, b = ast.parse(orig_src), ast.parse(new_src)
    da, db = _defs(a), _defs(b)
    changed = sorted(n for n in set(da) | set(db) if n not in da or n not in db or ast.dump(da[n]) != ast.dump(db[n]))
    rest = lambda t: [ast.dump(n) for n in t.body if not isinstance(n, (ast.FunctionDef, ast.Import, ast.ImportFrom))]  # noqa: E731
    imps = lambda t: {ast.dump(n) for n in t.body if isinstance(n, (ast.Import, ast.ImportFrom))}  # noqa: E731
    if rest(a) != rest(b):
        changed.append("<module-level statements>")
    if not imps(a) <= imps(b):
        changed.append("<imports removed>")
    return changed


CONTROLLED = "\n\n\ndef controlled_eval(df, seed):\n    return claimed_eval(df, seed)\n"


def build_configs(train_src, edits):
    """edits = {"A": {"kind", "steps"}, "B": {"kind", "steps"}, "both_overrides": {step: src}}.
    Returns {config: {"src", "kinds", "declared", "violations"}} for fix_A / fix_B / fix_both."""
    out = {}
    try:
        A, B = edits["A"], edits["B"]
        sa, sb = dict(A["steps"]), dict(B["steps"])
    except (KeyError, TypeError) as e:
        v = [f"STRUCTURE: edits must have A and B, each with 'kind' and 'steps' ({e!r})"]
        return {c: {"src": None, "kinds": [], "declared": [], "violations": v} for c in ("fix_A", "fix_B", "fix_both")}
    both = {**sa, **sb}
    overlap = set(sa) & set(sb)
    over = edits.get("both_overrides") or {}
    missing = [s for s in overlap if s not in over]
    for s in overlap:
        if s in over:
            both[s] = over[s]
    plan = {"fix_A": (sa, [A.get("kind")]), "fix_B": (sb, [B.get("kind")]), "fix_both": (both, [A.get("kind"), B.get("kind")])}
    for cfg, (steps, kinds) in plan.items():
        v = []
        for k in kinds:
            if k not in KINDS:
                v.append(f"STRUCTURE: kind {k!r} is not one of {KINDS} (a fix may never change the model or the metric)")
        if not steps:
            v.append("STRUCTURE: no step declared")
        if cfg == "fix_both" and missing:
            v.append(f"STRUCTURE: A and B both edit {sorted(missing)}; give the combined def in both_overrides")
        src, av = apply_edits(train_src, steps)
        v += av
        out[cfg] = {"src": src + CONTROLLED, "kinds": kinds, "declared": sorted(steps), "violations": v}
    return out


def check_static(train_src, cfg_src=None, kinds=(), declared=None, patch_src=None):
    """Static fidelity check of one config.
    Structured: cfg_src = edited train.py (+controlled_eval), declared = its declared steps.
    Legacy replay: patch_src = a whole-file controlled_eval module that does `import train`."""
    tree_o = ast.parse(train_src)
    do = _defs(tree_o)
    orig_fp = fingerprint(_reachable(do["claimed_eval"], do, do))
    v = []
    if patch_src is not None:
        v.append("STRUCTURE: whole-file patch (not a structured edit against named steps of train.py)")
        tp = ast.parse(patch_src)
        dp = _defs(tp)
        if "controlled_eval" not in dp:
            return v + ["STRUCTURE: no controlled_eval"], {"changed": None}
        new_fp = fingerprint(_reachable(dp["controlled_eval"], dp, do))
        return v + compare(orig_fp, new_fp, kinds), {"changed": None, "orig_fp": orig_fp, "new_fp": new_fp}
    dn = _defs(ast.parse(cfg_src))
    new_fp = fingerprint(_reachable(dn["claimed_eval"], dn, dn))
    changed = [c for c in changed_steps(train_src, cfg_src.replace(CONTROLLED, "")) if c != "controlled_eval"]
    extra = [c for c in changed if c not in (declared or [])]
    if extra:
        v.append(f"LOCALITY: steps changed outside the declared ones: {extra}")
    noop = [s for s in (declared or []) if s not in changed]
    if noop:
        v.append(f"LOCALITY: declared step(s) {noop} are unchanged (a fix must change its step)")
    return v + compare(orig_fp, new_fp, kinds), {"changed": changed, "orig_fp": orig_fp, "new_fp": new_fp}


def check_runtime(raw_result, kinds):
    """SAMPLE SIZE: test n per seed must equal the original's unless a declared kind is 'split'.
    raw_result = executor result {"seeds": {s: {"orig": {"y"}, "fix_A": ...}}}; kinds = {config: [kinds]}."""
    v = []
    for s, res in raw_result["seeds"].items():
        n0 = len(res["orig"]["y"])
        for cfg, ks in kinds.items():
            n = len(res[cfg]["y"])
            if "split" not in ks and n != n0:
                v.append(f"SAMPLE SIZE: {cfg} seed {s} test n {n} != original {n0} but no declared step has kind 'split'")
    return v


def verdict_line(cfg_info, static_report):
    ch = static_report.get("changed") or []
    return f"only step(s) {', '.join(ch)} changed ({'/'.join(k for k in cfg_info['kinds'] if k)})"


# ---------------- G6: justification rules (design: docs/EVAL-6.md section 3) ----------------
TEMPORAL_CLAIM_WORDS = ("forecast", "future", "later year", "later period", "prospective", "temporal", "chronolog",
                        "over time", "ahead", "upcoming", "years they were not trained on", "later years")
TIME_NAME = re.compile(r"(year|date|time|month|week|period|_t$|^t$)", re.I)
RANDOM_CALLS = {"permutation", "shuffle", "choice", "default_rng", "RandomState", "sample", "integers", "rand", "randint"}
ORDER_CALLS = {"sort_values", "argsort", "sort", "sort_index", "TimeSeriesSplit"}


def _ws(t):
    return re.sub(r"\s+", " ", t).strip()


def _literals(node):
    return {sub.value for sub in ast.walk(node) if isinstance(sub, ast.Constant) and isinstance(sub.value, str)}


def _ordered_split_markers(node):
    """Evidence that a step holds rows out by ORDER (time / position) rather than at random or by group."""
    m = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if _fname(sub) in ORDER_CALLS:
                m.add(_fname(sub))
            for k in sub.keywords:
                if k.arg == "shuffle" and isinstance(k.value, ast.Constant) and k.value.value is False:
                    m.add("shuffle=False")
        if isinstance(sub, ast.Subscript) and isinstance(sub.slice, ast.Slice):
            bounds = [b for b in (sub.slice.lower, sub.slice.upper) if b is not None]
            if any(isinstance(x, ast.Call) and _fname(x) in ("int", "round", "len") or isinstance(x, ast.BinOp) for b in bounds for x in ast.walk(b)):
                m.add("positional slice")
        if isinstance(sub, ast.Compare):
            names = {x.value for x in ast.walk(sub) if isinstance(x, ast.Constant) and isinstance(x.value, str)}
            names |= {x.id for x in ast.walk(sub) if isinstance(x, ast.Name)}
            if any(TIME_NAME.search(n) for n in names):
                m.add("time comparison")
    return m


def check_justification(train_src, excerpt, header_cols, plan):
    """G6 rules on top of check_static (deterministic, no model call):
    FEATURE-REASON  a 'feature' fix that names a data column the original step did not name must cite evidence: its
                    cited line (X_code_line, or edits[X]['evidence']) must occur verbatim (whitespace-normalised) in
                    train.py or the excerpt AND contain every newly named column. A column known only from the data
                    head cannot be justified, so it cannot be dropped.
    SPLIT-USE       a 'split' fix that introduces an ORDERED hold-out (sort / shuffle=False / positional slice /
                    comparison on a time-like column / TimeSeriesSplit) is allowed only if the excerpt states a
                    temporal intended use (forecasting, future or later periods, ...). Random and group hold-outs are
                    not gated here.
    Returns a list of violations (empty = accepted)."""
    v = []
    edits = (plan or {}).get("edits") or {}
    orig = _defs(ast.parse(train_src))
    corpus = _ws(train_src) + "\n" + _ws(excerpt)
    cols = set(header_cols)
    items = []
    for X in ("A", "B"):
        e = edits.get(X) or {}
        items += [(X, e, e.get("kind"), step, src) for step, src in (e.get("steps") or {}).items()]
    for step, src in (edits.get("both_overrides") or {}).items():  # combined defs are held to the rules of both fixes
        for X in ("A", "B"):
            e = edits.get(X) or {}
            if step in (e.get("steps") or {}):
                items.append((X, e, e.get("kind"), step, src))
    if True:
        for X, e, kind, step, src in items:
            try:
                fn, _ = parse_replacement(step, src)
            except ValueError:
                continue  # STRUCTURE is reported by build_configs
            old = orig.get(step)
            if kind == "feature":
                named = (_literals(fn) - (_literals(old) if old else set())) & cols
                if named:
                    cite = _ws(str(e.get("evidence") or plan.get(f"{X}_code_line") or ""))
                    if not cite or cite not in corpus:
                        v.append(f"FEATURE-REASON: fix {X} names column(s) {sorted(named)} but its cited line is not "
                                 "verbatim in train.py or the excerpt")
                    elif [c for c in named if c not in cite]:
                        v.append(f"FEATURE-REASON: fix {X} names column(s) {sorted(c for c in named if c not in cite)} "
                                 "that its cited line does not mention (a column seen only in the data head cannot be justified)")
            if kind == "split":
                new_m = _ordered_split_markers(fn) - (_ordered_split_markers(old) if old else set())
                calls = lambda n: {_fname(c) for c in ast.walk(n) if isinstance(c, ast.Call)}  # noqa: E731
                if old and calls(old) & SPLITTERS and not calls(fn) & (SPLITTERS | RANDOM_CALLS):
                    new_m.add("random splitter replaced by a deterministic hold-out")
                if new_m and not any(w in excerpt.lower() for w in TEMPORAL_CLAIM_WORDS):
                    v.append(f"SPLIT-USE: fix {X} introduces an ordered hold-out ({sorted(new_m)}) but the excerpt "
                             "states no temporal intended use")
    return v
