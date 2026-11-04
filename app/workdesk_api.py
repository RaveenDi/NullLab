"""Question-first local workdesk routes, backed by the existing audit service."""
from __future__ import annotations

from dataclasses import replace
import base64
import binascii
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from starlette.concurrency import run_in_threadpool

from agent import workdesk as wd
from agent import workdesk_protocol
from agent.provider import Provider, ProviderConfig
from agent.storage import write_json

TERMINAL = {"completed", "inconclusive", "failed", "cancelled"}


class StrictBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewInvestigation(StrictBody):
    question: str = Field(min_length=1, max_length=4000)
    title: str = Field(default="", max_length=160)


class Material(StrictBody):
    filename: str = Field(min_length=1, max_length=160)
    content: str | None = Field(default=None, min_length=1)
    content_b64: str | None = Field(default=None, min_length=1)


class Message(StrictBody):
    text: str = Field(min_length=1, max_length=4000)
    live: bool = False
    outbound_confirmed: bool = False
    context_sha256: str | None = Field(default=None, max_length=64)


class Brief(StrictBody):
    target: str = Field(min_length=1, max_length=1024)
    intended_use: str = Field(min_length=1, max_length=4000)
    study: dict[str, Any] = Field(default_factory=dict)
    source_mode: str = "generated"
    trust_code: bool = False


class Run(StrictBody):
    plan_id: str | None = Field(default=None, max_length=64)
    live: bool = False
    critic: bool = False
    outbound_confirmed: bool = False


class Example(StrictBody):
    case: str = Field(min_length=1, max_length=128)


def _error(exc):
    if isinstance(exc, KeyError):
        return HTTPException(404, str(exc).strip("'"))
    return HTTPException(400, str(exc)[:500])


async def _body(request, model, limit=7_000_000):
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > limit:
            raise HTTPException(413, "Workdesk request exceeds the supported upload size")
    try:
        return model.model_validate_json(data)
    except ValueError:
        raise HTTPException(400, "Request fields or JSON are invalid") from None


def _active(project, server):
    for run in project["runs"]:
        try:
            job = server.get_job(run["job_id"])
        except HTTPException:
            continue
        if job["status"] not in TERMINAL:
            return True
    return False


def _locked(server, action, *args):
    # Check-and-dispatch shares the job service's reentrant lock. Two browser
    # requests cannot both pass an idle check before either records its run.
    with server._LOCK:
        return action(*args)


def _run_context(project, server):
    """Only finalized, input-bound measurements may inform an explanation."""
    if not project["runs"]:
        return None
    job_id = project["runs"][-1]["job_id"]
    try:
        job = server.get_job(job_id)
    except HTTPException:
        return {"job_id": job_id, "status": "unavailable", "finalized": False, "evidence_verified": False}
    return _job_context(job, server)


def _job_context(job, server):
    job_id = job["id"]
    result = job.get("result") or {}
    final = job.get("status") in TERMINAL and result.get("status") == job.get("status")
    view = {"job_id": job_id, "status": job.get("status"), "finalized": final, "evidence_verified": False}
    if not final:
        events = result.get("events", [])
        view["phase"] = events[-1].get("phase") if events else None
        view["note"] = "No finalized result is available. Do not quote checkpoint numbers or infer a conclusion."
        return view
    if result.get("evidence"):
        try:
            from agent.evidence import verify

            verify(server._job_path(job_id) / "inputs", result)
            if result.get("summary") and (not isinstance(result.get("record"), dict) or result["record"].get("evidence") != result["evidence"] or result["record"].get("sources") != result.get("sources")):
                raise ValueError("Measured record identity differs")
            view["evidence_verified"] = True
            view.update({key: result.get(key) for key in ("verdict", "summary", "baseline", "limitations", "plan", "critic", "independent_review", "questions", "scope_gaps")})
            view["evidence_manifest_sha256"] = result["evidence"].get("manifest_sha256")
        except (ValueError, OSError, KeyError, TypeError):
            view["note"] = "Saved input/control identity could not be verified; no numerical conclusion is supplied."
    else:
        view["verdict"] = result.get("verdict") if not result.get("summary") else "INCONCLUSIVE"
        view["note"] = "This outcome has no verifiable input manifest. No measured evidence is supplied."
    return view


