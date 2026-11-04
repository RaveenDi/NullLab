"""Workdesk failures must be visible before baseline execution/provider spend."""
import json

from agent import engine
from app import server, workdesk_api
from tests.test_workdesk_api import STUDY, attach, client as api_client, create, plan, save

client = api_client

GROUP_CSV = "device_id,sensor,event\n" + "\n".join(f"{i // 6},{i / 100},{i % 2}" for i in range(60)) + "\n"
GROUP_SOURCE = '''import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold
TARGET = "event"
METRIC = "accuracy"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return ["sensor"]
def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy()
    y = df[TARGET].to_numpy()
    for tr, te in StratifiedKFold(n_splits=3,shuffle=True,random_state=seed).split(X,y):
        pass
    return y,y
'''


def test_impossible_required_control_is_blocked_before_case_job_or_provider(client, monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "run_audit", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("baseline must not run")))
    monkeypatch.setattr(workdesk_api, "Provider", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no provider")))
    pid = create(client)["id"]
    attach(client, pid, content=GROUP_CSV)
    attach(client, pid, "train.py", GROUP_SOURCE)
    save(client, pid, source_mode="custom", trust_code=True, study={**STUDY, "population": "unseen_entities", "entity_column": "device_id"})
    prepared = plan(client, pid)
    assert prepared["plan"]["status"] == "unsupported"
    assert prepared["plan"]["case"] is None
    check = prepared["plan"]["compatibility"]
    assert check["status"] == "blocked"
    assert "groups" in json.dumps(check["rejected"])
    assert "No baseline" in check["messages"][0]
    assert prepared["plan"]["protocol"]["seeds"] == [42, 43, 44]
    assert client.post(f"/api/investigations/{pid}/runs", json={"plan_id": prepared["plan"]["id"]}).status_code == 400
    assert not list((tmp_path / "out/jobs").glob("*/job.json"))
    assert not (tmp_path / "examples").exists()


def test_concrete_generated_protocol_records_target_metric_and_fixed_seeds(client):
    pid = create(client)["id"]
    attach(client, pid)
    save(client, pid)
    prepared = plan(client, pid)["plan"]
    assert prepared["status"] == "ready"
    protocol = prepared["protocol"]
    assert protocol["target"] == "event" and protocol["metric"] == "pr_auc"
    assert protocol["population"] == "independent_records"
    assert "42, 43 and 44" in prepared["steps"][1]
    assert "40-tree" in prepared["steps"][1]
    assert "may" in prepared["steps"][2] or "can propose" in prepared["steps"][2]


def test_optional_guidance_uses_confirmed_brief_and_filters_repeated_questions(client, monkeypatch):
    pid = create(client)["id"]
    attach(client, pid)
    project = save(client, pid)
    monkeypatch.setenv("NULLLAB_ALLOW_WEB_LIVE", "1")
    contexts = []

    class FakeProvider:
        def __init__(self, *args, **kwargs):
            pass

        def complete(self, system, text, **kwargs):
            contexts.append(json.loads(text))
            assert "mechanical applicability failure" in system
            return json.dumps({"text": "The declared protocol can be investigated. Which outcome column do you want to predict? When is the prediction made?", "questions": ["Which target column?", "When is the prediction made?", "Are all predictors available at prediction time?", "How are missing values handled?"], "references": []})

        def model_for(self, role):
            return "mock-model"

        def ledger(self):
            return {"calls": 1, "est_usd": 0}

    monkeypatch.setattr(workdesk_api, "Provider", FakeProvider)
    reply = client.post(f"/api/investigations/{pid}/messages", json={"text": "Review my saved declarations", "live": True, "outbound_confirmed": True, "context_sha256": project["outbound_preview"]["context_sha256"]})
    assert reply.status_code == 200, reply.text
    answer = reply.json()["messages"][-1]
    assert answer["kind"] == "meta_guidance", answer
    assert answer["questions"] == ["How are missing values handled?"]
    assert "Which outcome column" not in answer["text"]
    assert "prediction made?" not in answer["text"]
    assert contexts[0]["clarifications"]["confirmed"]["target"]["value"] == "event"
    assert reply.json()["brief"]["id"] == project["brief"]["id"]


def test_local_structured_answers_become_reviewable_drafts_not_saved_declarations(client):
    pid = create(client)["id"]
    attach(client, pid)
    project = client.post(f"/api/investigations/{pid}/messages", json={"text": "Target: event\nPopulation: independent_records\nDecision time: Before the outcome\nIntended use: Screen components before failure"}).json()
    assert project["brief"] is None
    assert {p["field"] for p in project["brief_suggestions"]} >= {"target", "population", "decision_time", "intended_use"}
    assert all(p["requires_author_review"] for p in project["brief_suggestions"])
    assert project["runs"] == []


def test_projection_restores_requested_mode_from_job_before_engine_checkpoint(client, monkeypatch):
    pid = create(client)["id"]
    store = workdesk_api.wd.WorkdeskStore(server.WORKSPACE)
    job_id = workdesk_api.wd.uid()
    store.change(pid, lambda p: p["runs"].append({"job_id": job_id, "plan_id": "old", "revision_id": "old"}))
    monkeypatch.setattr(server, "get_job", lambda _: {"id": job_id, "status": "running", "live": True, "critic": True, "result": {"mode": "rules", "events": []}})
    detail = client.get(f"/api/investigations/{pid}").json()
    assert detail["runs"][0]["requested_mode"] == "live"
    assert detail["runs"][0]["requested_critic"] is True
    assert detail["runs"][0]["verdict"] is None


def test_no_key_followup_explains_recorded_descriptive_inconclusive_limit(monkeypatch):
    monkeypatch.setattr(workdesk_api, "_run_context", lambda *args: {"status": "completed", "finalized": True, "evidence_verified": True, "verdict": "INCONCLUSIVE", "summary": {"claimed": .974, "controlled": .290, "metric": "accuracy"}, "limitations": ["Group/time control measured descriptively only: conditional intervals are not dependence-aware."]})
    project = {"materials": [{"kind": "csv"}], "plan": None, "runs": [{"job_id": "test"}]}
    response = workdesk_api._local_reply(project, "What can I conclude?", server)
    assert "0.9740 → 0.2900" in response and "INCONCLUSIVE" in response
    assert "do not account for repeated entities" in response
    assert "does not establish calibrated inflation" in response
