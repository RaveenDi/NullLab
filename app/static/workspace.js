"use strict";
(() => {
  const $ = id => document.getElementById(id), recordedOnly = Boolean(window.__NL_RECORDED);
  const terminal = s => ["completed","inconclusive","failed","cancelled"].includes(s);
  const text = (id,v) => { $(id).textContent = v == null ? "—" : String(v); };
  const pretty = v => JSON.stringify(v,null,2), fmt = v => Number.isFinite(v) ? v.toFixed(3) : "—";
  const strings = v => Array.isArray(v) ? v.filter(x => typeof x === "string" && x.trim()) : [];
  const populations = {independent_records:"New independent records",represented_entities:"More records from represented entities",unseen_entities:"Previously unseen entities",future_records:"Future records",undecided:"Not decided"};
  const labels = {INFLATED:"The tested control lowered the score",NO_EFFECT_DETECTED:"No effect detected for this control",CONTROL_SCORE_HIGHER:"The tested control increased the score",MODEL_NO_FLAW:"The model proposed no flaw",NOT_TESTED:"No supported control was tested",DISPUTED:"The interpretation is disputed",INCONCLUSIVE:"The evidence is inconclusive",UNSUPPORTED:"This concern needs a different instrument",NEEDS_INFORMATION:"More information is needed before testing"};
  let choices=[],recording=[],savedJobs=[],current=null,caseDetail=null,activeJobId=null,displayedJobId=null,timer=null,busy=true,cancelRequested=false,displayingRecording=false,viewRequest=0,detailRequest=0;
  async function api(path,body) {
    const response=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),data=await response.json();
    if(!response.ok) throw new Error(typeof data.detail==="string"?data.detail:"Request could not be completed");
    return data;
  }
  function notice(message) { text("notice",message);$("notice").hidden=!message; }
  function node(tag,content,className) { const n=document.createElement(tag);if(content!=null)n.textContent=String(content);if(className)n.className=className;return n; }
  function syncControls() {
    const blocked=recordedOnly||busy||Boolean(activeJobId);
    $("runButton").disabled=blocked||!choices.length;$("importCsv").disabled=blocked;
    $("reviseCase").disabled=blocked||!caseDetail?.generated_pipeline||caseDetail.id!==$("caseSelect").value||Boolean($("csvFile").files[0]);$("answerQuestions").disabled=blocked;
    $("cancelButton").hidden=!activeJobId;$("cancelButton").disabled=!activeJobId||cancelRequested;
    text("cancelButton",cancelRequested?"Cancellation requested":"Cancel active audit");$("activeAuditStatus").hidden=!activeJobId;
    text("activeAuditStatus",activeJobId?`Active audit ${activeJobId}. Inspecting other evidence does not change this cancellation target.`:"");
  }
  function updateStudyFields() {
    const population=$("studyPopulation").value||"undecided";
    $("entityField").hidden=!["represented_entities","unseen_entities"].includes(population)&&!$("entityColumn").value;
    $("timeField").hidden=population!=="future_records"&&!$("timeColumn").value;
    text("protocolHint",population==="undecided"?"Save what you know. The audit asks you to clarify the population before training.":["unseen_entities","future_records"].includes(population)?"This generated protocol is not supported yet. That limit is recorded before training or model calls.":population==="represented_entities"?"The random-row baseline concerns represented entities only. General group-aware uncertainty remains unsupported.":"The baseline uses stratified random-row cross-validation. Confirm decision-time availability below.");
  }
  function readStudy() { return {title:$("caseTitle").value.trim(),decision_time:$("decisionTime").value.trim(),unit_of_analysis:$("unitOfAnalysis").value.trim(),population:$("studyPopulation").value||"undecided",predictor_availability:$("predictorAvailability").value||"unknown",entity_column:$("entityColumn").value.trim(),time_column:$("timeColumn").value.trim(),excluded_columns:[...new Set($("excludedColumns").value.split(",").map(v=>v.trim()).filter(Boolean))]}; }
  function fillStudy(detail) {
    const editable=Boolean(detail.generated_pipeline),study=editable?(detail.study||{}):{};
    const fields={caseTitle:editable?(study.title||detail.title||""):"",targetColumn:editable?(detail.target||""):"",intendedUse:editable?(detail.intended_use||study.intended_use||detail.claim||""):"",decisionTime:study.decision_time||"",unitOfAnalysis:study.unit_of_analysis||"",studyPopulation:study.population||"undecided",predictorAvailability:study.predictor_availability||"unknown",entityColumn:study.entity_column||"",timeColumn:study.time_column||"",excludedColumns:strings(study.excluded_columns).join(", "),revisionReason:""};
    Object.entries(fields).forEach(([id,value])=>{$(id).value=value;});
    const columns=detail.predictor_columns||detail.predictors,lineage=detail.lineage||{},parent=lineage.parent_case_id||lineage.parent_case||lineage.parent;
    text("predictorPreview",Array.isArray(columns)?`Generated predictors (${columns.length}): ${columns.join(", ")}`:"Predictor preview becomes available after preparing a case.");
    text("caseLineage",parent?`Version of ${parent}. ${lineage.reason||"Earlier inputs and results are preserved."}`:"Original case version. Saving a revision creates another case.");
    $("revisionActions").hidden=!detail.generated_pipeline||recordedOnly;updateStudyFields();syncControls();
  }
  async function loadCaseDetail(id,view=null) {
    if(!id||recordedOnly)return;
    const request=++detailRequest;caseDetail=null;syncControls();const detail=await api(`/api/cases/${encodeURIComponent(id)}`);if(request!==detailRequest||$("caseSelect").value!==id||(view!==null&&view!==viewRequest))return;
    caseDetail=detail;text("claimText",detail.claim||"No claim supplied.");fillStudy(detail);
    if(!current)renderRoom({case:id,study:detail.study,study_review:detail.study_review});else if(current.case===id)renderRoom(current);
  }
  async function loadCases(select) {
    const previous=$("caseSelect").value,data=await api("/api/cases");choices=data.cases||[];$("caseSelect").replaceChildren();
    choices.forEach(c=>{const o=node("option",c.title||c.id);o.value=c.id;$("caseSelect").append(o);});
    const next=choices.some(c=>c.id===select)?select:choices.some(c=>c.id===previous)?previous:choices[0]?.id||"";$("caseSelect").value=next;
    const option=$("executionMode").querySelector('option[value="live"]');option.disabled=!data.live_enabled;option.textContent=data.live_enabled?"Meta planner · configured provider":"Meta planner · configure locally";
    text("claimText",choices.find(c=>c.id===next)?.claim||"No available case. Prepare a CSV or use the README examples.");
    if(next)await loadCaseDetail(next);syncControls();
  }
  function roomCard(title,body,extra=[]) {
    const card=node("article",null,"room-card");card.append(node("h4",title),node("p",body));
    if(extra.length){const list=node("ul");extra.forEach(item=>list.append(node("li",item)));card.append(list);}$("roomParticipants").append(card);
  }
  function renderRoom(r) {
    const detail=caseDetail?.id===r.case?caseDetail:{},study=r.study||r.study_review?.study||detail.study,review=r.study_review,room=r.review_room;
    text("studySummary",study?`Author declaration · ${populations[study.population]||study.population||"Population not recorded"}. Decision: ${study.decision_time||"not clarified"}. Predictor availability: ${study.predictor_availability||"not clarified"}.`:"This run has no structured study declaration. Inspect its original claim and limitations.");
    $("roomParticipants").replaceChildren();
    if(Array.isArray(room?.participants))room.participants.forEach(p=>{const kind={deterministic:"local check",model_record:"model assessment",assessment_record:"recorded assessment",recorded_proposal:"recorded proposal"}[p.kind]||"recorded contribution";roomCard(`${String(p.role||"Recorded contribution").replaceAll("_"," ")} · ${kind}${p.status?" · "+String(p.status).replaceAll("_"," "):""}`,p.summary||"Contribution recorded",strings(p.items));});
    else {
      if(review)roomCard("Study contract",review.reason||review.summary||String(review.status||review.verdict||"Review recorded").replaceAll("_"," "),[...strings(review.questions),...strings(review.scope_gaps),...strings(review.warnings)]);
      if(r.plan)roomCard("Planner proposal",r.plan.reason||"Structured proposal recorded",strings(r.plan.questions));
      if(r.independent_review)roomCard("Independent methodology review",r.independent_review.reason||"Independent review recorded",strings(r.independent_review.concerns));
      if(r.critic)roomCard("Post-measurement critic",`${r.critic.decision||"Unresolved"}: ${r.critic.reason||"No reason supplied"}`);
      if(r.baseline)roomCard("Executed evidence",`Baseline ${fmt(r.baseline.score)} ${r.baseline.metric||""}.${r.summary?` Control ${fmt(r.summary.controlled)}. Inspect the conditional intervals.`:" No counterfactual was measured."}`);
    }
    if(review?.facts?.rows){const f=review.facts;roomCard("Dataset profile · aggregate checks",`${f.rows} rows · ${f.predictor_count} selected predictors · positive prevalence ${fmt(f.positive_prevalence)}. ${f.missing_predictor_cells||0} missing predictor cells; ${f.duplicate_predictor_rows||0} repeated predictor rows.`,[`Selected: ${strings(review.predictor_columns).join(", ")}`,`Excluded metadata and columns: ${strings(review.excluded_columns).join(", ")||"none"}`,"These diagnostics do not establish predictor availability or independent records."]);}
    const questions=[...new Set([...strings(r.questions),...strings(review?.questions),...strings(room?.open_questions),...strings(r.scope_gaps),...strings(review?.scope_gaps),...strings(room?.scope_gaps),...strings(r.unresolved_concerns)])];
    $("openQuestions").replaceChildren();questions.forEach(q=>$("openQuestions").append(node("li",q)));$("openQuestionsBlock").hidden=!questions.length;
    $("answerQuestions").hidden=recordedOnly||!questions.length||!detail.generated_pipeline;syncControls();
  }
  function render(r,recorded=false) {
    current=r;displayingRecording=recorded;$("emptyState").hidden=true;$("auditOutput").hidden=false;
    text("resultCase",r.case);text("resultTitle",labels[r.verdict]||"Audit in progress");text("modeBadge",recorded?"RECORDED · no new execution":`${(r.mode||"rules").toUpperCase()} · ${r.status}`);
    const next=[...strings(r.questions),...strings(r.scope_gaps)];
    text("resultExplanation",r.error||(next.length?next.join(" ")+" No counterfactual was measured.":r.verdict==="MODEL_NO_FLAW"?"The baseline ran. A model-only assessment is not a measured clearance.":r.summary?"Original and controlled evaluations use pinned inputs. Inspect the control and uncertainty below.":(r.plan?.reason||"The outcome reflects the supported checks and available evidence.")+" No counterfactual was measured."));
    const s=r.summary;$("measurement").hidden=!s;$("baselineOnly").hidden=!r.baseline||Boolean(s);
    if(r.baseline&&!s){text("baselineScore",`${fmt(r.baseline.score)} ${r.baseline.metric||""}`);const seeds=Object.entries(r.baseline.per_seed_scores||{}).map(([seed,score])=>`${seed}: ${fmt(score)}`).join(" · ");text("baselineDetail","Executed starting protocol only. No counterfactual or empirical clearance. "+(seeds?`Seed scores ${seeds}. `:"")+(r.baseline.reference_note||""));}
    if(s){text("metricName",s.metric==="pr_auc"?"AVERAGE PRECISION / PR-AUC":s.metric.toUpperCase());text("deltaValue","Change "+(s.inflation>=0?"+":"")+fmt(s.inflation));text("claimedScore",fmt(s.claimed));text("controlledScore",fmt(s.controlled));$("claimedBar").setAttribute("width",String(Math.max(0,Math.min(1,s.claimed))*600));$("controlledBar").setAttribute("width",String(Math.max(0,Math.min(1,s.controlled))*600));text("seedEvidence","Per-seed 95% conditional intervals: "+Object.entries(s.ci_per_seed||{}).map(([seed,ci])=>`${seed}: [${fmt(ci[0])}, ${fmt(ci[1])}]`).join(" · ")+". "+(s.interval_note||""));}
    text("planDetails",r.plan?pretty(r.plan):"No control proposed. This is not an all-clear.");$("events").replaceChildren();(r.events||[]).forEach(e=>$("events").append(node("li",`${e.phase} · ${e.status}: ${e.detail}`)));
    const population=s&&r.input&&s.positive_prevalence!==r.input.positive_prevalence?`Scored prevalence ${fmt(s.positive_prevalence)}; supplied records ${fmt(r.input.positive_prevalence)}. A changed evaluation population makes this a protocol comparison, not an isolated causal amount of leakage.`:"";
    text("limitations",[...(r.limitations||[]),population].filter(Boolean).join("\n\n"));text("provenance",r.evidence?pretty(r.evidence):"No audited input manifest available.");text("ledger",`${r.ledger?.calls||0} model attempts · $${Number(r.ledger?.est_usd||0).toFixed(3)} reserved estimate · ${recorded?"recorded evidence":"local job"}`);
    $("bundleLink").hidden=recorded||r._checkpoint_only||!displayedJobId||!r.record||!terminal(r.status);if(!$("bundleLink").hidden)$("bundleLink").href=`/api/jobs/${displayedJobId}/bundle`;
    $("assessmentLink").hidden=recorded||r._checkpoint_only||!displayedJobId||!r.evidence||Boolean(r.record||r.summary)||!terminal(r.status);if(!$("assessmentLink").hidden)$("assessmentLink").href=`/api/jobs/${displayedJobId}/assessment`;
    $("cleanComparison").hidden=!recording.some(c=>c.case?.includes("clean"));const phases=(r.events||[]).map(e=>e.phase.toLowerCase());document.querySelectorAll(".pipeline li").forEach((li,i)=>li.classList.toggle("done",i===0?phases.includes("baseline"):i===1?phases.includes("hypothesis"):i===2?phases.includes("measurement"):terminal(r.status)));
    renderRoom(r);syncControls();
  }
  function rememberView(id){if(window.history?.replaceState)window.history.replaceState(null,"",`?job=${encodeURIComponent(id)}#workspace`);}
  function resultForState(state){const result=state.result||{case:state.case,status:state.status,verdict:terminal(state.status)?"INCONCLUSIVE":"",error:state.error,events:[],limitations:[],ledger:{}};return terminal(state.status)&&result.status!==state.status?{...result,status:state.status,verdict:"INCONCLUSIVE",summary:null,record:null,_checkpoint_only:true,error:state.error||"This audit stopped before finalizing its saved checkpoint. Start a new audit; this checkpoint is not a completed result."}:result;}
  async function openJob(id) {
    const request=++viewRequest,state=await api(`/api/jobs/${encodeURIComponent(id)}`);if(request!==viewRequest)return;
    if(!activeJobId&&!terminal(state.status)){activeJobId=id;cancelRequested=Boolean(state.cancel_requested);clearTimeout(timer);timer=setTimeout(poll,500);}
    if(choices.some(c=>c.id===state.case)){$("caseSelect").value=state.case;await loadCaseDetail(state.case,request);}if(request!==viewRequest)return;
    displayedJobId=id;displayingRecording=false;rememberView(id);render(resultForState(state));
  }
  async function refreshHistory(recover=false) {
    if(recordedOnly)return;const data=await api("/api/jobs?limit=30");savedJobs=data.jobs||[];$("historyList").replaceChildren();
    if(!savedJobs.length)$("historyList").append(node("li","No saved audits yet. Prepare a case and run an audit.","history-empty"));
    savedJobs.forEach(job=>{const item=node("li",null,"history-run"),button=node("button",job.title||job.case,"history-open");button.type="button";button.addEventListener("click",()=>openJob(job.id).catch(e=>notice(e.message)));item.append(button,node("span",`${job.status} · ${labels[job.verdict]||job.verdict||"No conclusion yet"} · ${job.created_at||""}`));$("historyList").append(item);});
    const completed=savedJobs.filter(j=>terminal(j.status));["compareLeft","compareRight"].forEach((id,index)=>{const previous=$(id).value;$(id).replaceChildren();completed.forEach(j=>{const o=node("option",`${j.title||j.case} · ${j.verdict||j.status} · ${j.id.slice(0,8)}`);o.value=j.id;$(id).append(o);});$(id).value=completed.some(j=>j.id===previous)?previous:completed[index]?.id||completed[0]?.id||"";});if(completed.length>1&&$("compareLeft").value===$("compareRight").value)$("compareRight").value=completed.find(j=>j.id!==$("compareLeft").value).id;$("compareRuns").disabled=completed.length<2;
    if(recover){const requested=new URLSearchParams(window.location?.search||"").get("job"),active=savedJobs.find(j=>(data.active_job_ids||[]).includes(j.id)||!terminal(j.status));if(active){activeJobId=active.id;cancelRequested=Boolean(active.cancel_requested);clearTimeout(timer);timer=setTimeout(poll,500);}const target=requested||active?.id||savedJobs[0]?.id;if(target)await openJob(target);}syncControls();
  }
  async function poll() {
    const id=activeJobId;if(!id)return;
    try{const state=await api(`/api/jobs/${id}`);if(activeJobId!==id)return;if(displayedJobId===id&&!displayingRecording)render(resultForState(state));if(terminal(state.status)){clearTimeout(timer);activeJobId=null;cancelRequested=false;syncControls();if(state.error)notice(state.error);await refreshHistory();}else timer=setTimeout(poll,1500);}
    catch(e){notice("Connection interrupted. Retrying active audit: "+e.message);if(activeJobId===id)timer=setTimeout(poll,3000);}
  }
  $("runButton").addEventListener("click",async()=>{
    if(recordedOnly||busy||activeJobId)return notice("Finish or cancel the active audit before starting another.");const request=++viewRequest;busy=true;syncControls();notice("");
    try{const live=$("executionMode").value==="live",state=await api("/api/jobs",{case:$("caseSelect").value,live,critic:live&&$("critic").checked,outbound_confirmed:$("outbound").checked});activeJobId=state.id;cancelRequested=false;if(request===viewRequest){displayedJobId=state.id;rememberView(state.id);render({case:state.case,status:"queued",mode:live?"live":"rules",verdict:"",events:[],limitations:[],ledger:{}});}timer=setTimeout(poll,500);await refreshHistory();}catch(e){notice(e.message);}finally{busy=false;syncControls();}
  });
  $("cancelButton").addEventListener("click",async()=>{if(!activeJobId||recordedOnly)return;try{await api(`/api/jobs/${activeJobId}/cancel`,{});cancelRequested=true;syncControls();notice("Cancellation requested for the active audit. Its bounded stage may still need to finish.");}catch(e){notice(e.message);}});
  $("importCsv").addEventListener("click",async()=>{
    if(recordedOnly||busy||activeJobId)return notice("Finish or cancel the active audit before importing data.");busy=true;syncControls();
    try{const file=$("csvFile").files[0];if(!file||file.size>5000000)throw new Error("Select a CSV file up to 5 MB.");const body={target:$("targetColumn").value.trim(),intended_use:$("intendedUse").value.trim(),study:readStudy()};body.csv=await file.text();const result=await api("/api/intake",body);$("csvFile").value="";await loadCases(result.case);notice(`Saved ${result.rows} rows and ${result.predictors} generated predictors. Review the brief, then run an audit.`);}catch(e){notice(e.message);}finally{busy=false;syncControls();}
  });
  $("reviseCase").addEventListener("click",async()=>{
    if(recordedOnly||busy||activeJobId||!caseDetail?.generated_pipeline||caseDetail.id!==$("caseSelect").value)return notice("Finish the active audit before saving a generated-case revision.");if($("csvFile").files[0])return notice("A new CSV is selected. Prepare a new case, or clear the file selection to revise the saved data.");busy=true;syncControls();
    try{const parent=$("caseSelect").value,body={study:readStudy(),intended_use:$("intendedUse").value.trim(),reason:$("revisionReason").value.trim()};if(displayedJobId&&current?.case===parent&&!displayingRecording)body.parent_job_id=displayedJobId;const result=await api(`/api/cases/${encodeURIComponent(parent)}/revisions`,body);await loadCases(result.case);notice("New case version saved. The earlier result remains displayed; run a fresh audit to test this revision.");}catch(e){notice(e.message);}finally{busy=false;syncControls();}
  });
  $("answerQuestions").addEventListener("click",async()=>{if(recordedOnly||busy||activeJobId||!current)return;try{$("caseSelect").value=current.case;await loadCaseDetail(current.case);$("preparePanel").open=true;$("studyContext").open=true;$("preparePanel").scrollIntoView({behavior:"smooth"});$("revisionReason").focus?.();}catch(e){notice(e.message);}});
  $("refreshHistory").addEventListener("click",()=>refreshHistory().catch(e=>notice(e.message)));
  $("compareRuns").addEventListener("click",async()=>{
    if(recordedOnly)return;const left=$("compareLeft").value,right=$("compareRight").value;if(!left||!right||left===right)return notice("Choose two different completed audits.");
    try{const data=await api(`/api/jobs/compare?left=${encodeURIComponent(left)}&right=${encodeURIComponent(right)}`),box=$("comparisonResult");box.replaceChildren();box.append(node("p",typeof data.interpretation==="string"?data.interpretation:"Descriptive record comparison only. No winner or new statistical conclusion."),node("p",data.comparable?"Recorded identity checks are satisfied. Scores remain descriptive.":"These records are not directly comparable: "+strings(data.reasons).join(" "),"room-note"));const table=node("table",null,"comparison-table"),header=node("tr");["Recorded field","First audit","Second audit"].forEach(v=>header.append(node("th",v)));table.append(header);["case","status","verdict","mode","metric","baseline_score","controlled_score"].forEach(field=>{const row=node("tr");[field.replaceAll("_"," "),data.left?.[field]??"Not recorded",data.right?.[field]??"Not recorded"].forEach(v=>row.append(node("td",v)));table.append(row);});(data.differences||[]).forEach(diff=>{const row=node("tr");[diff.field,typeof diff.left==="object"?pretty(diff.left):diff.left,typeof diff.right==="object"?pretty(diff.right):diff.right].forEach(v=>row.append(node("td",v??"Not recorded")));table.append(row);});box.append(table);}catch(e){notice(e.message);}
  });
  $("executionMode").addEventListener("change",()=>{$("liveOptions").hidden=$("executionMode").value!=="live";});$("studyPopulation").addEventListener("change",updateStudyFields);$("csvFile").addEventListener("change",syncControls);
  $("caseSelect").addEventListener("change",()=>{viewRequest++;if(recordedOnly){displayedJobId=null;const r=recording.find(c=>c.case===$("caseSelect").value);if(r)render(r,true);}else loadCaseDetail($("caseSelect").value).catch(e=>notice(e.message));});
  $("openRecording").addEventListener("click",()=>{if(!recording.length)return notice("No recording is available yet.");viewRequest++;detailRequest++;displayedJobId=null;render(recording.find(c=>c.case==="secom")||recording[0],true);$("workspace").scrollIntoView({behavior:"smooth"});});
  $("showClean").addEventListener("click",()=>{const r=recording.find(c=>c.case?.includes("clean"));if(r){viewRequest++;detailRequest++;displayedJobId=null;render(r,true);}});
  $("downloadJson").addEventListener("click",()=>{if(!current)return;const url=URL.createObjectURL(new Blob([pretty(current)],{type:"application/json"})),a=document.createElement("a");a.href=url;a.download=`nulllab-${current.case}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
  $("copyNote").addEventListener("click",async()=>{if(!current)return;try{await navigator.clipboard.writeText(`${current.case}: ${labels[current.verdict]||current.verdict}. ${current.summary?`Original ${fmt(current.summary.claimed)}, control ${fmt(current.summary.controlled)} ${current.summary.metric}.`:"No controlled effect measured."} ${[...(current.limitations||[]),...strings(current.questions),...strings(current.scope_gaps)].join(" ")}`);notice("Research note copied.");}catch{notice("Clipboard unavailable. Download the assessment or evidence JSON.");}});
  async function initialize(){if(recordedOnly){recording=window.__NL_RECORDED.cases||[];$("caseSelect").replaceChildren();recording.forEach(r=>{const o=node("option",r.case.includes("clean")?"Manufacturing · clean twin":"Manufacturing · Meta audit");o.value=r.case;$("caseSelect").append(o);});$("preparePanel").hidden=true;$("historyPanel").hidden=true;notice("Recorded public evidence. Fresh audits and revisions are available in the local author workspace.");if(recording.length)render(recording[0],true);}else{await loadCases();const demo=await api("/api/demo");recording=demo.cases||[];$("openRecording").disabled=!recording.length;await refreshHistory(true);}}
  initialize().catch(e=>notice(e.message)).finally(()=>{busy=false;updateStudyFields();syncControls();});
})();