def _outbound_preview(project, server):
    frozen = {
        "question": project["question"],
        "materials": [{"id": m["id"], "sha256": m["sha256"], "filename": m["filename"]} for m in project["materials"]],
        "brief": project["brief"],
        "clarifications": wd.guidance_state(project),
        "messages": [{"id": m["id"], "role": m["role"], "text": m["text"]} for m in project["messages"][-6:]],
        "latest_run": _run_context(project, server),
    }
    return {"context_sha256": wd.identity(frozen), "files": [m["filename"] for m in project["materials"]], "data_policy": "Your new prompt, recent research thread, code/notes excerpts, declarations, column names and aggregate diagnostics; no raw CSV rows. Verified completed-run evidence is included when available.", "note": "Review again when materials, brief, thread or saved run evidence changes."}


def _detail(project, server):
    """Projection over saved jobs; reading never triggers inference or execution."""
    runs, active, latest = [], [], None
    for link in project["runs"]:
        try:
            job = server.get_job(link["job_id"])
            result = job.get("result") or {}
            context = _job_context(job, server)
            provisional = job.get("status") not in TERMINAL
            item = {**link, "status": job["status"], "verdict": context.get("verdict") if context["finalized"] else None, "measured": bool(context.get("summary")) and context["evidence_verified"], "events": result.get("events", []), "baseline": result.get("baseline") if provisional else context.get("baseline"), "summary": context.get("summary"), "evidence_verified": context["evidence_verified"], "checkpoint_only": not context["finalized"] and not provisional, "ledger": result.get("ledger", {"calls": 0, "est_usd": 0}), "error": job.get("error") or result.get("error") or (context.get("note") if not provisional and not context["evidence_verified"] else None)}
            item.update(requested_mode=link.get("requested_mode", "live" if job.get("live") else "rules"), requested_critic=link.get("requested_critic", bool(job.get("critic"))))
            runs.append(item)
            if job["status"] not in TERMINAL:
                active.append(job["id"])
            latest = item
        except HTTPException:
            runs.append({**link, "status": "unavailable", "error": "Saved audit is unavailable; no result is inferred."})
    suggested = "custom" if wd.latest_material(project, "python") else "generated"
    clarifications = wd.guidance_state(project)
    return {**project, "runs": runs, "clarification_state": clarifications, "brief_suggestions": clarifications["proposals"], "suggested_source_mode": suggested, "outbound_preview": _outbound_preview(project, server), "dashboard": {"active_job_ids": active, "material_count": len(project["materials"]), "run_count": len(runs), "latest_run": latest, "readiness": project["plan"]["status"] if project["plan"] else "review_brief" if project["brief"] else "needs_materials" if not wd.latest_material(project, "csv") else "needs_brief"}}


