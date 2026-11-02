"""NullLab EVAL-8: a NO-LLM, RULE-BASED leakage-fix baseline (design + preregistration: runs_rulefix/PREREG.md).

A fixed library of five standard leakage remedies. Each rule has a DETECTOR (a static look at train.py plus a label-free
dry run of the claim's own split, plus column statistics of data.csv) and a REMEDY (a source rewrite of train.py). Every
rule whose detector fires is applied, blindly, with no model call and no look at any result.

  R1 random hold-out rescore      the claim scores rows it trained on  -> stratified random 25% hold-out
  R2 refit inside folds           scaler / PCA / selector fit on rows later scored -> fit on the training rows only
  R3 group-aware split            an id-like column repeats across the claim's split -> GroupShuffleSplit on that column
  R4 temporal split               a time column exists and the split is not ordered by it -> train earliest 75%, test latest 25%
  R5 drop duplicates              exact duplicate rows in data.csv -> drop_duplicates before the claim's evaluation

Factorial layout (same sandbox, same statistics, same verdict contract as the loop):
  fix_A    = the fired rules of the SPLIT/DATA family (R1, R3, R4, R5)
  fix_B    = the fired rule of the FIT-SCOPE family (R2)
  fix_both = every fired rule.   Verdict = sign of the unpaired-bootstrap CI of (orig - fix_both), as in g4/g5/g6.
Precedence when several split rules fire (one splitter can exist): R4 > R3 > R1.

Limits, stated up front: the rules match code IDIOMS of the benchmark (a top-level split function called as
`tr, te = f(df, seed)`, a transformer fit in a top-level function, a selector hoisted out of a CV loop). The author of this
module had read the benchmark train.py files, so the baseline is, if anything, OPTIMISTIC for rules. Column detection uses
statistics and names only through the time-name regex; hashed (c_xxxxxx) columns carry no names, so R4 cannot fire on them."""
import ast
import hashlib
import importlib.util
import json
import re
import sys
import textwrap
from pathlib import Path

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True

HOLDOUT = 0.25
SPLIT_PRECEDENCE = ("R4", "R3", "R1")
FACTOR_A, FACTOR_B = ("R1", "R3", "R4", "R5"), ("R2",)
TRANSFORMER_RE = re.compile(r"(Scaler$|^PCA$|^TruncatedSVD$|^SelectKBest$|^SelectPercentile$|^SelectFromModel$|"
                            r"^VarianceThreshold$|^Normalizer$|^PowerTransformer$|^QuantileTransformer$)")
PIPE_WRAPPERS = {"Pipeline", "make_pipeline", "ColumnTransformer", "make_column_transformer"}
TIME_NAME_RE = re.compile(r"(year|date|time|month|week|period)", re.I)

RULES = {
    "R1": {"name": "random hold-out rescore", "family": "A",
           "detector": "claimed_eval calls a top-level split function `tr, te = f(df, seed)`; a label-free dry run of that call "
                       "returns scoring rows of which >= 50% are also training rows",
           "remedy": f"replace the split function by a stratified (on TARGET) random hold-out, test_size={HOLDOUT}, random_state=seed"},
    "R2": {"name": "refit inside folds (scaling / feature selection)", "family": "B",
           "detector": "a top-level function F builds a scaler/PCA/selector (class name matches TRANSFORMER_RE) OUTSIDE any "
                       "Pipeline/make_pipeline/ColumnTransformer, calls .fit/.fit_transform, and every call to F passes un-sliced "
                       "arguments (no Subscript argument)",
           "remedy": "mode scope (a split function exists): F's transformers are fit on the training rows of the claim's own split "
                     "and transform every row; mode hoist (selection before a CV loop): the selector call moves inside the loop and "
                     "is fit on each fold's training rows; no applicable idiom => reported as detected-not-applied"},
    "R3": {"name": "group-aware split", "family": "A",
           "detector": "an integer column that feats(df) leaves out of the model (metadata), is not time-named, has 3 <= nunique <= "
                       "n/2 (the one with most distinct values is chosen), and > 5% of the claim's scored rows share its value with a "
                       "training row (dry run of the claim's split)",
           "remedy": f"replace the split function by GroupShuffleSplit(test_size={HOLDOUT}, random_state=seed) on that column"},
    "R4": {"name": "temporal split", "family": "A",
           "detector": "a numeric column that feats(df) leaves out, whose NAME matches year|date|time|month|week|period, nunique >= 5, "
                       "and the claim's split is not ordered by it (max(train time) > min(test time) in the dry run)",
           "remedy": f"replace the split function by: sort rows by that column (stable), train = earliest {1 - HOLDOUT:.0%}, test = latest {HOLDOUT:.0%}"},
    "R5": {"name": "drop duplicate rows", "family": "A",
           "detector": "data.csv has >= 1 exact duplicate row",
           "remedy": "df = df.drop_duplicates().reset_index(drop=True) as the first statement of claimed_eval"},
}


