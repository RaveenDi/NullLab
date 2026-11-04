"""Read-only operation preflight for a reviewed Workdesk study.

This invokes the frozen AST compiler, never imports researcher Python, and never
claims that a compilable operation has passed runtime/fidelity guards.
"""
from __future__ import annotations

import ast
import hashlib
import io

from agent import edit_dsl

SEEDS = [42, 43, 44]


def _column_expression(node, column):
    """Recognize only a direct column vector from claimed_eval's df parameter."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "to_numpy" and not node.args and not node.keywords:
        node = node.func.value
    elif isinstance(node, ast.Attribute) and node.attr == "values":
        node = node.value
    return (isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name)
            and node.value.id == "df" and isinstance(node.slice, ast.Constant)
            and node.slice.value == column)


def _group_binding(tree, step, column):
    """The CV template uses `groups`; verify the canonical direct caller too."""
    defs = edit_dsl.defs_of(tree)
    fn = defs[step]
    splitters = [n for n in ast.walk(fn) if isinstance(n, ast.Call) and edit_dsl.fname(n) in edit_dsl.SPLITTER_CLASSES]
    if not splitters:
        # Hold-out templates read df[col] themselves.
        return True
    if step == "claimed_eval":
        return False  # the engine calls claimed_eval(df, seed), without groups
    params = edit_dsl.params_of(fn)
    if "groups" not in params:
        return False
    calls = [n for n in ast.walk(defs["claimed_eval"]) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == step]
    all_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == step]
    if not calls or len(calls) != len(all_calls):
        return False
    for call in calls:
        binding = next((k.value for k in call.keywords if k.arg == "groups"), None)
        index = params.index("groups")
        if binding is None and len(call.args) > index:
            binding = call.args[index]
        if not _column_expression(binding, column):
            return False
        # Rebinding a groups parameter inside the helper defeats its provenance.
        if any(isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store) and n.id == "groups" for n in ast.walk(fn)):
            return False
    return True


def _required_groups(tree, candidates):
    """Conservative count for literal CV folds; dynamic folds remain runtime checks."""
    required = 2
    for operation in candidates:
        fn = edit_dsl.defs_of(tree)[operation["step"]]
        for call in ast.walk(fn):
            if not isinstance(call, ast.Call) or edit_dsl.fname(call) not in edit_dsl.SPLITTER_CLASSES:
                continue
            count = next((item.value for item in call.keywords if item.arg == "n_splits"), call.args[0] if call.args else ast.Constant(value=5))
            if isinstance(count, ast.Constant) and isinstance(count.value, int) and not isinstance(count.value, bool):
                required = max(required, count.value)
    return required


def _column_data(csv_text, column, required):
    """Match the frozen guard's finite numeric column representation, without execution."""
    if csv_text is None:
        return {"status": "not_checked", "required_distinct": required, "issues": ["Dataset metadata was not supplied to this AST-only check."]}
    import numpy as np
    import pandas as pd

    frame = pd.read_csv(io.StringIO(csv_text))
    if column not in frame:
        return {"status": "blocked", "required_distinct": required, "issues": [f"Declared metadata column {column!r} is absent from this CSV."]}
    original = frame[column]
    numeric = pd.to_numeric(original, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    missing = int(original.isna().sum())
    nonnumeric = int((numeric.isna() & original.notna()).sum())
    nonfinite = int((~np.isfinite(values) & ~np.isnan(values)).sum())
    unique = int(original.nunique(dropna=True))
    finite = values[np.isfinite(values)]
    float_unique = int(len(np.unique(finite)))
    unsafe_precision = bool(((numeric > 2 ** 53) | (numeric < -(2 ** 53))).any())
    issues = []
    if missing:
        issues.append(f"Metadata column {column!r} contains {missing} missing values; the guard requires complete group/time identities.")
    if nonnumeric:
        issues.append(f"Metadata column {column!r} contains {nonnumeric} nonnumeric values. The frozen runtime guard currently requires numeric group/time metadata.")
    if nonfinite:
        issues.append(f"Metadata column {column!r} contains {nonfinite} nonfinite values; use finite identities.")
    if unsafe_precision:
        issues.append(f"Metadata column {column!r} exceeds the safe numeric identity range (absolute value 2^53); float conversion may lose identity precision.")
    if not missing and not nonnumeric and not nonfinite and float_unique != unique:
        issues.append(f"Numeric conversion of {column!r} merges distinct metadata identities; this is not a safe representation.")
    if not missing and not nonnumeric and not nonfinite and float_unique < required:
        issues.append(f"Metadata column {column!r} has {float_unique} distinct identities; this candidate requires at least {required}.")
    return {"status": "blocked" if issues else "compatible", "rows": len(frame), "unique_values": unique,
            "numeric_unique_values": float_unique, "missing_values": missing, "nonnumeric_values": nonnumeric,
            "nonfinite_values": nonfinite, "unsafe_precision": unsafe_precision, "required_distinct": required,
            "issues": issues}


def check(source, brief, csv_text=None):
    """Return input-bound preflight plus a concrete, unmeasured protocol."""
    tree = ast.parse(source)
    declaration = brief["study"]
    population = declaration["population"]
    kind = {"unseen_entities": "group", "future_records": "temporal"}.get(population)
    column = declaration.get("entity_column" if kind == "group" else "time_column", "") if kind else ""
    functions = edit_dsl.defs_of(tree)
    reachable = {"claimed_eval"}
    pending = ["claimed_eval"]
    while pending:
        current = functions.get(pending.pop())
        if current is None:
            continue
        for node in ast.walk(current):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in functions and node.func.id not in reachable:
                reachable.add(node.func.id)
                pending.append(node.func.id)
    candidates, rejected = [], []
    if kind and column:
        for name in sorted(reachable):
            op = {"op": "replace_split", "step": name, "kind": kind, "col": column}
            try:
                edit_dsl.compile_ops(source, [op])
            except edit_dsl.OpError as exc:
                if "no recognisable split" not in exc.msg:
                    rejected.append({"step": name, "reason": str(exc)})
                continue
            if kind == "group" and not _group_binding(tree, name, column):
                rejected.append({"step": name, "reason": f"The AST template can compile, but a direct groups vector from df[{column!r}] to this helper could not be verified. Adding groups=None is insufficient."})
                continue
            if kind == "temporal" and any(isinstance(n, ast.Call) and edit_dsl.fname(n) in edit_dsl.SPLITTER_CLASSES for n in ast.walk(functions[name])):
                rejected.append({"step": name, "reason": "A chronological CV replacement does not sort the declared time column. Use a reviewed df/seed hold-out helper; its template separates earlier and later times explicitly."})
                continue
            candidates.append(op)
    data = _column_data(csv_text, column, _required_groups(tree, candidates)) if kind and column else {"status": "not_required", "issues": []}
    ast_candidates = list(candidates)
    if data["status"] == "blocked":
        candidates = []
    status = "not_required" if not kind else "applicable" if candidates else "blocked"
    messages = []
    if status == "blocked":
        if data["status"] == "blocked":
            messages.append(f"The declared {kind} metadata cannot be safely represented by the current runtime guard. No baseline or model call has started.")
            messages.extend(data["issues"])
            if kind == "group":
                messages.append("For categorical entity IDs, explicitly review a one-to-one numeric metadata encoding as a NEW input revision. Preserve the original IDs, exact mapping and original files; do not alter predictors, labels or model. Verify baseline equivalence before another audit.")
            else:
                messages.append("Review a numeric time representation that preserves chronological order and timezone semantics as a NEW input revision. An arbitrary categorical ID mapping is not a valid time ordering. Preserve original timestamps and the conversion; verify baseline equivalence before another audit.")
        elif kind == "group":
            messages.append(f"This study needs a {kind}-separated comparison on {column!r}, but no safely bound split operation was found. No baseline or model call has started.")
            messages.append("Keep the model, feature construction and random-row baseline unchanged. Move the CV body into a helper such as cv_eval(X, y, seed, groups), and pass df[entity_column].to_numpy() explicitly from claimed_eval(df, seed). Check baseline equivalence on all three seeds, attach the reviewed adapter as a new material version, then prepare a new brief/plan.")
        else:
            messages.append(f"This study needs a {kind}-separated comparison on {column!r}, but no safely bound split operation was found. No baseline or model call has started.")
            messages.append("Use a reviewed hold-out helper taking df and seed and returning train/test row indices. Preserve the starting protocol and model; the typed temporal control must read the declared time column. Attach a new adapter version and review again.")
    note = "AST applicability and explicit group binding only. No Python was imported or executed. Runtime provenance, fidelity, data sufficiency and scientific interpretation remain unverified."
    from agent.workdesk import inspect_python

    shape = inspect_python(source)
    protocol = {
        "target": brief["target"], "population": population,
        "decision_time": declaration["decision_time"],
        "entity_column": declaration.get("entity_column"), "time_column": declaration.get("time_column"),
        "excluded_columns": declaration.get("excluded_columns", []),
        "metric": shape["metric"], "seeds": SEEDS,
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "control_candidates": candidates,
        "selection": "Candidate operations are mechanically inspected, not an executed or final model proposal. Local rules may abstain; acknowledged Meta planning may choose a supported operation or abstain.",
        "inference": "Group/time comparisons are descriptive; row-bootstrap intervals do not establish unseen-entity or future-period uncertainty." if kind else "Intervals condition on fixed predictions; they omit training uncertainty.",
    }
    return {"status": status, "required_kind": kind, "column": column or None, "candidates": candidates, "ast_candidates": ast_candidates,
            "column_diagnostics": data,
            "rejected": rejected, "messages": messages, "note": note, "protocol": protocol}


def steps(protocol, source_mode):
    operations = protocol["control_candidates"]
    candidate = "; ".join(f"{op['op']}({op['step']}, {op['kind']}, {op['col']})" for op in operations)
    return [
        f"Freeze the reviewed target {protocol['target']!r}, population {protocol['population']}, column roles and exact CSV/Python/notes bytes.",
        ("Execute the supplied Python baseline" if source_mode == "custom" else "Execute the generated 40-tree Random Forest, 3-fold stratified baseline") + f" on seeds 42, 43 and 44; metric: {protocol['metric']}. No model or metric change is allowed in the control.",
        (f"Review the mechanically applicable candidate: {candidate}. " if candidate else "No required group/time operation is established. ") + "Local rules or acknowledged Meta planning can propose a supported typed intervention or abstain; this plan does not promise a measured control.",
        "Run the frozen contract, runtime row-provenance and model-fidelity guards before accepting any control. Rejection remains an unmeasured assessment.",
        "Measure accepted controls on the same three seeds, retain every outcome and any reviewer disagreement. " + protocol["inference"],
        "Export verified inputs and measurements, or an explicitly unmeasured assessment. A different material or study declaration requires a new reviewed revision.",
    ]