def _local_reply(project, text, server):
    csv = wd.latest_material(project, "csv")
    if csv is None:
        return "Attach a CSV to investigate your question. A question alone is saved context, not a measured experiment. A compatible training script lets us inspect your existing protocol; CSV alone creates a clearly labelled generated baseline."
    if project.get("brief_dirty"):
        return "Your materials have changed. Review the target, predictor roles and intended use, then save a new brief revision. Earlier runs remain bound to their original inputs."
    if project.get("plan") and project["plan"]["status"] != "ready":
        needs = wd.filter_guidance_questions(project, project["plan"]["questions"]) + project["plan"]["scope_gaps"]
        proposals = wd.guidance_state(project)["proposals"]
        return ("The investigation needs these decisions before execution: " + " ".join(needs) if needs else "The existing plan still belongs to your previous reviewed brief.") + (" Review the quoted proposed answers in the study brief and save a new revision to refresh this plan." if proposals else "")
    if project["runs"]:
        context = _run_context(project, server)
        if context["status"] == "unavailable":
            return "The saved audit file is unavailable. Your research question and materials remain saved; no result is inferred. Review a new plan if you want another explicit run."
        if context["status"] not in TERMINAL:
            return "Your latest audit is still running" + (f" at {context['phase']}" if context.get("phase") else "") + ". Check the real stage events; no final conclusion is available yet."
        if not context["finalized"] or not context["evidence_verified"]:
            return context.get("note", "The saved checkpoint is not a verified finalized result; no numerical conclusion is supplied.")
        if context.get("summary"):
            summary = context["summary"]
            descriptive = any(str(limit).startswith("Group/time control measured descriptively only") for limit in context.get("limitations", []))
            return f"The saved audit measured {summary['claimed']:.4f} → {summary['controlled']:.4f} {summary['metric']}, with outcome {context['verdict']}. " + ("This group/time comparison is descriptive: the conditional row intervals do not account for repeated entities or time dependence, so the large difference does not establish calibrated inflation evidence. " if descriptive else "Inspect its per-seed uncertainty, tested operation and objections. ") + "This applies to the tested protocol only. A changed research question or material needs a new reviewed brief and run."
        return f"Your saved audit ended {context.get('verdict', 'without a finalized measurement')}. No counterfactual was measured. " + " ".join((context.get("questions") or []) + (context.get("scope_gaps") or []))
    candidates = csv["profile"]["target_candidates"]
    clarifications = wd.guidance_state(project)
    if clarifications["confirmed"] or clarifications["proposals"]:
        labels = {"target": "outcome column", "intended_use": "intended use", "population": "evaluation population", "decision_time": "prediction time", "predictor_availability": "availability of all selected predictors", "entity_column": "entity identifier column", "time_column": "time column"}
        unresolved = [labels.get(field, field.replace("_", " ")) for field in clarifications["missing"]]
        return ("Your author-reviewed answers are retained. " if clarifications["confirmed"] else "Your explicit answers are available as quoted brief suggestions. ") + ("Review the proposed values in the study brief; nothing is confirmed automatically. " if clarifications["proposals"] else "") + ("Still needed: " + ", ".join(unresolved) + "." if unresolved else "Review and save the brief, then inspect its concrete experiment plan.")
    return f"I can observe {csv['profile']['rows']} rows and {len(csv['profile']['columns'])} columns. " + ("Possible binary targets: " + ", ".join(candidates[:8]) + ". " if candidates else "No supported binary target was found. ") + "Confirm which outcome you want to predict, when the inputs are available, and which population the result should cover. Save that reviewed brief to prepare an investigation plan."


