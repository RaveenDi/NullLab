"""Author answers, grounded draft suggestions and non-repetitive guidance.

These are offline application checks, not model-quality or scientific scores.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from agent import workdesk as wd


CSV = "sensor,device_id,event\n" + "\n".join(f"{i / 100},{i // 5},{i % 2}" for i in range(60)) + "\n"


@pytest.fixture
def saved(tmp_path):
    store = wd.WorkdeskStore(tmp_path)
    project = store.create("Does row validation support new machines?")
    project = store.attach(project["id"], "rigs.csv", CSV)
    return store, project


def author_message(project, text):
    message = {"id": wd.uid(), "role": "user", "text": text, "created_at": wd.now()}
    project["messages"].append(message)
    return message


def proposal(field, value, message, quote=None):
    return {"field": field, "value": value, "source_id": message["id"], "quote": quote or message["text"]}


def reviewed(project):
    project["brief"] = {
        "id": wd.uid(), "created_at": wd.now(), "material_ids": [m["id"] for m in project["materials"]],
        "target": "event", "intended_use": "Screen new machines", "source_mode": "custom",
        "study": {"population": "unseen_entities", "decision_time": "Before inspection", "unit_of_analysis": "One reading",
                  "predictor_availability": "confirmed", "entity_column": "device_id", "time_column": ""},
    }
    return project


def add_proposals(project, suggestions):
    project["messages"].append({"id": wd.uid(), "role": "assistant", "created_at": wd.now(), "brief_proposals": suggestions})
    return project


def test_author_reviewed_answers_are_authoritative_and_read_is_pure(saved):
    _, project = saved
    reviewed(project)
    before = deepcopy(project)
    state = wd.guidance_state(project)
    assert state["confirmed"]["target"]["value"] == "event"
    assert state["confirmed"]["predictor_availability"]["source"] == "author_reviewed_brief"
    assert state["missing"] == [] and state["proposals"] == []
    assert project == before


def test_suggestions_require_review_never_change_saved_brief(saved):
    store, project = saved
    message = author_message(project, "I want to evaluate unseen rigs.")
    suggestions = wd.validate_brief_proposals(store, project, [proposal("population", "unseen_entities", message)])
    assert suggestions[0]["requires_author_review"] is True
    add_proposals(project, suggestions)
    state = wd.guidance_state(project)
    assert project["brief"] is None and state["confirmed"] == {}
    assert state["proposals"][0]["value"] == "unseen_entities"
    assert "entity_column" in state["missing"] and "population" not in state["missing"]


def test_model_and_fabricated_sources_are_rejected(saved):
    store, project = saved
    author = author_message(project, "The target column is event.")
    assistant = {"id": wd.uid(), "role": "assistant", "text": "All predictors are available before prediction."}
    project["messages"].append(assistant)
    items = [proposal("target", "event", author, "Fabricated target is event."),
             proposal("predictor_availability", "confirmed", assistant),
             {"field": "target", "value": "event", "source_id": wd.uid(), "quote": author["text"]}]
    assert wd.validate_brief_proposals(store, project, items) == []


@pytest.mark.parametrize("field,value,text", [
    ("target", "not_a_column", "The target is not_a_column."),
    ("target", "sensor", "The target is sensor."),
    ("target", "event", "The target is not event."),
    ("entity_column", "missing", "The entity column is missing."),
    ("population", "unseen_entities", "Do we predict unseen rigs?"),
    ("population", "unseen_entities", "I am unsure whether we predict unseen rigs."),
    ("population", "unseen_entities", "We will not predict unseen rigs."),
    ("population", "future_records", "The model predicts independent records."),
    ("predictor_availability", "confirmed", "Are all predictors available before prediction?"),
    ("predictor_availability", "confirmed", "All predictors are not available before prediction."),
    ("predictor_availability", "confirmed", "Predictors are numeric."),
    ("predictor_availability", "confirmed", "All predictors are available."),
    ("trust_code", "true", "I trust the code."),
    ("excluded_columns", "sensor", "Exclude sensor."),
    ("decision_time", "After the outcome", "Before the outcome"),
])
def test_unsupported_or_uncertain_suggestions_are_discarded(saved, field, value, text):
    store, project = saved
    message = author_message(project, text)
    assert wd.validate_brief_proposals(store, project, [proposal(field, value, message)]) == []


def test_explicit_positive_availability_is_only_an_unconfirmed_draft(saved):
    store, project = saved
    message = author_message(project, "All selected predictors are available before the inspection decision.")
    suggestions = wd.validate_brief_proposals(store, project, [proposal("predictor_availability", "confirmed", message)])
    assert len(suggestions) == 1 and suggestions[0]["requires_author_review"]
    add_proposals(project, suggestions)
    assert wd.guidance_state(project)["confirmed"] == {}


def test_author_notes_ground_free_text_and_known_column_suggestions(saved):
    store, project = saved
    project = store.attach(project["id"], "context.md", "The target is event. The entity column is device_id.\nPredict before inspection.")
    notes = project["materials"][-1]
    suggestions = wd.validate_brief_proposals(store, project, [
        {"field": "target", "value": "event", "source_id": notes["id"], "quote": "The target is event."},
        {"field": "entity_column", "value": "device_id", "source_id": notes["id"], "quote": "The entity column is device_id."},
        {"field": "decision_time", "value": "before inspection", "source_id": notes["id"], "quote": "Predict before inspection."},
    ])
    assert {item["field"] for item in suggestions} == {"target", "entity_column", "decision_time"}
    assert all(item["source_id"] == notes["id"] for item in suggestions)


def test_column_token_cannot_match_a_substring(saved):
    store, project = saved
    message = author_message(project, "The target is event_rate.")
    assert wd.validate_brief_proposals(store, project, [proposal("target", "event", message)]) == []


def test_changed_materials_invalidate_saved_answers_and_proposals(saved):
    store, project = saved
    reviewed(project)
    message = author_message(project, "The decision time is before inspection.")
    suggestions = wd.validate_brief_proposals(store, project, [proposal("decision_time", "before inspection", message)])
    add_proposals(project, suggestions)
    project["materials"].append({"id": wd.uid(), "kind": "notes"})
    project["brief_dirty"] = True
    state = wd.guidance_state(project)
    assert state["confirmed"] == {} and state["proposals"] == [] and state["needs_material_review"]


def test_saving_newer_brief_retires_earlier_suggestions(saved):
    store, project = saved
    message = author_message(project, "I want to evaluate unseen rigs.")
    add_proposals(project, wd.validate_brief_proposals(store, project, [proposal("population", "unseen_entities", message)]))
    reviewed(project)
    assert wd.guidance_state(project)["proposals"] == []


def test_explicit_change_proposal_preserves_confirmation_question(saved):
    store, project = saved
    reviewed(project)
    message = author_message(project, "Please change the population to future records.")
    add_proposals(project, wd.validate_brief_proposals(store, project, [proposal("population", "future_records", message)]))
    question = "Which population should this evaluation cover?"
    assert wd.guidance_state(project)["confirmed"]["population"]["value"] == "unseen_entities"
    assert "time_column" in wd.guidance_state(project)["missing"]
    assert wd.filter_guidance_questions(project, [question]) == [question]


def test_repeated_intake_removed_but_scientific_objections_and_new_facts_stay(saved):
    _, project = saved
    reviewed(project)
    duplicates = ["Which target column should be predicted?", "At what decision time are measurements available?",
                  "Which population should this evaluate?", "Which column identifies the same machine?",
                  "Are all predictors available at the decision time?"]
    scientific = ["Which group split holds out entire rigs?", "Could feature availability introduce leakage despite the current claim?",
                  "What evidence supports generalization to new machines?", "How many rigs were sampled?",
                  "Which target is most sensitive to selection bias?"]
    assert wd.filter_guidance_questions(project, duplicates + scientific) == scientific


def test_unknown_availability_question_is_kept_when_only_timing_is_reviewed(saved):
    _, project = saved
    reviewed(project)["brief"]["study"]["predictor_availability"] = "unknown"
    question = "Are all predictors available at the decision time?"
    assert wd.filter_guidance_questions(project, [question]) == [question]


@pytest.mark.parametrize("question", ["When is the prediction made?", "When are predictions made?",
                                     "When are inputs measured?", "When is each measurement taken?"])
def test_reviewed_prediction_time_handles_common_word_variants(saved, question):
    _, project = saved
    reviewed(project)
    assert wd.filter_guidance_questions(project, [question]) == []
    assert question not in wd.filter_guidance_text(project, question)


def test_prediction_time_filter_preserves_new_methodological_questions(saved):
    _, project = saved
    reviewed(project)
    question = "When are prediction intervals reliable under entity dependence?"
    assert wd.filter_guidance_questions(project, [question]) == [question]


def test_duplicate_questions_removed_from_prose_without_losing_explanation(saved):
    _, project = saved
    reviewed(project)
    text = ("Row validation does not establish unseen-rig performance.\n"
            "- Which target column should be predicted?\n"
            "- Are all predictors available at the decision time?\n"
            "A group control still needs mechanical validation. What evidence supports generalization to new machines?")
    filtered = wd.filter_guidance_text(project, text)
    assert "Which target" not in filtered and "Are all predictors" not in filtered
    assert "Row validation" in filtered and "mechanical validation" in filtered and "What evidence" in filtered


def test_all_duplicate_text_has_an_actionable_fallback(saved):
    _, project = saved
    reviewed(project)
    filtered = wd.filter_guidance_text(project, "Which target column should be predicted?")
    assert "study brief" in filtered and "experiment result" in filtered


def test_local_explicit_answers_propose_drafts_without_confirming_code_or_timing(saved):
    _, project = saved
    message = author_message(project, "Target: event\nPopulation: unseen_entities\nEntity column: device_id\nDecision time: Before inspection\nTrust code: true\nPredictor availability: confirmed")
    suggestions = wd.proposals_for_message(project, message)
    assert {item["field"] for item in suggestions} == {"target", "population", "entity_column", "decision_time"}
    assert all(item["source_id"] == message["id"] and item["requires_author_review"] for item in suggestions)
    assert project["brief"] is None


def test_local_explicit_availability_sentence_proposes_review_only(saved):
    _, project = saved
    message = author_message(project, "All selected predictors are available at prediction time.")
    suggestions = wd.proposals_for_message(project, message)
    assert len(suggestions) == 1
    assert suggestions[0]["field"] == "predictor_availability" and suggestions[0]["value"] == "confirmed"
    assert suggestions[0]["requires_author_review"] and project["brief"] is None


@pytest.mark.parametrize("text", ["Are all selected predictors available at prediction time?",
                                 "Not all selected predictors are available at prediction time.",
                                 "Predictor availability: confirmed", "All predictors are numeric."])
def test_local_availability_never_assumes_unstated_or_negative_timing(saved, text):
    _, project = saved
    assert wd.proposals_for_message(project, author_message(project, text)) == []


def test_optional_suggestion_schema_errors_do_not_crash_guidance(saved):
    store, project = saved
    assert wd.validate_brief_proposals(store, project, {"field": "target"}) == []
    assert wd.validate_brief_proposals(store, project, [None, {"field": [], "value": "event"}, {"field": "target", "unexpected": True}]) == []


def test_brief_review_retires_context_even_if_a_late_model_reply_arrives(saved):
    store, project = saved
    message = author_message(project, "I want to evaluate future records.")
    suggestions = wd.validate_brief_proposals(store, project, [proposal("population", "future_records", message)])
    reviewed(project)
    project["brief"]["context_message_ids"] = [message["id"]]
    add_proposals(project, suggestions)
    assert wd.guidance_state(project)["proposals"] == []
    assert wd.guidance_state(project)["confirmed"]["population"]["value"] == "unseen_entities"


def test_guidance_instructions_protect_declarations_and_mechanical_failures():
    assert "do not ask them again" in wd.GUIDANCE_INSTRUCTIONS
    assert "mechanical applicability failure is authoritative" in wd.GUIDANCE_INSTRUCTIONS
    assert "author to review and save a brief" in wd.GUIDANCE_INSTRUCTIONS
