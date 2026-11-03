"""Author-declared study contracts and deterministic review, never scientific clearance."""

from __future__ import annotations

POPULATIONS = ("undecided", "independent_records", "represented_entities", "unseen_entities", "future_records")
SCHEMA = "nulllab.study.v1"
FIELDS = {"schema", "author_declared", "title", "decision_time", "unit_of_analysis", "population", "entity_column", "time_column", "excluded_columns", "predictor_availability"}


def normalize(value, columns, target):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("Study must contain only the supported brief and column-role fields")
    if value.get("schema", SCHEMA) != SCHEMA:
        raise ValueError("Unsupported study contract schema")

    def text(name, limit, default=""):
        answer = value.get(name, default)
        if not isinstance(answer, str) or len(answer) > limit:
            raise ValueError(f"Study {name} must be text up to {limit} characters")
        return answer.strip()

    result = {
        "schema": SCHEMA, "author_declared": True,
        "title": text("title", 160, "Your CSV study") or "Your CSV study",
        "decision_time": text("decision_time", 2000),
        "unit_of_analysis": text("unit_of_analysis", 300, "One CSV row"),
        "population": text("population", 40, "undecided"),
        "entity_column": text("entity_column", 1024), "time_column": text("time_column", 1024),
        "predictor_availability": text("predictor_availability", 20, "unknown"),
    }
    if result["population"] not in POPULATIONS:
        raise ValueError("Choose a supported study population")
    if result["predictor_availability"] not in ("confirmed", "unknown"):
        raise ValueError("Predictor availability must be confirmed or unknown")
    exclusions = value.get("excluded_columns", [])
    if not isinstance(exclusions, list) or not all(isinstance(c, str) and c in columns for c in exclusions):
        raise ValueError("Excluded columns must be a list of existing column names")
    for name in ("entity_column", "time_column"):
        role = result[name]
        if role and (role not in columns or role == target):
            raise ValueError(f"Study {name} must name an existing non-target column")
    if result["entity_column"] and result["entity_column"] == result["time_column"]:
        raise ValueError("Entity and time metadata must use different columns")
    excluded = set(exclusions) | {result["entity_column"], result["time_column"]}
    result["excluded_columns"] = [c for c in columns if c in excluded and c != target]
    return result


def predictors(columns, target, study):
    return [c for c in columns if c != target and c not in study["excluded_columns"]]


def review(study, *, generated=False, predictor_columns=(), facts=None):
    questions, gaps, warnings = [], [], []
    if study is None:
        return {"schema": "nulllab.study-review.v1", "status": "not_declared", "questions": [], "scope_gaps": [], "warnings": ["No structured author study contract was supplied; intended use still requires review."], "inference_scope": "conditional_rows"}
    population = study["population"]
    if not study["decision_time"]:
        questions.append("At what decision or prediction time must the input measurements be available?")
    if population == "undecided":
        questions.append("Will predictions be used for independent records, represented entities, unseen entities, or future records?")
    if study["predictor_availability"] != "confirmed":
        questions.append("Are all selected predictors available at that decision time? Exclude unavailable inputs before confirming.")
    if population in ("represented_entities", "unseen_entities") and not study["entity_column"]:
        questions.append("Which column identifies records from the same entity?")
    if population == "future_records" and not study["time_column"]:
        questions.append("Which column records the time used to separate earlier and later observations?")
    if generated and population in ("unseen_entities", "future_records"):
        gaps.append("The generated adapter uses stratified random-row cross-validation. It cannot answer unseen-entity or future-period performance; a separately validated group/time pipeline is required.")
    if population == "represented_entities":
        warnings.append("This is a descriptive random-row baseline for represented entities. Dependence between their records is not resolved by row-bootstrap intervals.")
    if study["time_column"] and population != "future_records":
        warnings.append("A time column is recorded as metadata; this does not establish a forecasting evaluation.")
    if (facts or {}).get("target_matching_columns"):
        warnings.append("Some selected columns exactly match the target or its inverse in these records. Check their decision-time availability; this observation alone is not a leakage finding.")
    if (facts or {}).get("duplicate_predictor_rows"):
        warnings.append("Repeated predictor rows exist. Check whether they are legitimate repeated records or duplicates requiring a different evaluation design.")
    if (facts or {}).get("missing_predictor_cells"):
        warnings.append("The generated baseline replaces missing selected predictors with a fixed zero. Confirm that this is appropriate for the measurements.")
    warnings.append("Study statements and predictor availability are author declarations, not independently verified facts.")
    return {
        "schema": "nulllab.study-review.v1", "status": "needs_information" if questions else "unsupported" if gaps else "ready",
        "questions": questions, "scope_gaps": gaps, "warnings": warnings,
        "population": population, "predictor_columns": list(predictor_columns),
        "excluded_columns": study["excluded_columns"], "facts": facts or {},
        "inference_scope": "descriptive_only" if population in ("represented_entities", "unseen_entities", "future_records") else "conditional_rows",
    }


def data_facts(frame, target, selected):
    """Only aggregate facts; correlation or exact agreement is not a leakage finding."""
    import numpy as np

    X = frame[selected]
    matches = [c for c in selected if not X[c].isna().any() and (np.array_equal(X[c].to_numpy(), frame[target].to_numpy()) or np.array_equal(X[c].to_numpy(), 1 - frame[target].to_numpy()))]
    return {
        "rows": len(frame), "predictor_count": len(selected),
        "class_counts": {str(k): int(v) for k, v in frame[target].value_counts().items()},
        "positive_prevalence": float(frame[target].mean()),
        "missing_predictor_cells": int(X.isna().sum().sum()),
        "duplicate_predictor_rows": int(X.duplicated().sum()),
        "target_matching_columns": matches,
    }


def room(result):
    """A view of actual recorded evidence, without fabricated agent conversation."""
    check = result.get("study_review") or {}
    participants = [{"role": "study_checks", "kind": "deterministic", "status": check.get("status", "not_declared"), "summary": "Author contract and column-role checks", "items": check.get("questions", []) + check.get("scope_gaps", []) + check.get("warnings", [])}]
    for role, field in (("planner", "plan"), ("independent_methodology", "independent_review"), ("final_critic", "critic")):
        record = result.get(field)
        if record:
            if not isinstance(record, dict):
                participants.append({"role": role, "kind": "assessment_record", "status": "invalid", "summary": "The response was not a structured assessment; inspect the recorded error.", "items": []})
                continue
            concerns = record.get("concerns", [])
            participants.append({"role": role, "kind": "model_record" if result.get("mode") in ("live", "replay") else "recorded_proposal", "status": record.get("decision", record.get("assessment", record.get("verdict", "recorded"))), "summary": record.get("reason", "Recorded assessment"), "items": concerns if isinstance(concerns, list) else [str(concerns)]})
    participants.append({"role": "measurement", "kind": "deterministic", "status": "measured" if result.get("summary") else "baseline_only" if result.get("baseline") else "not_executed", "summary": "A controlled experiment was measured" if result.get("summary") else "No counterfactual was measured; no scientific clearance", "items": []})
    return {"schema": "nulllab.review-room.v1", "participants": participants, "open_questions": result.get("questions", []), "scope_gaps": result.get("scope_gaps", []), "note": "These are recorded checks and model assessments, not simulated conversation or proof of consensus."}