def _add_message(store, project_id, body, server):
    if body.live and os.environ.get("NULLLAB_ALLOW_WEB_LIVE") != "1":
        raise HTTPException(403, "Meta guidance is disabled; local study guidance remains available")
    if body.live and not body.outbound_confirmed:
        raise HTTPException(400, "Review the outbound prompt/material preview before Meta guidance")
    stamp = wd.now()
    user = {"id": wd.uid(), "role": "user", "kind": "research_message", "text": body.text.strip(), "created_at": stamp, "references": []}
    if not user["text"]:
        raise ValueError("Write a research question or follow-up")
    with server._LOCK:
        project = store.get(project_id)
        if body.live and body.context_sha256 != _outbound_preview(project, server)["context_sha256"]:
            raise HTTPException(409, "The outbound context changed. Review the current materials/brief/thread and acknowledge it again.")
        if body.live:
            for material in project["materials"]:
                store.read_material(project, material["id"])
        authorized_run_context = _run_context(project, server)
        # Keep this authorized snapshot even if another request attaches a new
        # material while inference is running. New material cannot enter it.
        store.change(project_id, lambda p: p["messages"].append(user))
        project["messages"].append(user)
    if not body.live:
        project["messages"][-1]["brief_proposals"] = wd.proposals_for_message(project, user)
        reply = wd.local_message(_local_reply(project, body.text, server), references=[m["id"] for m in project["materials"]])
        reply["brief_proposals"] = wd.proposals_for_message(project, user)
    else:
        # Fixed per-investigation clarification envelope; repeated messages cannot
        # reset either the attempt or reservation limit. Raw CSV rows are absent.
        config = replace(ProviderConfig.from_env(), max_tokens=2000, retries=0)
        provider = Provider(config, store.root / "guidance" / project_id, max_usd=0.25, max_calls=4)
        materials = []
        for material in project["materials"]:
            summary = {key: material[key] for key in ("id", "filename", "kind", "profile", "compatibility")}
            if material["kind"] != "csv":
                content = store.read_material(project, material["id"])
                summary["text_excerpt"] = content[:16_000] if material["kind"] == "python" else content[:4000]
                summary["truncated"] = len(content) > len(summary["text_excerpt"])
            materials.append(summary)
        author_proposals = wd.proposals_for_message(project, user)
        proposed_message = {**user, "brief_proposals": author_proposals}
        guidance_project = {**project, "messages": [*project["messages"][:-1], proposed_message]}
        context = {"question": project["question"], "materials": materials, "brief": project["brief"], "clarifications": wd.guidance_state(guidance_project), "recent_messages": [{"id": m["id"], "role": m["role"], "text": m["text"]} for m in project["messages"][-6:]], "latest_run": authorized_run_context, "capabilities": "Supported binary tabular evaluation. CSV creates a fixed Random Forest baseline; compatible trusted-local Python may reproduce a supplied protocol. Never execute arbitrary notebook/PDF. Future/unseen-entity generated tasks are unsupported. Ask only for unresolved timing/population instead of inferring it. Mechanical applicability or runtime rejection overrides a model's supported assessment; state disagreements accurately rather than recasting them as agreement."}
        try:
            raw = provider.complete(wd.GUIDANCE_INSTRUCTIONS, json.dumps(context), role="intake", response_format={"type": "json_object"})
            parsed = json.loads(raw)
            if not isinstance(parsed, dict) or set(parsed) - {"text", "questions", "references", "brief_proposals"} or not isinstance(parsed.get("text"), str) or not 1 <= len(parsed["text"]) <= 6000:
                raise ValueError("Invalid guidance schema")
            questions, references = parsed.get("questions", []), parsed.get("references", [])
            if not isinstance(questions, list) or not all(isinstance(q, str) and len(q) <= 1000 for q in questions) or not isinstance(references, list) or not all(ref in {m["id"] for m in materials} for ref in references):
                raise ValueError("Invalid guidance references")
            reply = wd.local_message(parsed["text"], references=references, kind="meta_guidance")
            reply["brief_proposals"] = wd.validate_brief_proposals(store, project, parsed.get("brief_proposals", [])) + author_proposals
            filtered_project = {**project, "messages": [*project["messages"], reply]}
            questions = wd.filter_guidance_questions(filtered_project, questions)
            reply["text"] = wd.filter_guidance_text(filtered_project, parsed["text"])
            reply.update(questions=questions, model=provider.model_for("intake"), ledger=provider.ledger(), note="Unmeasured model guidance; proposed facts require author review.")
        except Exception as exc:
            reply = wd.local_message("Meta guidance could not complete. Your question and materials are saved. Continue with local guidance or edit the study brief; no experiment result was inferred.", kind="guidance_error")
            reply.update(error_type=type(exc).__name__, ledger=provider.ledger())
    reply["reply_to"] = user["id"]
    return store.change(project_id, lambda p: p["messages"].append(reply))