def spec():
    """The preregistered rule set (hashed into PREREG.md)."""
    return {"rules": RULES, "holdout": HOLDOUT, "split_precedence": SPLIT_PRECEDENCE, "factor_A": FACTOR_A, "factor_B": FACTOR_B,
            "transformer_re": TRANSFORMER_RE.pattern, "time_name_re": TIME_NAME_RE.pattern,
            "pipe_wrappers": sorted(PIPE_WRAPPERS)}


def spec_sha256():
    return hashlib.sha256(json.dumps(spec(), sort_keys=True).encode()).hexdigest()


# ---------------- detection ----------------
def _fname(call):
    f = call.func
    return f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else "")


def _defs(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}


def _load_train(case_dir):
    case_dir = Path(case_dir)
    spec_ = importlib.util.spec_from_file_location("rulefix_train_" + case_dir.name, case_dir / "train.py")
    m = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(m)
    return m


def _is_splitter(fn):
    """A split function: its name says split, or its body calls something named split (train_test_split, .split, ...)."""
    return "split" in fn.name.lower() or any(isinstance(n, ast.Call) and "split" in _fname(n).lower() for n in ast.walk(fn))


def _find_split(tree):
    """-> (index in claimed_eval body, Assign node, split function name) for `tr, te = f(...)`, or None."""
    d = _defs(tree)
    ce = d.get("claimed_eval")
    if ce is None:
        return None
    for i, s in enumerate(ce.body):
        if (isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Tuple)
                and len(s.targets[0].elts) == 2 and all(isinstance(e, ast.Name) for e in s.targets[0].elts)
                and isinstance(s.value, ast.Call) and isinstance(s.value.func, ast.Name) and s.value.func.id in d
                and s.value.func.id != "claimed_eval" and _is_splitter(d[s.value.func.id])):
            return i, s, s.value.func.id
    return None


def _dry_split(mod, tree, df, seed):
    """Label-free dry run of the claim's own split: runs the statements of claimed_eval that precede the split call, then the
    split call. Returns (train_idx, test_idx, frame passed to the split) or None."""
    found = _find_split(tree)
    if found is None:
        return None
    i, asg, _ = found
    ce = _defs(tree)["claimed_eval"]
    pre = [s for s in ce.body[:i] if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
    tr_n, te_n = (e.id for e in asg.targets[0].elts)
    body = "\n".join(ast.unparse(s) for s in pre) or "pass"
    src = (f"def _dry({ast.unparse(ce.args)}):\n{textwrap.indent(body, '    ')}\n    {ast.unparse(asg)}\n"
           f"    return {tr_n}, {te_n}, {ast.unparse(asg.value.args[0])}\n")
    ns = dict(mod.__dict__)
    try:
        exec(compile(src, "<rulefix-dry>", "exec"), ns)
        tr, te, d0 = ns["_dry"](df.copy(), seed)
    except Exception:  # noqa: BLE001  (an unrunnable prefix means the rule cannot be judged: it does not fire)
        return None
    return np.asarray(tr), np.asarray(te), d0


def _outside_pipeline_ctors(fn):
    """Transformer constructor calls in `fn` that are not arguments of a Pipeline-like call."""
    inside = set()
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and _fname(n) in PIPE_WRAPPERS:
            for sub in ast.walk(n):
                if sub is not n:
                    inside.add(id(sub))
    return [n for n in ast.walk(fn) if isinstance(n, ast.Call) and TRANSFORMER_RE.search(_fname(n)) and id(n) not in inside]


def _leaky_fit_functions(tree):
    """Top-level functions that fit a transformer outside a pipeline, called only with un-sliced arguments."""
    d = _defs(tree)
    calls = {}
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in d:
            calls.setdefault(n.func.id, []).append(n)
    out = []
    for name, fn in d.items():
        ctors = _outside_pipeline_ctors(fn)
        fits = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and _fname(n) in ("fit", "fit_transform")]
        if not ctors or not fits:
            continue
        cs = [c for c in calls.get(name, []) if c is not None]
        if not cs:
            continue
        sliced = any(isinstance(a, ast.Subscript) or any(isinstance(x, ast.Subscript) for x in ast.walk(a))
                     for c in cs for a in list(c.args) + [k.value for k in c.keywords])
        if not sliced:
            out.append({"fn": name, "ctors": sorted({_fname(c) for c in ctors}), "calls": cs})
    return out


