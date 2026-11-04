"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const terminal = status => ["completed", "inconclusive", "failed", "cancelled"].includes(status);
  const verdicts = {
    INFLATED: "The tested control lowered the score",
    NO_EFFECT_DETECTED: "No effect detected for this control",
    CONTROL_SCORE_HIGHER: "The tested control increased the score",
    MODEL_NO_FLAW: "The model proposed no flaw",
    NOT_TESTED: "No supported control was measured",
    DISPUTED: "The interpretation is disputed",
    INCONCLUSIVE: "The evidence is inconclusive",
    UNSUPPORTED: "This concern needs a different instrument",
    NEEDS_INFORMATION: "More information is needed before testing"
  };
  const state = {
    project: null, projects: [], config: {}, pending: [], view: "research", busy: 0,
    epoch: 0, jobEpoch: 0, selectedJob: null, job: null, timer: null,
    activeJob: null, cancelRequested: null, briefDirty: false, materialKey: "",
    threadKey: "", drawerOpen: false, priorFocus: null, drafts: new Map(),
    outboundKey: "", intakeConsentHash: null, reviewedPlanId: null
  };
  const text = (id, value) => { $(id).textContent = value == null ? "" : String(value); };
  const node = (tag, value, className) => {
    const element = document.createElement(tag);
    if (value != null) element.textContent = String(value);
    if (className) element.className = className;
    return element;
  };
  const fmt = value => typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : "—";
  const list = value => Array.isArray(value) ? value : [];
  const contentText = value => typeof value === "string" ? value : value && typeof value === "object" ? value.text || value.question || value.title || value.description || JSON.stringify(value) : "";
  const shortId = value => String(value || "").slice(0, 8);
  const briefFields = {
    target: ["Outcome column", "briefTarget"], intended_use: ["Decision or research claim", "briefUse"],
    population: ["Where the result must apply", "briefPopulation"], decision_time: ["Prediction time", "briefDecisionTime"],
    predictor_availability: ["Predictor availability", "briefAvailability"], unit_of_analysis: ["One row represents", "briefUnit"],
    entity_column: ["Entity/group column", "briefEntity"], time_column: ["Time column", "briefTime"],
    source_mode: ["Pipeline to investigate", "sourceMode"]
  };
  const briefValueLabels = {
    unseen_entities: "Previously unseen entities", represented_entities: "More records from represented entities",
    independent_records: "New independent records", future_records: "Future records", confirmed: "Available at prediction time — review required",
    unknown: "Not confirmed", custom: "Supplied Python pipeline", generated: "Create a baseline from the CSV"
  };
  const projectPath = (suffix = "", id = state.project?.id) => `/api/investigations/${encodeURIComponent(id)}${suffix}`;
  const dateLabel = value => {
    if (!value) return "Saved locally";
    const date = new Date(value);
    return Number.isNaN(date.valueOf()) ? "Saved locally" : date.toLocaleDateString(undefined, {month: "short", day: "numeric"});
  };

  async function api(path, body) {
    const response = await fetch(path, body === undefined ? {} : {
      method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = typeof data.detail === "string" ? data.detail : "The request could not be completed. Your saved work is preserved.";
      throw new Error(detail);
    }
    return data;
  }

  function notice(message, tone = "error") {
    text("deskNotice", message);
    $("deskNotice").dataset.tone = tone;
    $("deskNotice").hidden = !message;
    for (const prefix of ["run", "example", "material"]) {
      const id = prefix === "run" ? "runDialog" : prefix === "example" ? "exampleDialog" : "materialDialog";
      const region = $(prefix + "DialogNotice");
      if (region) { region.textContent = message || ""; region.hidden = !message || !$(id).open; }
    }
  }

  async function busy(task, label = "Saving your work…") {
    state.busy++;
    text("threadStatus", label);
    text("requestProgress", label + (label.startsWith("Meta") ? " The bounded provider request is pending; no experiment is running. Keep this page open or return to the saved investigation." : " Your existing saved inputs and results remain available."));
    $("requestProgress").hidden = false;
    syncControls();
    try { return await task(); }
    catch (error) { notice(error.message || "This action could not finish. Your saved work is preserved."); return null; }
    finally {
      state.busy--;
      text("threadStatus", "Grounded in your materials");
      $("requestProgress").hidden = !state.busy;
      syncControls();
    }
  }

  function remember() {
    const params = new URLSearchParams();
    if (state.project) params.set("project", state.project.id);
    if (state.selectedJob) params.set("run", state.selectedJob);
    if (state.project && state.view !== "research") params.set("view", state.view);
    window.history.replaceState(null, "", "/workdesk" + (params.size ? "?" + params.toString() : ""));
  }

  function saveDraft() {
    const key = state.project?.id || "new";
    state.drafts.set(key, {
      pending: [...state.pending], message: $("followupQuestion").value,
      question: $("researchQuestion").value,
      brief: state.briefDirty && state.project ? readBrief() : null
    });
  }

  function restoreDraft(key) {
    const draft = state.drafts.get(key);
    state.pending = draft?.pending || [];
    $("followupQuestion").value = draft?.message || "";
    if (key === "new") $("researchQuestion").value = draft?.question || "";
    if (draft?.brief) { fillBrief(draft.brief); state.briefDirty = true; }
    renderPending();
  }

  function setView(view, focus = false) {
    state.view = ["research", "brief", "results", "materials"].includes(view) ? view : "research";
    $("investigationGrid").dataset.view = state.view;
    document.querySelectorAll(".desk-tabs button").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.view === state.view)));
    if (state.project) remember();
    if (focus) {
      if (state.view !== "research") $("contextColumn").scrollTop = 0;
      const target = {research: "followupQuestion", brief: "briefTarget", results: state.selectedJob ? "runTitle" : "resultsTitle", materials: "materialsTitle"}[state.view];
      $(target)?.focus({preventScroll: true});
    }
  }

  function closeDrawer(restore = true) {
    state.drawerOpen = false;
    $("projectRail").removeAttribute("data-open");
    $("projectToggle").setAttribute("aria-expanded", "false");
    $("railScrim").hidden = true;
    $("researchMain").inert = false;
    document.body.style.overflow = "";
    if (restore) state.priorFocus?.focus();
  }

  function toggleDrawer() {
    if (state.drawerOpen) return closeDrawer();
    state.priorFocus = document.activeElement;
    state.drawerOpen = true;
    $("projectRail").dataset.open = "true";
    $("projectToggle").setAttribute("aria-expanded", "true");
    $("railScrim").hidden = false;
    $("researchMain").inert = true;
    document.body.style.overflow = "hidden";
    $("newInvestigation").focus();
  }

  function syncControls() {
    const blocked = state.busy > 0;
    const running = Boolean(state.activeJob);
    ["startInvestigation", "sendMessage", "downloadInvestigation"].forEach(id => { $(id).disabled = blocked; });
    $("loadExample").disabled = blocked || running;
    ["startAttach", "threadAttach", "materialsAttach"].forEach(id => { $(id).disabled = blocked || running; });
    $("saveBrief").disabled = blocked || running || !state.project;
    $("reviewRun").disabled = blocked || running || state.briefDirty || state.project?.brief_dirty || state.project?.plan?.status !== "ready";
    $("startRun").disabled = blocked || running || state.briefDirty || state.project?.brief_dirty || state.project?.plan?.status !== "ready";
    $("cancelRun").hidden = !state.activeJob;
    $("cancelRun").disabled = blocked || state.cancelRequested === state.activeJob;
    text("cancelRun", state.cancelRequested === state.activeJob ? "Cancellation requested" : "Cancel active run");
    $("useMetaIntake").disabled = !state.config.live_enabled || blocked;
    $("runMode").querySelector('option[value="live"]').disabled = !state.config.live_enabled;
    $("intakeConsentRow").hidden = !$("useMetaIntake").checked;
    text("assistantMode", $("useMetaIntake").checked ? "Meta · optional guidance" : "Local study guide");
    $("runMetaOptions").hidden = $("runMode").value !== "live";
    text("briefSaveNote", running ? "A run is active. Its input snapshot is fixed; save a new revision after it finishes." : state.briefDirty || state.project?.brief_dirty ? "Unsaved changes need a new reviewed brief and plan before running." : "Saving creates a new revision. Earlier run evidence stays attached to its original inputs.");
    renderBriefSuggestions(state.project);
  }

  function renderProjects() {
    const container = $("projectList");
    container.replaceChildren();
    if (!state.projects.length) container.append(node("p", "Your investigations will be saved here.", "small-muted"));
    state.projects.forEach(project => {
      const button = node("button", null, "project-item");
      button.type = "button";
      button.dataset.projectId = project.id;
      button.title = project.question || project.title || "";
      button.setAttribute("aria-current", String(project.id === state.project?.id));
      button.append(node("strong", project.title || project.question || "Untitled investigation"));
      const count = project.run_count ?? project.dashboard?.run_count ?? list(project.runs).length;
      button.append(node("span", dateLabel(project.updated_at || project.created_at) + ` · ${count} run${count === 1 ? "" : "s"}`));
      button.addEventListener("click", () => openProject(project.id));
      container.append(button);
    });
  }

  async function refreshProjects() {
    const data = await api("/api/investigations");
    state.projects = Array.isArray(data) ? data : data.investigations || data.projects || [];
    renderProjects();
  }

  function updateProjectList(project) {
    const item = {id: project.id, title: project.title, question: project.question, updated_at: project.updated_at, created_at: project.created_at, run_count: list(project.runs).length};
    state.projects = [item, ...state.projects.filter(p => p.id !== item.id)];
    renderProjects();
  }

  function renderPending() {
    ["startPendingFiles", "threadPendingFiles"].forEach(id => {
      const container = $(id);
      container.replaceChildren();
      state.pending.forEach(file => {
        const chip = node("span", null, "file-chip");
        chip.append(node("span", file.name));
        const remove = node("button", "×");
        remove.type = "button";
        remove.setAttribute("aria-label", `Remove pending attachment ${file.name}`);
        remove.addEventListener("click", () => { state.pending = state.pending.filter(p => p !== file); renderPending(); });
        chip.append(remove); container.append(chip);
      });
    });
  }

  function messagesKey(project) {
    return project.id + ":" + list(project.messages).map(message => message.id || message.text).join(":");
  }

  function readableMessageText(value, message, project) {
    let content = String(value || "");
    const referenceIds = new Set(list(message.references).map(reference => typeof reference === "string" ? reference : reference.material_id || reference.id));
    list(project.materials).forEach(material => {
      if (referenceIds.has(material.id) && typeof material.id === "string" && material.id) content = content.split(material.id).join(material.filename || "Attached material");
    });
    return content;
  }

  function renderThread(project) {
    const key = messagesKey(project);
    if (state.threadKey === key) return;
    state.threadKey = key;
    const container = $("researchThread");
    container.replaceChildren();
    if (!list(project.messages).length) container.append(node("p", "Your question is saved. Attach materials or add context to begin framing the study.", "thread-empty"));
    list(project.messages).forEach(message => {
      const role = message.role === "user" ? "user" : message.role === "system" ? "system" : "assistant";
      const article = node("article", null, "message " + role);
      const header = node("div", null, "message-header");
      const model = /meta|model/.test(message.kind || "");
      header.append(node("strong", role === "user" ? "You" : model ? `Meta · ${message.model || "intake review"}` : role === "system" ? "Investigation record" : "Local study guide"));
      if (message.created_at) header.append(node("span", new Date(message.created_at).toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit"})));
      article.append(header, node("div", readableMessageText(message.text, message, project), "message-body"));
      if (list(message.questions).length) {
        const questions = node("ul");
        message.questions.forEach(question => questions.append(node("li", readableMessageText(contentText(question), message, project))));
        article.append(questions);
      }
      if (list(message.references).length) {
        const references = node("div", null, "message-references");
        message.references.forEach(reference => {
          const id = typeof reference === "string" ? reference : reference.material_id || reference.id;
          const material = list(project.materials).find(item => item.id === id);
          if (!material) return;
          const button = node("button", material.filename, "reference-chip");
          button.type = "button";
          button.addEventListener("click", () => previewMaterial(material));
          references.append(button);
        });
        article.append(references);
      }
      if (message.ledger) article.append(node("p", `${message.ledger.calls || 0} provider attempts · $${Number(message.ledger.est_usd || 0).toFixed(3)} reserved estimate · unmeasured guidance`, "field-note"));
      container.append(article);
    });
    container.scrollTop = container.scrollHeight;
  }

  function renderBriefSuggestions(project) {
    const container = $("briefSuggestions");
    container.replaceChildren();
    if (!project) { container.hidden = true; return; }
    const current = project.brief || {};
    const suggestions = list(project.brief_suggestions).filter(suggestion => {
      if (!briefFields[suggestion.field] || typeof suggestion.value !== "string" || !suggestion.value.trim() || suggestion.requires_author_review !== true) return false;
      const source = list(project.messages).some(message => message.id === suggestion.source_id && message.role === "user") || list(project.materials).some(material => material.id === suggestion.source_id);
      const saved = suggestion.field in current ? current[suggestion.field] : current.study?.[suggestion.field];
      return source && saved !== suggestion.value;
    });
    container.hidden = !suggestions.length;
    if (!suggestions.length) return;
    container.append(node("h3", "From your research context"), node("p", "Review each suggestion before using it in your draft. Saving the brief confirms your declarations; suggestions never change a saved revision.", "field-note"));
    const copyValue = suggestion => {
      const control = $(briefFields[suggestion.field][1]);
      const options = Array.from(control.options || []);
      if (options.length && !options.some(option => option.value === suggestion.value)) return false;
      control.value = suggestion.value;
      if (suggestion.field === "source_mode") $("trustCode").checked = false;
      return true;
    };
    const markDraft = () => {
      state.briefDirty = true;
      updateSourceMode(); renderPlan(project); syncControls(); setView("brief");
      notice("Suggestions copied into your draft. Review every declaration and save the brief to confirm them. Trusted code still requires its separate acknowledgement.", "success");
    };
    const bulk = node("button", "Copy suggestions to draft", "button secondary full-width");
    bulk.type = "button"; bulk.disabled = state.busy > 0 || Boolean(state.activeJob);
    bulk.addEventListener("click", () => {
      if (state.busy || state.activeJob || state.project?.id !== project.id) return;
      suggestions.forEach(copyValue); markDraft();
      const firstField = $(briefFields[suggestions[0].field][1]);
      firstField.focus({preventScroll: true}); firstField.scrollIntoView({block: "nearest"});
    });
    container.append(bulk);
    const sources = node("details", null, "suggestion-details");
    sources.append(node("summary", `Review ${suggestions.length} source ${suggestions.length === 1 ? "quote" : "quotes"} & individual fields`));
    suggestions.forEach(suggestion => {
      const card = node("article", null, "brief-suggestion");
      const [label, inputId] = briefFields[suggestion.field];
      card.append(node("strong", label), node("p", briefValueLabels[suggestion.value] || suggestion.value));
      const sourceMaterial = list(project.materials).find(material => material.id === suggestion.source_id);
      const source = sourceMaterial?.filename || "Your research message";
      card.append(node("p", source + (suggestion.quote ? ": “" + suggestion.quote + "”" : ""), "suggestion-source"));
      const button = node("button", "Use in draft", "text-button suggestion-apply");
      button.type = "button";
      button.disabled = state.busy > 0 || Boolean(state.activeJob);
      button.addEventListener("click", () => {
        if (state.busy || state.activeJob || state.project?.id !== project.id) return;
        if (!copyValue(suggestion)) return notice("This suggestion is outside the supported choices. Review the study brief manually.");
        markDraft();
        const control = $(inputId);
        control.focus({preventScroll: true});
        control.scrollIntoView({block: "nearest"});
      });
      card.append(button); sources.append(card);
    });
    container.append(sources);
  }

  function latestCsv(project = state.project) {
    return [...list(project?.materials)].reverse().find(material => material.kind === "csv");
  }

  function fillBrief(brief = state.project?.brief || {}) {
    const project = state.project;
    if (!project) return;
    const csv = latestCsv(project);
    const columns = list(csv?.profile?.columns).map(column => typeof column === "string" ? column : column.name).filter(Boolean);
    const target = $("briefTarget");
    target.replaceChildren();
    const empty = node("option", columns.length ? "Choose the outcome column" : "Attach a CSV to choose a target");
    empty.value = ""; target.append(empty);
    columns.forEach(column => { const option = node("option", column); option.value = column; target.append(option); });
    const candidate = list(csv?.profile?.target_candidates);
    target.value = columns.includes(brief.target) ? brief.target : candidate.length === 1 ? candidate[0] : "";
    $("sourceMode").value = brief.source_mode || project.suggested_source_mode || "generated";
    $("briefUse").value = brief.intended_use || project.question || "";
    const study = brief.study || {};
    $("briefPopulation").value = study.population || "undecided";
    $("briefDecisionTime").value = study.decision_time || "";
    $("briefAvailability").value = study.predictor_availability || "unknown";
    $("briefUnit").value = study.unit_of_analysis || "";
    $("briefEntity").value = study.entity_column || "";
    $("briefTime").value = study.time_column || "";
    $("briefExclude").value = list(study.excluded_columns).join(", ");
    const python = [...list(project.materials)].reverse().find(material => material.kind === "python");
    $("trustCode").checked = brief.trust_code === true && Boolean(python) && brief.python_material_id === python.id;
    updateSourceMode();
  }

  function readBrief() {
    return {
      target: $("briefTarget").value,
      intended_use: $("briefUse").value.trim(),
      source_mode: $("sourceMode").value,
      trust_code: $("sourceMode").value === "custom" && $("trustCode").checked,
      study: {
        title: state.project?.title || "Your investigation",
        population: $("briefPopulation").value,
        decision_time: $("briefDecisionTime").value.trim(),
        predictor_availability: $("briefAvailability").value,
        unit_of_analysis: $("briefUnit").value.trim(),
        entity_column: $("briefEntity").value.trim(),
        time_column: $("briefTime").value.trim(),
        excluded_columns: [...new Set($("briefExclude").value.split(",").map(item => item.trim()).filter(Boolean))]
      }
    };
  }

  function updateSourceMode() {
    const custom = $("sourceMode").value === "custom";
    const hasPython = list(state.project?.materials).some(material => material.kind === "python");
    $("trustCodeRow").hidden = !custom;
    text("sourceModeHint", custom
      ? "Uses your attached compatible load / feats / claimed_eval Python adapter. Code is inspected before trusted-local execution."
      : "Creates a fixed Random Forest baseline from the selected numeric predictors." + (hasPython ? " Your attached Python pipeline will not be used in this mode." : " This does not reproduce an existing study."));
  }

  function renderPlan(project) {
    if (!project) return;
    const plan = project.plan;
    $("planCard").hidden = !plan;
    if (!plan) return;
    text("planState", project.brief_dirty || state.briefDirty ? "Review changes" : plan.status === "ready" ? "Ready to review" : plan.status === "unsupported" ? "Scope gap" : "Needs information");
    $("planSteps").replaceChildren();
    list(plan.steps).forEach(step => $("planSteps").append(node("li", contentText(step))));
    const preflight = $("planCompatibility");
    preflight.replaceChildren(); preflight.hidden = !plan.compatibility;
    if (plan.compatibility) {
      const check = plan.compatibility;
      preflight.dataset.state = check.status;
      preflight.append(node("h4", check.status === "blocked" ? "This control cannot run with the supplied adapter" : check.status === "applicable" ? "Static control preflight passed" : "Control scope checked"));
      list(check.messages).forEach(message => preflight.append(node("p", contentText(message))));
      list(check.rejected).forEach(rejected => preflight.append(node("p", `${rejected.step || "Adapter"}: ${rejected.reason || "Control is not applicable"}`)));
      preflight.append(node("p", check.note || "Static applicability is checked without executing source. Runtime fidelity and leakage guards must still pass.", "field-note"));
    }
    const questions = $("planQuestions");
    questions.replaceChildren();
    const items = [...list(plan.questions), ...list(plan.scope_gaps)];
    if (items.length) {
      questions.append(node("p", "Resolve before execution:"));
      const bullets = node("ul"); items.forEach(item => bullets.append(node("li", contentText(item)))); questions.append(bullets);
    }
    if (list(plan.warnings).length) {
      questions.append(node("p", "Limits to review:"));
      const warnings = node("ul"); plan.warnings.forEach(warning => warnings.append(node("li", contentText(warning)))); questions.append(warnings);
    }
    const source = plan.source_mode === "custom" ? "Supplied Python pipeline" : "Generated Random Forest baseline";
    const protocol = plan.protocol;
    text("planScope", source + (protocol ? ` · ${protocol.metric || "declared metric"} · seeds ${list(protocol.seeds).join(", ")} · target ${protocol.target || "not declared"}. ` : ". ") + "The plan is not a measured result; runtime guards and the final recorded outcome determine what was actually tested.");
  }

  function renderMaterials(project) {
    const container = $("materialList");
    container.replaceChildren();
    if (!list(project.materials).length) container.append(node("p", "Attach a CSV, compatible Python pipeline or text notes. Your original file bytes will be retained.", "small-muted"));
    list(project.materials).forEach(material => {
      const card = node("article", null, "material-card");
      card.append(node("h3", material.filename));
      card.append(node("div", `${String(material.kind || "material").toUpperCase()} · ${Number(material.bytes || 0).toLocaleString()} bytes · ${shortId(material.sha256)}`, "material-meta"));
      const compatibility = material.compatibility;
      if (compatibility) {
        const problems = typeof compatibility === "string" ? compatibility : compatibility.reason || list(compatibility.problems).join(" ") || (compatibility.supported || compatibility.compatible ? "Compatible adapter shape; source is not executed during inspection." : JSON.stringify(compatibility));
        card.append(node("p", problems));
      }
      const preview = node("button", "Inspect material ↗", "text-button");
      preview.type = "button"; preview.addEventListener("click", () => previewMaterial(material)); card.append(preview);
      container.append(card);
    });
    const csv = latestCsv(project);
    const profile = csv?.profile;
    $("dataProfile").hidden = !profile;
    $("dataProfile").replaceChildren();
    if (profile) {
      $("dataProfile").append(node("h3", "Observed in your CSV"));
      const grid = node("div", null, "profile-grid");
      const stats = [["Rows", profile.rows], ["Columns", list(profile.columns).length], ["Missing cells", profile.missing_cells]];
      stats.filter(([, value]) => typeof value === "number").forEach(([label, value]) => {
        const stat = node("div", null, "profile-stat"); stat.append(node("span", label), node("strong", value.toLocaleString())); grid.append(stat);
      });
      $("dataProfile").append(grid);
      $("dataProfile").append(node("p", "Possible binary targets: " + (list(profile.target_candidates).join(", ") || "none identified") + ". Confirm the intended outcome in your study brief.", "profile-columns"));
    }
  }

  function runId(run) { return run.job_id || run.id; }

  function renderRuns(project) {
    const runs = list(project.runs);
    state.activeJob = list(project.dashboard?.active_job_ids)[0] || [...runs].reverse().find(run => run.status && !terminal(run.status) && run.status !== "unavailable")?.job_id || null;
    $("runIndicator").hidden = !state.activeJob;
    $("runList").replaceChildren();
    [...runs].reverse().forEach((run, index) => {
      const button = node("button", null, "run-item"); button.type = "button";
      button.setAttribute("aria-current", String(runId(run) === state.selectedJob));
      button.append(node("strong", `Run ${runs.length - index} · ${shortId(runId(run))}`));
      button.append(node("span", terminal(run.status) ? String(run.verdict || run.status).replaceAll("_", " ") : run.status === "unavailable" ? "Unavailable" : "In progress"));
      button.addEventListener("click", () => selectJob(runId(run), true));
      $("runList").append(button);
    });
    const ready = project.plan?.status;
    const latestRun = runs.at(-1);
    const savedState = project.brief && latestRun?.revision_id === project.brief.id && terminal(latestRun.status) ? latestRun.evidence_verified ? latestRun.measured ? "Evidence saved" : "Assessment saved" : "Saved result needs review" : "";
    text("investigationState", state.activeJob ? "Running" : project.brief_dirty || state.briefDirty ? "Review changes" : savedState || (ready === "ready" ? "Plan ready" : ready === "unsupported" ? "Scope gap" : ready === "needs_information" ? "Needs information" : runs.length ? "Evidence saved" : list(project.materials).length ? "Frame your study" : "Attach materials"));
    $("investigationState").dataset.state = state.activeJob ? "running" : ready || "draft";
    $("resultsEmpty").hidden = Boolean(state.selectedJob);
    $("runOutput").hidden = !state.selectedJob;
    if (!runs.length) $("runList").append(node("p", "A reviewed plan starts your first run.", "small-muted"));
    renderComposerContext(project);
  }

  function renderComposerContext(project) {
    const latest = list(project.runs).at(-1);
    if (!latest) {
      text("composerContext", "Follow-ups use this investigation’s question, materials and study brief.");
      $("composerContext").dataset.older = "false";
      return;
    }
    const latestId = runId(latest);
    const older = Boolean(state.selectedJob && state.selectedJob !== latestId);
    let explanation = older
      ? `Viewing run ${shortId(state.selectedJob)}. Follow-ups use the latest run ${shortId(latestId)}.`
      : `Follow-up context: latest run ${shortId(latestId)}.`;
    if (latest.status === "unavailable") explanation += " That run is unavailable; no result is inferred.";
    else if (latest.status && !terminal(latest.status)) explanation += " It is still running; no final finding is available.";
    text("composerContext", explanation);
    $("composerContext").dataset.older = String(older);
  }

  function receiveProject(project, {fill = false, expected = null} = {}) {
    if (!project?.id) throw new Error("The server did not return an investigation identity.");
    updateProjectList(project);
    if (expected && state.project?.id !== expected) return;
    const previousId = state.project?.id;
    const previousPython = [...list(state.project?.materials)].reverse().find(material => material.kind === "python")?.id;
    const nextPython = [...list(project.materials)].reverse().find(material => material.kind === "python")?.id;
    state.project = project;
    if (previousPython !== nextPython) $("trustCode").checked = false;
    if (state.reviewedPlanId && project.plan?.id !== state.reviewedPlanId && $("runDialog").open) {
      $("runDialog").close(); state.reviewedPlanId = null;
      notice("The investigation plan changed. Review the current plan before starting a run.");
    }
    const materialKey = list(project.materials).map(material => material.sha256).join(":");
    const outboundKey = project.outbound_preview?.context_sha256 || materialKey + ":" + (project.brief?.id || "");
    if (outboundKey !== state.outboundKey || previousId !== project.id) {
      $("intakeConsent").checked = false;
      $("runConsent").checked = false;
      state.intakeConsentHash = null;
      state.outboundKey = outboundKey;
    }
    state.materialKey = materialKey;
    $("startView").hidden = true;
    $("investigationView").hidden = false;
    const displayTitle = project.title && project.title !== String(project.question || "").slice(0, 90) ? project.title : project.question || project.title;
    text("investigationTitle", displayTitle);
    $("investigationTitle").title = project.question || project.title || "";
    text("revisionLabel", project.brief ? " · REV " + shortId(project.brief.id) : "");
    renderThread(project); renderMaterials(project); renderRuns(project); renderThreadActions(project);
    if (fill || !state.briefDirty) fillBrief(project.brief || {});
    renderPlan(project); renderPending(); syncControls();
  }

  function renderThreadActions(project) {
    const container = $("threadActions");
    container.replaceChildren();
    let label, action;
    if (state.activeJob) {
      label = "Follow the active run ↗";
      action = () => selectJob(state.activeJob, true);
    } else if (list(project.runs).length) {
      label = "Inspect the latest evidence ↗";
      action = () => selectJob(runId(project.runs.at(-1)), true);
    } else if (project.plan?.status === "ready" && !project.brief_dirty && !state.briefDirty) {
      label = "Review your investigation plan ↗";
      action = () => { setView("brief"); $("planCard").scrollIntoView({block: "nearest"}); };
    } else if (latestCsv(project)) {
      label = "Review your study brief ↗";
      action = () => setView("brief", true);
    } else return;
    const button = node("button", label, "text-button");
    button.type = "button";
    button.addEventListener("click", action);
    container.append(button);
    if (list(project.brief_suggestions).length && latestCsv(project)) {
      const review = node("button", "Review suggested brief details ↗", "text-button");
      review.type = "button";
      review.addEventListener("click", () => { setView("brief"); $("briefSuggestions").scrollIntoView({block: "nearest"}); });
      container.append(review);
    }
  }

  function normalizedResult(job) {
    const result = job.result || {events: [], limitations: []};
    if (terminal(job.status) && result.status !== job.status) return {
      ...result, status: job.status, verdict: "INCONCLUSIVE", summary: null, record: null,
      _checkpoint_only: true,
      error: job.error || "This run stopped before finalizing its result. The saved checkpoint is not a completed measurement."
    };
    if (terminal(job.status) && job.evidence_verified !== true) return {
      ...result, status: job.status, verdict: "", summary: null, record: null, baseline: null,
      _unverified: true,
      error: job.evidence_error || "Saved input/control identity could not be verified. No numerical conclusion or verified export is supplied."
    };
    return {...result, status: job.status || result.status};
  }

  function renderJob(job) {
    const result = normalizedResult(job);
    const finished = terminal(job.status);
    const summary = finished ? result.summary : null;
    const baseline = result.baseline;
    const link = list(state.project?.runs).find(run => runId(run) === job.id);
    const requestedMode = link?.requested_mode || (typeof job.live === "boolean" ? job.live ? "live" : "rules" : result.mode || "unknown");
    const requestedCritic = link?.requested_critic ?? job.critic;
    const ledger = result.ledger || {};
    const modeLabel = requestedMode === "live" ? "META" + (requestedCritic ? " + INDEPENDENT REVIEW" : "") : requestedMode === "rules" ? "LOCAL RULES" : "MODE NOT RECORDED";
    text("selectedRunMeta", `${shortId(job.id)} · ${modeLabel} · ${job.status}${link?.revision_id ? " · REV " + shortId(link.revision_id) : ""}`);
    text("runTitle", !finished ? "Investigation in progress" : job.status === "failed" ? "The run could not finish" : job.status === "cancelled" ? "Run cancelled" : result._unverified ? "Saved evidence cannot be verified" : verdicts[result.verdict] || "Run finished");
    const questions = [...list(result.questions), ...list(result.scope_gaps)];
    const latestPhase = list(result.events).at(-1)?.phase;
    text("runExplanation", !finished
      ? (latestPhase ? `${latestPhase} is the latest recorded stage. ` : "Your run is queued. ") + "The audit is still running; no final conclusion is available."
      : result.error || (questions.length ? questions.join(" ") : summary ? "Original and controlled protocols were measured on pinned inputs. Inspect the uncertainty, tested change and objections." : result.verdict === "MODEL_NO_FLAW" ? "The baseline ran, but a model-only no-flaw assessment is not empirical clearance." : "No counterfactual was measured. Review the supported checks and open questions."));
    $("runPending").hidden = finished;
    if (!finished) {
      let pending = !baseline ? "Executing the pinned starting protocol before any control is measured."
        : requestedMode === "live" && !result.plan ? requestedCritic && !result.independent_review ? "Waiting for the independent Meta methodology review, then the control planner." : "Waiting for Meta to propose a supported control."
        : "Validating or executing the proposed control and recording the result.";
      if (job.status === "queued") pending = "Queued for local execution. No measurement or provider outcome is inferred yet.";
      const last = list(result.events).at(-1);
      const stamp = last?.time ? new Date(last.time * 1000).toLocaleTimeString(undefined, {hour: "2-digit", minute: "2-digit", second: "2-digit"}) : "";
      text("runPending", pending + (stamp ? ` Last recorded activity: ${stamp}.` : "") + " This view refreshes while the job is active; no automatic rerun is started.");
    }
    $("runMetrics").hidden = !summary && !baseline;
    $("controlMetric").hidden = !summary;
    text("baselineMetricLabel", `${summary ? "Original protocol" : "Starting protocol"} · ${summary?.metric || baseline?.metric || ""}`);
    text("runBaseline", fmt(summary?.claimed ?? baseline?.score));
    text("runControlled", fmt(summary?.controlled));
    text("runIntervals", summary
      ? "Per-seed conditional 95% intervals: " + Object.entries(summary.ci_per_seed || {}).map(([seed, interval]) => `${seed}: [${fmt(interval[0])}, ${fmt(interval[1])}]`).join(" · ") + ". " + (summary.interval_note || "")
      : baseline ? "The starting protocol completed. " + (finished ? "No controlled comparison was measured." : "The controlled measurement is not yet available.") : "");
    const inferenceLimit = list(result.limitations).find(value => typeof value === "string" && value.startsWith("Group/time control measured descriptively only"));
    $("runInferenceNote").hidden = !summary || !inferenceLimit;
    text("runInferenceNote", inferenceLimit ? "Descriptive comparison: the displayed row intervals do not account for repeated entities or time dependence. A large score change cannot remove this uncertainty limit. " + inferenceLimit : "");
    $("runEvents").replaceChildren();
    list(result.events).forEach(event => { const item = node("li"); item.append(node("strong", `${event.phase} · ${event.status || "recorded"}`), node("span", event.detail)); $("runEvents").append(item); });
    $("runQuestions").replaceChildren();
    if (questions.length) {
      $("runQuestions").append(node("h4", "Open questions & scope gaps"));
      const items = node("ul"); questions.forEach(question => items.append(node("li", contentText(question)))); $("runQuestions").append(items);
    }
    $("reviewCards").replaceChildren();
    if (!summary && result.verdict === "UNSUPPORTED" && result.independent_review?.assessment === "supported") {
      const disagreement = node("article", null, "review-card review-disagreement");
      disagreement.append(node("h4", "The recorded reviewers disagree"), node("p", "The independent review marked this concern supported; the planner returned unsupported. Both judgments remain recorded. No control was measured, and model agreement cannot replace a mechanically applicable, validated intervention."));
      $("reviewCards").append(disagreement);
    }
    [["Independent methodology review", result.independent_review], ["Planner proposal", result.plan], ["Post-measurement critic", result.critic]].forEach(([title, review]) => {
      if (!review) return;
      const card = node("article", null, "review-card");
      card.append(node("h4", title + " · " + (review.decision || review.assessment || review.verdict || "recorded").replaceAll("_", " ")), node("p", review.reason || "Review recorded"));
      if (list(review.concerns).length) { const items = node("ul"); review.concerns.forEach(concern => items.append(node("li", concern))); card.append(items); }
      $("reviewCards").append(card);
    });
    text("runLimits", list(result.limitations).join("\n\n"));
    text("runPlanHeading", summary ? "Tested control & input identity" : result.plan ? "Proposed control & input identity · unmeasured" : "Control status & input identity");
    text("runPlan", result.plan ? JSON.stringify(result.plan, null, 2) : finished ? "No control proposed. This is not scientific clearance." : "A control proposal has not been recorded yet.");
    text("runIdentity", result.evidence ? JSON.stringify(result.evidence, null, 2) : "The input identity will appear after successful intake.");
    text("runLedger", `${ledger.calls || 0} recorded provider attempts · $${Number(ledger.est_usd || 0).toFixed(3)} reserved estimate · ${finished ? "saved local run" : requestedMode === "live" ? "Meta requested; pending stages may not be recorded yet" : "local execution in progress"}`);
    $("runBundle").hidden = !finished || result._checkpoint_only || result._unverified || !result.record || !summary;
    $("runAssessment").hidden = !finished || result._checkpoint_only || result._unverified || !result.evidence || Boolean(result.record || summary);
    $("runBundle").href = `/api/jobs/${encodeURIComponent(job.id)}/bundle`;
    $("runAssessment").href = `/api/jobs/${encodeURIComponent(job.id)}/assessment`;
    text("runJson", result._checkpoint_only ? "Audit checkpoint JSON ↓" : "Result JSON ↓");
    syncControls();
  }

  function clearPoll() { if (state.timer) clearTimeout(state.timer); state.timer = null; }

  function schedulePoll(delay = 1500) {
    clearPoll();
    if (state.activeJob && state.project) state.timer = setTimeout(pollCurrent, delay);
  }

  async function pollCurrent() {
    const projectId = state.project?.id;
    const epoch = state.epoch;
    if (!projectId) return;
    try {
      const project = await api(projectPath("", projectId));
      if (state.epoch !== epoch || state.project?.id !== projectId) return;
      receiveProject(project, {expected: projectId});
      const selected = state.selectedJob;
      const jobEpoch = state.jobEpoch;
      if (selected) {
        const job = await api(`/api/jobs/${encodeURIComponent(selected)}`);
        if (state.epoch !== epoch || state.jobEpoch !== jobEpoch || state.selectedJob !== selected) return;
        state.job = job; renderJob(job);
      }
      schedulePoll();
    } catch (error) {
      if (state.epoch !== epoch) return;
      notice("Could not refresh the run: " + error.message + " The last saved view remains visible.");
      schedulePoll(4000);
    }
  }

  async function selectJob(id, changeView = false) {
    const projectId = state.project?.id;
    const epoch = state.epoch;
    const request = ++state.jobEpoch;
    state.selectedJob = id;
    state.job = null;
    renderRuns(state.project); syncControls();
    text("runTitle", "Loading saved run…"); text("runExplanation", "Reading the result belonging to this run.");
    $("runMetrics").hidden = true; $("runBundle").hidden = true; $("runAssessment").hidden = true;
    if (changeView) setView("results", true); else remember();
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (state.epoch !== epoch || state.jobEpoch !== request || state.project?.id !== projectId || state.selectedJob !== id) return;
      state.job = job; renderJob(job); schedulePoll();
    } catch (error) {
      if (state.epoch === epoch && state.jobEpoch === request) { notice(error.message); text("runTitle", "Saved run unavailable"); text("runExplanation", "No result is inferred. Refresh or select another saved run."); }
    }
  }

  async function openProject(id, options = {}) {
    saveDraft(); clearPoll(); closeDrawer(false);
    ["exampleDialog", "runDialog", "materialDialog"].forEach(dialog => $(dialog).close());
    const request = ++state.epoch;
    ++state.jobEpoch;
    try {
      const project = await api(projectPath("", id));
      if (request !== state.epoch) return;
      state.briefDirty = false; state.selectedJob = null; state.job = null; state.threadKey = "";
      receiveProject(project, {fill: true}); restoreDraft(id);
      const runs = list(project.runs);
      const selected = options.run && runs.some(run => runId(run) === options.run) ? options.run : runs.at(-1) ? runId(runs.at(-1)) : null;
      setView(options.view || "research");
      if (selected) await selectJob(selected);
      else { $("runOutput").hidden = true; $("resultsEmpty").hidden = false; }
      schedulePoll();
    } catch (error) {
      if (request === state.epoch) notice(error.message);
    }
  }

  function newProject() {
    saveDraft(); clearPoll(); ++state.epoch; ++state.jobEpoch;
    state.project = null; state.selectedJob = null; state.job = null; state.activeJob = null;
    state.briefDirty = false; state.threadKey = ""; state.materialKey = "";
    $("investigationView").hidden = true; $("startView").hidden = false;
    restoreDraft("new"); renderProjects(); closeDrawer(false); notice(""); remember(); syncControls();
    $("researchQuestion").focus();
  }

  async function uploadPending(projectId, files = [...state.pending], originKey = projectId) {
    for (const file of files) {
      const bytes = new Uint8Array(await file.arrayBuffer());
      let binary = "";
      for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768));
      const project = await api(projectPath("/materials", projectId), {filename: file.name, content_b64: btoa(binary)});
      for (const key of new Set([projectId, originKey])) {
        const draft = state.drafts.get(key);
        if (draft) state.drafts.set(key, {...draft, pending: draft.pending.filter(item => item !== file)});
      }
      if ((state.project?.id || "new") === projectId || (state.project?.id || "new") === originKey) state.pending = state.pending.filter(item => item !== file);
      if (state.project?.id === projectId) receiveProject(project, {expected: projectId});
      else updateProjectList(project);
      renderPending();
    }
  }

  async function previewMaterial(material) {
    const projectId = state.project?.id;
    if (!projectId) return;
    await busy(async () => {
      const response = await api(projectPath(`/materials/${encodeURIComponent(material.id)}`, projectId));
      if (state.project?.id !== projectId) return;
      const content = response.content ?? response.text ?? "Material content is unavailable.";
      text("materialPreviewTitle", material.filename);
      text("materialPreview", String(content).slice(0, 12000));
      text("materialPreviewNote", `${material.kind} · SHA-256 ${material.sha256}. ${String(content).length > 12000 ? "Showing the first 12,000 characters; original bytes remain preserved." : "Original material preview; no code is executed by opening it."}`);
      $("materialDialog").showModal();
    }, "Reading the selected material…");
  }

  function downloadJson(value, filename) {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2) + "\n"], {type: "application/json"}));
    const anchor = node("a"); anchor.href = url; anchor.download = filename; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  $("startForm").addEventListener("submit", event => {
    event.preventDefault();
    const question = $("researchQuestion").value.trim();
    if (!question) return notice("Write the question you want to investigate.");
    if (state.busy) return;
    const epoch = state.epoch;
    const pending = [...state.pending];
    busy(async () => {
      const project = await api("/api/investigations", {question});
      if (state.epoch === epoch) {
        ++state.jobEpoch; state.briefDirty = false;
        receiveProject(project, {fill: true}); state.pending = pending;
        setView("research"); remember();
      } else updateProjectList(project);
      await uploadPending(project.id, pending, "new");
      const draft = state.drafts.get("new");
      if (draft?.question === question) state.drafts.set("new", {...draft, question: ""});
      if (state.project?.id === project.id) {
        notice("Investigation saved. Review your materials and frame the study brief when ready.", "success");
        $("followupQuestion").focus();
      }
    }, "Creating your investigation…");
  });

  ["startAttach", "threadAttach", "materialsAttach"].forEach(id => $(id).addEventListener("click", () => $("materialInput").click()));
  $("materialInput").addEventListener("change", () => {
    for (const file of $("materialInput").files) {
      const extension = "." + file.name.split(".").at(-1).toLowerCase();
      const limit = extension === ".csv" ? 5_000_000 : 256_000;
      if (![".csv", ".py", ".txt", ".md"].includes(extension)) { notice(`${file.name}: use CSV, compatible Python, text or Markdown files.`); continue; }
      if (file.size > limit) { notice(`${file.name}: supported limit is ${extension === ".csv" ? "5 MB" : "256 KB"}.`); continue; }
      if (!state.pending.some(p => p.name === file.name && p.size === file.size && p.lastModified === file.lastModified)) state.pending.push(file);
    }
    $("materialInput").value = ""; renderPending();
    if (state.project && !state.busy) {
      const id = state.project.id;
      busy(async () => { await uploadPending(id); notice("Materials attached. Review their role and save a new brief before running.", "success"); }, "Inspecting your attached materials…");
    }
  });

  $("messageForm").addEventListener("submit", event => {
    event.preventDefault();
    const projectId = state.project?.id;
    const message = $("followupQuestion").value.trim();
    if (!projectId || state.busy) return;
    if (!message && !state.pending.length) return notice("Write a question or attach a material.");
    const live = $("useMetaIntake").checked;
    if (live && !$("intakeConsent").checked) return notice("Review what leaves this machine before asking Meta for guidance.");
    busy(async () => {
      if (state.pending.length) await uploadPending(projectId);
      if (message) {
        const body = {text: message, live, outbound_confirmed: live && $("intakeConsent").checked};
        if (live) body.context_sha256 = state.intakeConsentHash;
        const project = await api(projectPath("/messages", projectId), body);
        if (state.project?.id === projectId) { $("followupQuestion").value = ""; receiveProject(project, {expected: projectId}); }
        else updateProjectList(project);
      }
      notice("");
    }, live ? "Meta is reviewing the supplied context…" : "Reading your question and saved context…");
  });

  $("briefForm").addEventListener("submit", event => {
    event.preventDefault();
    const id = state.project?.id;
    if (!id || state.busy || state.activeJob) return;
    const body = readBrief();
    if (!body.target) return notice("Choose the outcome column from your CSV.");
    if (!body.intended_use) return notice("Describe the decision or research claim this result should support.");
    if (body.source_mode === "custom" && !body.trust_code) return notice("Review the attached Python source and confirm trusted-local execution before preparing its plan.");
    busy(async () => {
      let project = await api(projectPath("/brief", id), body);
      if (state.project?.id === id) { state.briefDirty = false; receiveProject(project, {fill: true, expected: id}); }
      project = await api(projectPath("/plan", id), {});
      receiveProject(project, {expected: id});
      if (state.project?.id === id) {
        setView("brief");
        notice(project.plan?.status === "ready" ? "The plan is ready to review. Starting a run is a separate action." : "The plan preserves open questions or scope gaps. No training has run.", "success");
        $("planCard").scrollIntoView({behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest"});
      }
    }, "Saving a reviewed brief and preparing its plan…");
  });

  $("briefForm").addEventListener("input", () => { state.briefDirty = true; updateSourceMode(); renderPlan(state.project); syncControls(); });
  $("briefForm").addEventListener("change", () => { state.briefDirty = true; updateSourceMode(); renderPlan(state.project); syncControls(); });
  $("reviewRun").addEventListener("click", () => {
    if (state.project?.plan?.status !== "ready" || state.activeJob || state.briefDirty || state.project.brief_dirty) return;
    text("runSnapshotNote", `This run uses brief ${shortId(state.project.brief.id)} and ${state.project.materials.length} attached material versions. ${state.project.plan.method || "The reviewed protocol"} will be executed; earlier results remain unchanged.`);
    state.reviewedPlanId = state.project.plan.id;
    $("runConsent").checked = false; notice(""); $("runDialog").showModal();
  });
  $("runMode").addEventListener("change", syncControls);
  $("useMetaIntake").addEventListener("change", syncControls);
  $("intakeConsent").addEventListener("change", () => {
    state.intakeConsentHash = $("intakeConsent").checked ? state.project?.outbound_preview?.context_sha256 || null : null;
  });
  $("startRun").addEventListener("click", () => {
    const id = state.project?.id;
    if (!id || state.busy || state.activeJob) return;
    const live = $("runMode").value === "live";
    if (live && !$("runConsent").checked) return notice("Review the outbound data and acknowledge it before starting Meta execution.");
    busy(async () => {
      const response = await api(projectPath("/runs", id), {live, critic: live && $("runCritic").checked, outbound_confirmed: live && $("runConsent").checked, plan_id: state.reviewedPlanId});
      const project = response.investigation || response;
      receiveProject(project, {expected: id});
      if (state.project?.id !== id) return;
      $("runDialog").close();
      const jobId = response.job?.id || list(project.runs).at(-1)?.job_id;
      if (!jobId) throw new Error("The server did not return the started job identity. Refresh this investigation before starting another run.");
      notice("Run started. Follow the recorded stages; a final conclusion appears only after it finishes.", "success");
      await selectJob(jobId, true); schedulePoll(700);
    }, "Freezing the accepted inputs and starting execution…");
  });

  $("cancelRun").addEventListener("click", () => {
    const id = state.activeJob;
    if (!id || state.busy || state.cancelRequested === id) return;
    busy(async () => {
      await api(`/api/jobs/${encodeURIComponent(id)}/cancel`, {});
      state.cancelRequested = id;
      notice("Cancellation requested for the active run. The current bounded stage may finish before cancellation takes effect.", "success");
      schedulePoll(500);
    }, "Requesting cancellation…");
  });

  $("newInvestigation").addEventListener("click", newProject);
  $("refreshProjects").addEventListener("click", () => busy(async () => { await refreshProjects(); if (state.project) await pollCurrent(); }, "Refreshing saved work…"));
  $("projectToggle").addEventListener("click", toggleDrawer);
  $("railScrim").addEventListener("click", () => closeDrawer());
  document.querySelectorAll(".desk-tabs button").forEach(button => button.addEventListener("click", () => setView(button.dataset.view, true)));
  $("openExamples").addEventListener("click", () => { closeDrawer(false); $("exampleDialog").showModal(); });
  $("loadExample").addEventListener("click", () => {
    const epoch = state.epoch;
    const selectedCase = $("exampleCase").value;
    return busy(async () => {
    let project = state.project;
    if (!project) {
      project = await api("/api/investigations", {question: "Does this semiconductor evaluation estimate performance on original production records?", title: "Semiconductor evaluation investigation"});
      if (state.epoch === epoch) { state.briefDirty = false; state.pending = []; receiveProject(project, {fill: true}); }
      else updateProjectList(project);
    }
    const id = project.id;
    project = await api(projectPath("/example", id), {case: selectedCase});
    if (state.epoch === epoch && state.project?.id === id) {
      state.briefDirty = false; receiveProject(project, {fill: true, expected: id});
      $("exampleDialog").close(); setView("materials");
      notice("Example input files copied. No recorded result or model call was loaded. Review the materials and study brief before starting a new run.", "success");
    }
    else updateProjectList(project);
    }, "Copying the selected public inputs…");
  });
  $("downloadInvestigation").addEventListener("click", () => { if (state.project) downloadJson(state.project, `nulllab-investigation-${shortId(state.project.id)}.json`); });
  $("runJson").addEventListener("click", () => { if (state.job) downloadJson(state.job, `nulllab-audit-${shortId(state.job.id)}.json`); });
  document.addEventListener("keydown", event => {
    if (!state.drawerOpen) return;
    if (event.key === "Escape") { event.preventDefault(); closeDrawer(); }
    if (event.key === "Tab") {
      const elements = [$("projectToggle"), ...$("projectRail").querySelectorAll('button:not([disabled]),a[href]')].filter(element => element.getClientRects().length);
      const index = elements.indexOf(document.activeElement);
      if (event.shiftKey && index <= 0) { event.preventDefault(); elements.at(-1)?.focus(); }
      else if (!event.shiftKey && (index === elements.length - 1 || index < 0)) { event.preventDefault(); elements[0]?.focus(); }
    }
  });
  window.addEventListener("resize", () => { if (!window.matchMedia("(max-width: 760px)").matches && state.drawerOpen) closeDrawer(false); });

  async function initialize() {
    const params = new URLSearchParams(window.location.search);
    try {
      state.config = await api("/api/workdesk/config");
      text("metaIntakeHint", state.config.live_enabled ? "Optional Meta guidance is bounded to four attempts and $0.25 reserved per investigation. It does not execute an experiment." : "Meta guidance is not enabled on this server. The local study guide and manual brief remain available without a key.");
      await refreshProjects();
      if (params.get("project")) await openProject(params.get("project"), {run: params.get("run"), view: params.get("view")});
      else if (["secom", "secom_clean"].includes(params.get("example"))) {
        $("exampleCase").value = params.get("example"); $("exampleDialog").showModal();
      }
      syncControls();
    } catch (error) {
      notice("The local workdesk could not load: " + error.message);
      state.config.live_enabled = false; syncControls();
    }
  }
  initialize();
})();