def _make_plan(store, project_id, server):
    project = store.get(project_id)
    if _active(project, server):
        raise ValueError("Wait for the active audit before preparing another plan")
    brief = project["brief"]
    if not brief:
        raise ValueError("Review and save your research brief first")
    if project.get("brief_dirty") or brief["material_ids"] != [m["id"] for m in project["materials"]]:
        raise ValueError("Materials changed; save a new reviewed brief before planning")
    # Revalidate material identities and declarations, rather than trusting UI.
    for material_id in brief["material_ids"]:
        store.read_material(project, material_id)
    review = brief["review"]
    plan = {"id": wd.uid(), "revision_id": brief["id"], "created_at": wd.now(), "source_mode": brief["source_mode"], "method": "Generated Random Forest baseline" if brief["source_mode"] == "generated" else "Supplied compatible Python pipeline", "status": review["status"], "questions": review["questions"], "scope_gaps": review["scope_gaps"], "warnings": review["warnings"], "steps": ["Freeze this brief and exact material bytes", "Execute the starting protocol on three fixed seeds", "Propose a supported typed control using local rules or optional Meta", "Validate applicability and preserve the model", "Measure accepted controls and retain objections", "Export input-bound evidence or an explicitly unmeasured assessment"], "budget": {"audit_max_calls": 4, "audit_max_reserved_usd": 1, "guidance_max_calls_per_investigation": 4, "guidance_max_reserved_usd_per_investigation": 0.25}, "case": None}
    compatibility = _protocol_check(store, project, brief)
    plan.update(compatibility=compatibility, protocol=compatibility["protocol"], steps=workdesk_protocol.steps(compatibility["protocol"], brief["source_mode"]))
    if plan["status"] == "ready" and compatibility["status"] == "blocked":
        plan.update(status="unsupported", scope_gaps=[*plan["scope_gaps"], *compatibility["messages"]])
    if plan["status"] == "ready":
        csv_text = store.read_material(project, brief["csv_material_id"])
        note_parts = []
        remaining = 12_000
        for material in project["materials"]:
            if material["kind"] == "notes" and remaining > 0:
                original = store.read_material(project, material["id"])
                excerpt = original[:min(4000, remaining)]
                remaining -= len(excerpt)
                note_parts.append(f"Author material {material['id']} ({material['filename']}):\n{excerpt}" + ("\n[Excerpt truncated; original material retained.]" if len(excerpt) < len(original) else ""))
        research_context = "Research question:\n" + project["question"] + "\n\nIntended use:\n" + brief["intended_use"]
        if note_parts:
            research_context += "\n\nAuthor-provided notes (not independently verified):\n" + "\n\n".join(note_parts)
        snapshot = {"investigation_id": project_id, "brief_revision_id": brief["id"], "brief_sha256": wd.identity(brief), "plan_id": plan["id"], "question": project["question"], "materials": [{"id": m["id"], "sha256": m["sha256"], "filename": m["filename"]} for m in project["materials"]], "orchestration_sources": {"agent/workdesk.py": hashlib.sha256(Path(wd.__file__).read_bytes()).hexdigest(), "agent/workdesk_protocol.py": hashlib.sha256(Path(workdesk_protocol.__file__).read_bytes()).hexdigest(), "app/workdesk_api.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}}
        if brief["source_mode"] == "generated":
            created = server._new_generated_case(csv_text, brief["target"], brief["intended_use"], brief["study"])
            case = created["case"]
            path = server.cases()[case]
            config = json.loads((path / "case.json").read_text())
            config["workdesk"] = snapshot
            write_json(path / "case.json", config)
            original_excerpt = (path / "excerpt.md").read_text(encoding="utf-8")
            (path / "excerpt.md").write_text(research_context + "\n\nGenerated adapter protocol:\n" + original_excerpt, encoding="utf-8")
        else:
            case = "user-" + wd.uid().replace("-", "")
            staging = store.root / "staging" / case
            staging.mkdir(parents=True)
            (staging / "data.csv").write_bytes(csv_text.encode("utf-8"))
            (staging / "train.py").write_bytes(store.read_material(project, brief["python_material_id"]).encode("utf-8"))
            (staging / "excerpt.md").write_text(research_context + "\n", encoding="utf-8")
            write_json(staging / "case.json", {"title": project["title"], "target": brief["target"], "intended_use": brief["intended_use"], "study": brief["study"], "adapter": "trusted-local-python", "generated_pipeline": False, "workdesk": snapshot})
            from agent.engine import preflight

            preflight(staging)  # AST + data only; never imports the Python source.
            destination = server.WORKSPACE / "examples" / case
            destination.parent.mkdir(parents=True, exist_ok=True)
            from agent.storage import publish_directory

            publish_directory(staging, destination)
        plan["case"] = case
        from agent.evidence import input_hashes

        plan["input_hashes"] = input_hashes(server.cases()[case])
    return store.change(project_id, lambda p: (p.update(plan=plan), p["plans"].append(plan), p["messages"].append(wd.local_message("Investigation plan prepared. " + ("Review the protocol and choose local or acknowledged Meta execution." if plan["status"] == "ready" else "Resolve the listed questions or scope gaps; no training has run.")))))


def _protocol_check(store, project, brief):
    if brief["source_mode"] == "custom":
        source = store.read_material(project, brief["python_material_id"])
    else:
        from agent.intake import TEMPLATE

        source = TEMPLATE.format(target=brief["target"], predictors=brief["review"]["predictor_columns"])
    return workdesk_protocol.check(source, brief, csv_text=store.read_material(project, brief["csv_material_id"]))


def create_router(server):
    """Install after existing server routes: app.include_router(create_router(module))."""
    router = APIRouter()

    def store():
        return wd.WorkdeskStore(server.WORKSPACE)

    @router.get("/api/workdesk/config")
    def config():
        return {"live_enabled": os.environ.get("NULLLAB_ALLOW_WEB_LIVE") == "1", "supported_files": [".csv", ".py", ".txt", ".md"], "limits": {"csv_mb": 5, "text_kb": 256, "materials": 20, "rows_min": 30, "rows_max": 20_000, "audit_max_attempts": 4, "audit_max_reserved_usd": 1, "guidance_max_attempts": 4, "guidance_max_reserved_usd": 0.25}, "scope": "Supported binary tabular evaluations on this local machine. CSV alone creates a generated baseline; compatible Python is explicitly trusted-local code."}

    @router.get("/api/investigations")
    def list_investigations():
        return {"investigations": [_detail(p, server) for p in store().list()]}

    @router.post("/api/investigations", status_code=201)
    def new_investigation(body: NewInvestigation):
        try:
            return _detail(store().create(body.question, body.title), server)
        except (ValueError, KeyError) as exc:
            raise _error(exc) from None

    @router.get("/api/investigations/{project_id}")
    def get_investigation(project_id: str):
        try:
            return _detail(store().get(project_id), server)
        except (ValueError, KeyError) as exc:
            raise _error(exc) from None

    @router.post("/api/investigations/{project_id}/materials", status_code=201)
    async def attach_material(project_id: str, request: Request):
        body = await _body(request, Material)
        try:
            db = store()
            if (body.content is None) == (body.content_b64 is None):
                raise ValueError("Supply exactly one UTF-8 content string or original-file content_b64 payload")
            raw_data = base64.b64decode(body.content_b64, validate=True) if body.content_b64 is not None else body.content.encode("utf-8")
            content = raw_data.decode("utf-8")
            def attach():
                if _active(db.get(project_id), server):
                    raise ValueError("Wait for the current audit before attaching a new material version")
                return db.attach(project_id, body.filename, content, raw_data=raw_data)

            return _detail(await run_in_threadpool(_locked, server, attach), server)
        except (ValueError, KeyError, UnicodeError, binascii.Error) as exc:
            raise _error(exc) from None

    @router.get("/api/investigations/{project_id}/materials/{material_id}")
    def material_content(project_id: str, material_id: str):
        try:
            db = store()
            project = db.get(project_id)
            return {"id": material_id, "content": db.read_material(project, material_id)}
        except (ValueError, KeyError) as exc:
            raise _error(exc) from None

    @router.post("/api/investigations/{project_id}/messages")
    async def add_message(project_id: str, body: Message):
        try:
            return _detail(await run_in_threadpool(_add_message, store(), project_id, body, server), server)
        except (ValueError, KeyError) as exc:
            raise _error(exc) from None

    @router.post("/api/investigations/{project_id}/brief")
    def save_brief(project_id: str, body: Brief):
        try:
            db = store()
            def save():
                project = db.get(project_id)
                if _active(project, server):
                    raise ValueError("Wait for the current audit before saving a new brief revision")
                value = wd.review_brief(db, project, body.model_dump())
                return db.change(project_id, lambda p: (p.update(brief=value, plan=None, brief_dirty=False), p["brief_revisions"].append(value)))

            return _detail(_locked(server, save), server)
        except (ValueError, KeyError) as exc:
            raise _error(exc) from None

    @router.post("/api/investigations/{project_id}/plan")
    def prepare_plan(project_id: str):
        try:
            return _detail(_locked(server, _make_plan, store(), project_id, server), server)
        except (ValueError, KeyError, OSError) as exc:
            raise _error(exc) from None

    @router.post("/api/investigations/{project_id}/runs", status_code=202)
    def start_run(project_id: str, body: Run):
        try:
            db = store()
            def start():
                project = db.get(project_id)
                plan = project["plan"]
                if not plan or plan["status"] != "ready" or plan["revision_id"] != project["brief"]["id"] or project.get("brief_dirty"):
                    raise ValueError("Review a ready plan for the current brief/materials before running")
                if body.plan_id != plan["id"]:
                    raise HTTPException(409, "The reviewed plan changed. Open the current plan before starting its run.")
                if _active(project, server):
                    raise ValueError("This investigation already has an active audit")
                from agent.evidence import input_hashes

                if plan["input_hashes"] != input_hashes(server.cases()[plan["case"]]):
                    raise ValueError("Prepared case changed; prepare a new plan before execution")
                compatibility = _protocol_check(db, project, project["brief"])
                if compatibility["status"] == "blocked":
                    raise HTTPException(409, "The required split operation is not applicable to this source. Prepare a new plan to review the adapter guidance; no training or model call started.")
                job = server.create_job(server.AuditRequest(case=plan["case"], live=body.live, critic=body.critic, outbound_confirmed=body.outbound_confirmed))
                link = {"job_id": job["id"], "revision_id": project["brief"]["id"], "plan_id": plan["id"], "created_at": wd.now(), "requested_mode": "live" if body.live else "rules", "requested_critic": body.critic}
                try:
                    project = db.change(project_id, lambda p: p["runs"].append(link))
                except Exception:
                    # _run cannot pass the same server lock until this route
                    # releases it, so cancellation precedes execution/dispatch.
                    server.cancel_job(job["id"])
                    raise HTTPException(503, "The audit could not be linked to its investigation and was cancelled before execution. Your materials remain saved.") from None
                return {**_detail(project, server), "job": job}

            return _locked(server, start)
        except (ValueError, KeyError) as exc:
            raise _error(exc) from None

    @router.post("/api/investigations/{project_id}/example")
    def attach_example(project_id: str, body: Example):
        try:
            db = store()
            def attach():
                project = db.get(project_id)
                if _active(project, server):
                    raise ValueError("Wait for the current audit before adding example materials")
                if len(project["materials"]) > wd.MAX_MATERIALS - 3:
                    raise ValueError("This example needs three material slots; start another investigation")
                if body.case not in {"secom", "secom_clean"}:
                    raise ValueError("Choose an available public manufacturing example")
                source = server.cases().get(body.case)
                if source is None:
                    raise ValueError("Public example is not available in this workspace")
                # One SQLite metadata change, with staged-file rollback on
                # failure. No reader observes a half-imported example.
                files = [(name, (source / name).read_bytes()) for name in ("data.csv", "train.py", "excerpt.md")]
                return db.attach_many(project_id, files, csv_limit=50_000_000)

            return _detail(_locked(server, attach), server)
        except (ValueError, KeyError, OSError) as exc:
            raise _error(exc) from None

    return router