def _hoist_site(tree, leaky):
    """ESL idiom: in claimed_eval `keep = F(X, y)` ... `G(X[:, keep], y, ...)` where G loops `for tr, te in <cv>.split(...)`."""
    ce = _defs(tree).get("claimed_eval")
    d = _defs(tree)
    names = {x["fn"] for x in leaky}
    for s in ce.body:
        if (isinstance(s, ast.Assign) and len(s.targets) == 1 and isinstance(s.targets[0], ast.Name)
                and isinstance(s.value, ast.Call) and isinstance(s.value.func, ast.Name) and s.value.func.id in names):
            keep, F, fargs = s.targets[0].id, s.value.func.id, s.value.args
            for c in ast.walk(ce):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id in d and c.func.id not in (F, "claimed_eval"):
                    for ai, a in enumerate(c.args):
                        if (isinstance(a, ast.Subscript) and isinstance(a.value, ast.Name)
                                and any(isinstance(x, ast.Name) and x.id == keep for x in ast.walk(a.slice))):
                            G = d[c.func.id]
                            loops = [f for f in ast.walk(G) if isinstance(f, ast.For) and isinstance(f.target, ast.Tuple)
                                     and isinstance(f.iter, ast.Call) and _fname(f.iter) == "split"]
                            if loops and len(fargs) >= 1 and all(isinstance(x, ast.Name) for x in fargs):
                                # map F's args (names in claimed_eval) to G's parameters through G's call arguments
                                cargs = {}
                                for pi, ca in enumerate(c.args):
                                    base = ca.value if isinstance(ca, ast.Subscript) else ca
                                    if isinstance(base, ast.Name) and pi < len(G.args.args):
                                        cargs[base.id] = G.args.args[pi].arg
                                if all(x.id in cargs for x in fargs):
                                    return {"assign": s, "keep": keep, "F": F, "G": G.name, "call": c, "arg_index": ai,
                                            "G_params": [cargs[x.id] for x in fargs], "loop": loops[0]}
    return None


def detect(case_dir):
    """Label-free detection of which rules fire. No model, no scoring."""
    case_dir = Path(case_dir)
    src = (case_dir / "train.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    df = pd.read_csv(case_dir / "data.csv")
    mod = _load_train(case_dir)
    target = getattr(mod, "TARGET", None)
    n = len(df)
    det = {"case": case_dir.name, "n_rows": n, "split_fn": None, "fired": {}, "not_applied": [], "notes": []}
    found = _find_split(tree)
    if found:
        det["split_fn"] = found[2]
    try:
        fcols = list(mod.feats(df))
    except Exception as e:  # noqa: BLE001
        fcols = None
        det["notes"].append(f"feats(df) failed ({e!r}): no metadata columns, so R3/R4 cannot fire")
    meta = [c for c in df.columns if fcols is not None and c not in fcols and c != target]
    dry = _dry_split(mod, tree, df, 42) if found else None
    if found and dry is None:
        det["notes"].append("dry run of the claim's split failed: R1/R3/R4 cannot be judged")
    # R5
    ndup = int(df.duplicated().sum())
    if ndup:
        det["fired"]["R5"] = {"duplicate_rows": ndup}
    if dry is not None:
        tr, te, d0 = dry
        # R1
        ov = float(np.mean(np.isin(te, tr))) if len(te) else 0.0
        det["split_overlap_test_in_train"] = round(ov, 3)
        if ov >= 0.5:
            det["fired"]["R1"] = {"test_rows_also_in_train": round(ov, 3)}
        # R3
        ids = [c for c in meta if df[c].dtype.kind == "i" and not TIME_NAME_RE.search(c) and 3 <= df[c].nunique() <= n // 2]
        if ids and hasattr(d0, "columns"):
            col = max(ids, key=lambda c: df[c].nunique())
            if col in d0.columns:
                g = np.asarray(d0[col])
                share = float(np.mean(np.isin(g[te], np.unique(g[tr])))) if len(te) else 0.0
                det["group_candidate"] = {"column": col, "nunique": int(df[col].nunique()), "test_rows_sharing_group_with_train": round(share, 3)}
                if share > 0.05:
                    det["fired"]["R3"] = {"column": col, "nunique": int(df[col].nunique()), "test_rows_sharing_group_with_train": round(share, 3)}
        # R4
        tcols = [c for c in meta if df[c].dtype.kind in "if" and TIME_NAME_RE.search(c) and df[c].nunique() >= 5]
        if tcols and hasattr(d0, "columns"):
            col = max(tcols, key=lambda c: df[c].nunique())
            if col in d0.columns:
                t = np.asarray(d0[col], dtype=float)
                ordered = bool(len(te) and len(tr) and t[tr].max() <= t[te].min())
                det["time_candidate"] = {"column": col, "split_already_ordered": ordered}
                if not ordered:
                    det["fired"]["R4"] = {"column": col, "nunique": int(df[col].nunique())}
    # R2
    leaky = _leaky_fit_functions(tree)
    if leaky:
        site = _hoist_site(tree, leaky) if not found else None
        if found:
            info = {"mode": "scope", "functions": [x["fn"] for x in leaky], "transformers": sorted({c for x in leaky for c in x["ctors"]})}
            first_ok = all(len(_defs(tree)[x["fn"]].args.args) >= 1 for x in leaky)
            if first_ok:
                det["fired"]["R2"] = info
            else:
                det["fired"]["R2"] = {**info, "applicable": False}
        elif site:
            det["fired"]["R2"] = {"mode": "hoist", "functions": [site["F"]], "loop_function": site["G"],
                                  "transformers": sorted({c for x in leaky for c in x["ctors"]})}
        else:
            det["fired"]["R2"] = {"mode": "none", "applicable": False, "functions": [x["fn"] for x in leaky]}
    for r, v in det["fired"].items():
        if v.get("applicable") is False:
            det["not_applied"].append(r)
    return det


# ---------------- remedies ----------------
_SCOPE_HELPER = '''
_RF = {"seed": 0, "rows": None, "n": -1}


def _rf_take(obj, rows):
    return obj.iloc[rows] if hasattr(obj, "iloc") else obj[rows]


def _rf_scoped(cls):
    class _Scoped(cls):
        def fit(self, X, y=None, **kw):
            rows = _RF["rows"]
            if rows is not None and len(X) == _RF["n"]:
                X = _rf_take(X, rows)
                y = None if y is None else _rf_take(y, rows)
            return cls.fit(self, X, y, **kw)

        def fit_transform(self, X, y=None, **kw):
            return self.fit(X, y, **kw).transform(X)
    _Scoped.__name__ = cls.__name__
    return _Scoped


def _rf_wrap(fn, split_name):
    def wrapped(*a, **k):
        d0 = a[0]
        _RF["rows"], _RF["n"] = np.asarray(globals()[split_name](d0, _RF["seed"])[0]), len(d0)
        try:
            return fn(*a, **k)
        finally:
            _RF["rows"] = None
    wrapped.__name__ = fn.__name__
    return wrapped
'''
_HEADER = "import numpy as np\nimport pandas as pd\nfrom sklearn.model_selection import GroupShuffleSplit, train_test_split\n"


def _split_body(rule, det, has_target, dfn="df", sn="seed"):
    if rule == "R1":
        strat = f", stratify=np.asarray({dfn}[TARGET])" if has_target else ""
        return f"idx = np.arange(len({dfn}))\nreturn train_test_split(idx, test_size={HOLDOUT}, random_state={sn}{strat})"
    if rule == "R3":
        col = det["fired"]["R3"]["column"]
        return (f"idx = np.arange(len({dfn}))\nreturn next(GroupShuffleSplit(n_splits=1, test_size={HOLDOUT}, random_state={sn})"
                f".split(idx, groups=np.asarray({dfn}[{col!r}])))")
    col = det["fired"]["R4"]["column"]
    return (f"order = np.argsort(np.asarray({dfn}[{col!r}], dtype=float), kind='stable')\n"
            f"cut = int(round({1 - HOLDOUT} * len(order)))\nreturn order[:cut], order[cut:]")


class _Hoist(ast.NodeTransformer):
    def __init__(self, params, keep_name, loop_vars):
        self.params, self.keep, self.tr, self.te = params, keep_name, loop_vars[0], loop_vars[1]

    def visit_Subscript(self, node):
        self.generic_visit(node)
        if (isinstance(node.value, ast.Name) and node.value.id in self.params[:1]  # the feature matrix only, not the labels
                and isinstance(node.slice, ast.Name) and node.slice.id in (self.tr, self.te)):
            return ast.Subscript(value=node, slice=ast.Tuple(elts=[ast.Slice(), ast.Name(id=self.keep, ctx=ast.Load())], ctx=ast.Load()),
                                 ctx=ast.Load())
        return node


def apply_rules(train_src, det, rule_ids):
    """Rewrite train.py with the given rules (those that fired). Returns (module source, steps changed, applied rules, notes)."""
    ids = [r for r in rule_ids if r in det["fired"] and r not in det["not_applied"]]
    notes = [f"{r}: detected but no applicable idiom, not applied" for r in rule_ids if r in det["not_applied"]]
    tree = ast.parse(train_src)
    defs = _defs(tree)
    steps, applied, tail = [], [], ""
    has_target = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TARGET" for t in n.targets) for n in tree.body)
    split_fn = det.get("split_fn")
    # split family
    chosen = next((r for r in SPLIT_PRECEDENCE if r in ids), None)
    if chosen:
        fn = defs[split_fn]
        a = [x.arg for x in fn.args.args]
        body = _split_body(chosen, det, has_target, a[0], a[1])
        new = ast.parse(f"def {split_fn}({ast.unparse(fn.args)}):\n{textwrap.indent(body, '    ')}\n").body[0]
        tree.body = [new if (isinstance(n, ast.FunctionDef) and n.name == split_fn) else n for n in tree.body]
        steps.append(split_fn)
        applied += [r for r in SPLIT_PRECEDENCE if r in ids]
        if len([r for r in SPLIT_PRECEDENCE if r in ids]) > 1:
            notes.append(f"split rules {[r for r in SPLIT_PRECEDENCE if r in ids]} fired; one splitter exists, precedence R4 > R3 > R1 => {chosen} is in force")
    if "R5" in ids:
        defs = _defs(tree)
        ce = defs["claimed_eval"]
        first = ce.args.args[0].arg
        stmt = ast.parse(f"{first} = {first}.drop_duplicates().reset_index(drop=True)").body[0]
        k = 1 if (ce.body and isinstance(ce.body[0], ast.Expr) and isinstance(ce.body[0].value, ast.Constant)) else 0
        ce.body.insert(k, stmt)
        steps.append("claimed_eval")
        applied.append("R5")
    controlled = "\n\n\ndef controlled_eval(df, seed):\n    return claimed_eval(df, seed)\n"
    if "R2" in ids:
        info = det["fired"]["R2"]
        if info["mode"] == "scope":
            tail = _SCOPE_HELPER
            for c in info["transformers"]:
                tail += f"\n{c} = _rf_scoped({c})"
            for f in info["functions"]:
                tail += f"\n{f} = _rf_wrap({f}, {split_fn!r})"
                steps.append(f)
            controlled = "\n\n\ndef controlled_eval(df, seed):\n    _RF['seed'] = seed\n    return claimed_eval(df, seed)\n"
            applied.append("R2")
        else:  # hoist
            site = _hoist_site(tree, _leaky_fit_functions(tree))
            ce, G = _defs(tree)["claimed_eval"], _defs(tree)[site["G"]]
            # claimed_eval: drop `keep = F(...)`, pass the whole matrix to G
            ce.body = [s for s in ce.body if s is not site["assign"]]
            for c in ast.walk(ce):
                if isinstance(c, ast.Call) and isinstance(c.func, ast.Name) and c.func.id == site["G"]:
                    c.args[site["arg_index"]] = c.args[site["arg_index"]].value
            # G: re-run F inside every fold on the fold's training rows
            loop = [f for f in ast.walk(G) if isinstance(f, ast.For) and isinstance(f.target, ast.Tuple)
                    and isinstance(f.iter, ast.Call) and _fname(f.iter) == "split"][0]
            trn, ten = (e.id for e in loop.target.elts)
            kname = "_rf_keep"
            call = ", ".join(f"{p}[{trn}]" for p in site["G_params"])
            ins = ast.parse(f"{kname} = {site['F']}({call})").body[0]
            tx = _Hoist(site["G_params"], kname, (trn, ten))
            loop.body = [ins] + [tx.visit(s) for s in loop.body]
            steps += [site["G"], "claimed_eval"]
            applied.append("R2")
    src = _HEADER + ast.unparse(ast.fix_missing_locations(tree)) + "\n" + tail + controlled
    return src, sorted(set(steps)), applied, notes


def build_configs(case_dir):
    """-> {"det": detection, "configs": {fix_A|fix_B|fix_both: {"src", "rules_applied", "steps", "notes"}}}."""
    case_dir = Path(case_dir)
    det = detect(case_dir)
    train_src = (case_dir / "train.py").read_text(encoding="utf-8")
    out = {}
    for cfg, rids in (("fix_A", FACTOR_A), ("fix_B", FACTOR_B), ("fix_both", FACTOR_A + FACTOR_B)):
        src, steps, applied, notes = apply_rules(train_src, det, list(rids))
        out[cfg] = {"src": src, "rules_applied": applied, "steps": steps, "notes": notes}
    return {"det": det, "configs": out}
