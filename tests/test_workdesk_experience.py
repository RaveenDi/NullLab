"""Observed researcher journey regressions; no provider calls or browser network."""
from pathlib import Path

from tests.test_site_experience import EVIDENCE, node
from tests.test_workdesk_js import run_node


def test_requested_meta_mode_is_visible_during_baseline_before_provider_ledger():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'active',revision_id:p.brief.id,requested_mode:'live',requested_critic:true}];projects.p=p;
jobs.active={id:'active',status:'running',result:{status:'running',verdict:'NOT_TESTED',mode:'rules',baseline:{score:.974,metric:'accuracy'},events:[{phase:'Baseline',status:'ok',detail:'Starting protocol completed',time:1793793412}],limitations:[],ledger:{calls:0,est_usd:0}}};
window.location.search='?project=p&run=active&view=results';load();await drain();
assert(el('selectedRunMeta').textContent.includes('META + INDEPENDENT REVIEW'));
assert(!el('selectedRunMeta').textContent.includes('RULES'));
assert(el('runPending').textContent.includes('Waiting for the independent Meta'));
assert(el('runPending').textContent.includes('Last recorded activity'));
assert(el('runLedger').textContent.includes('0 recorded provider attempts'));
assert(el('runLedger').textContent.includes('Meta requested'));
assert.equal(el('runTitle').textContent,'Investigation in progress');
''')


def test_pending_guidance_remains_visible_until_bounded_request_finishes():
    run_node(r'''
liveEnabled=true;projects.p=addCsv(makeProject('p'));window.location.search='?project=p';load();await drain();
const pending=defer();overrides=async(path,body)=>path.endsWith('/messages')?pending.promise:undefined;
el('useMetaIntake').checked=true;el('useMetaIntake').handlers.change();el('intakeConsent').checked=true;el('intakeConsent').handlers.change();
el('followupQuestion').value='Inspect this context';el('messageForm').handlers.submit({preventDefault(){}});await drain();
assert(!el('requestProgress').hidden);assert(el('requestProgress').textContent.includes('bounded provider request is pending'));
assert(el('sendMessage').disabled);assert(!calls.some(c=>c.path.endsWith('/runs')));
pending.resolve(detail(projects.p));await drain();assert(el('requestProgress').hidden);assert(!el('sendMessage').disabled);
''')


def test_citations_use_attached_filenames_only_for_validated_references():
    run_node(r'''
const p=addCsv(makeProject('p'));p.materials.push({id:'notes-123',kind:'notes',filename:'research_context.md',sha256:'n',bytes:20});
p.messages=[{id:'reply',role:'assistant',kind:'meta_guidance',text:'Repeated rigs are described in [notes-123]. Another claim cites [unknown-789].',references:['notes-123','unknown-789']}];projects.p=p;
window.location.search='?project=p';load();await drain();
assert(el('researchThread').textContent.includes('[research_context.md]'));
assert(!el('researchThread').textContent.includes('[notes-123]'));
assert(el('researchThread').textContent.includes('[unknown-789]')); // never relabel an unknown source as a trusted file
const article=el('researchThread').children[0];const references=article.children.find(child=>child.className==='message-references');
assert.equal(references.children.length,1);assert.equal(references.children[0].textContent,'research_context.md');
assert.equal(projects.p.messages[0].text,'Repeated rigs are described in [notes-123]. Another claim cites [unknown-789].');
''')


def test_grounded_suggestions_require_explicit_copy_and_do_not_confirm_trusted_code():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.materials.push({id:'py',kind:'python',filename:'pipeline.py',sha256:'py',bytes:30});
p.messages=[{id:'author-answer',role:'user',text:'Use event before inspection on new rigs.'},{id:'model-guess',role:'assistant',text:'All predictors are available.'}];
p.plan={id:'ready-plan',status:'ready',source_mode:'generated',steps:[]};
p.brief_suggestions=[
 {field:'population',value:'unseen_entities',source_id:'author-answer',quote:'new rigs',requires_author_review:true},
 {field:'entity_column',value:'device_id',source_id:'author-answer',quote:'new rigs',requires_author_review:true},
 {field:'source_mode',value:'custom',source_id:'author-answer',quote:'Use event',requires_author_review:true},
 {field:'predictor_availability',value:'confirmed',source_id:'model-guess',quote:'All predictors',requires_author_review:true},
 {field:'trust_code',value:'true',source_id:'author-answer',quote:'Use event',requires_author_review:true}];projects.p=p;
window.location.search='?project=p';load();await drain();
assert.equal(el('briefPopulation').value,'independent_records');assert.equal(el('sourceMode').value,'generated');
assert(!el('briefSuggestions').hidden);assert(!el('briefSuggestions').textContent.includes('All predictors'));
el('trustCode').checked=true;
const bulk=el('briefSuggestions').children.find(child=>child.textContent==='Copy suggestions to draft');assert(bulk);bulk.click();
assert.equal(el('briefPopulation').value,'unseen_entities');assert.equal(el('briefEntity').value,'device_id');assert.equal(el('sourceMode').value,'custom');
assert(!el('trustCode').checked);assert(el('reviewRun').disabled);assert(el('deskNotice').textContent.includes('save the brief'));
assert.equal(projects.p.brief.study.population,'independent_records');assert.equal(projects.p.brief.source_mode,'generated');
assert(!calls.some(c=>c.path.endsWith('/brief')||c.path.endsWith('/runs')));
''')


def test_static_blocked_control_displays_actionable_reason_and_prevents_dispatch():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.plan={id:'blocked-plan',status:'unsupported',source_mode:'custom',steps:['Use group-disjoint validation on device_id'],scope_gaps:['Add a compatible groups parameter'],protocol:{metric:'accuracy',seeds:[42,43,44],target:'event'},compatibility:{status:'blocked',messages:['Group control needs explicit group metadata'],rejected:[{step:'claimed_eval',reason:'needs a groups parameter'}],note:'Static AST inspection only; runtime guards are still required.'}};projects.p=p;
window.location.search='?project=p&view=brief';load();await drain();
assert(!el('planCompatibility').hidden);assert(el('planCompatibility').textContent.includes('needs a groups parameter'));
assert(el('planCompatibility').textContent.includes('Static AST inspection only'));
assert(el('planScope').textContent.includes('accuracy · seeds 42, 43, 44 · target event'));
assert(el('reviewRun').disabled&&el('startRun').disabled);el('reviewRun').click();assert(!el('runDialog').open);
assert(!calls.some(c=>c.path.endsWith('/runs')));
''')


def test_many_suggestion_quotes_stay_collapsed_and_copy_does_not_save_or_trust():
    run_node(r'''
const p=addCsv(makeProject('p'));p.messages=[{id:'author-facts',role:'user',text:'Eight explicit author facts for review.'}];
const facts={target:'event',intended_use:'Predict on unseen rigs',population:'unseen_entities',decision_time:'Before inspection',predictor_availability:'confirmed',unit_of_analysis:'One repeated reading',entity_column:'device_id',source_mode:'custom'};
p.brief_suggestions=Object.entries(facts).map(([field,value])=>({field,value,source_id:'author-facts',quote:'Eight explicit author facts for review.',requires_author_review:true}));projects.p=p;
window.location.search='?project=p&view=brief';load();await drain();
let section=el('briefSuggestions');let detail=section.children.find(child=>child.className==='suggestion-details');
assert(detail&&!detail.open);assert(detail.children[0].textContent.includes('Review 8 source quotes'));
assert.equal(detail.children.filter(child=>child.className==='brief-suggestion').length,8);
assert(!section.children.some(child=>child.className==='brief-suggestion')); // sources do not push the form down unless requested
detail.open=true;const bulk=section.children.find(child=>child.textContent==='Copy suggestions to draft');bulk.click();
section=el('briefSuggestions');detail=section.children.find(child=>child.className==='suggestion-details');
assert(detail&&!detail.open);assert.equal(el('briefPopulation').value,'unseen_entities');assert.equal(el('briefEntity').value,'device_id');
assert.equal(document.activeElement.id,'briefTarget');assert(!el('trustCode').checked);assert.equal(projects.p.brief,null);
assert(!calls.some(c=>c.path.endsWith('/brief')||c.path.endsWith('/runs')));
''')


def test_explicit_desktop_tasks_focus_content_without_losing_unsaved_research_or_brief():
    run_node(r'''
projects.p=addBrief(addCsv(makeProject('p')));window.location.search='?project=p';load();await drain();
el('followupQuestion').value='A research draft that is not yet sent';el('briefDecisionTime').value='Before the final inspection';el('briefForm').handlers.input();
for(const [view,target] of [['results','resultsTitle'],['materials','materialsTitle'],['brief','briefTarget'],['research','followupQuestion']]){
 const tab=el('tab-'+view);tab.click();assert.equal(el('investigationGrid').dataset.view,view);
 assert.equal(document.activeElement.id,target);assert.equal(tab['aria-pressed'],'true');
 assert.equal(el('followupQuestion').value,'A research draft that is not yet sent');
 assert.equal(el('briefDecisionTime').value,'Before the final inspection');
}
assert(!calls.some(c=>c.method==='POST'));
''')
    css = (Path(__file__).resolve().parents[1] / "app/static/workdesk.css").read_text(encoding="utf-8")
    # The desktop rule is deliberately scoped away from the default Research layout.
    focused = css.split("/* Explicit task tabs", 1)[1]
    assert "@media(min-width:1051px)" in focused
    assert ".investigation-grid:not([data-view=research]){grid-template-columns:minmax(0,1fr)}" in focused
    assert ".investigation-grid:not([data-view=research]) .research-column{display:none}" in focused
    assert ".investigation-grid:not([data-view=research]) .context-column{display:block;border-left:0;width:100%;min-width:0}" in focused
    assert "max-width:1000px" in focused


def test_unsupported_review_disagreement_does_not_become_a_tested_control():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'audit',revision_id:p.brief.id}];projects.p=p;
jobs.audit={id:'audit',evidence_verified:true,status:'inconclusive',result:{status:'inconclusive',verdict:'UNSUPPORTED',mode:'live',summary:null,baseline:{score:.974,metric:'accuracy'},plan:{verdict:'unsupported',reason:'Group replacement requires groups parameter'},independent_review:{assessment:'supported',reason:'Concern can be tested'},events:[],limitations:[],evidence:{schema:'test'}}};
window.location.search='?project=p&run=audit&view=results';load();await drain();
assert.equal(el('runPlanHeading').textContent,'Proposed control & input identity · unmeasured');
assert(el('reviewCards').textContent.includes('The recorded reviewers disagree'));
assert(el('reviewCards').textContent.includes('supported'));assert(el('reviewCards').textContent.includes('unsupported'));
assert(el('reviewCards').textContent.includes('No control was measured'));
assert.equal(jobs.audit.result.verdict,'UNSUPPORTED');assert(!el('runAssessment').hidden);assert(el('runBundle').hidden);
''')


def test_evidence_lab_labels_unsupported_proposal_unmeasured_and_keeps_objections():
    script = EVIDENCE.replace("status:JOB_STATUS,result:base", "status:JOB_STATUS,evidence_verified:true,result:base").replace("JOB_STATUS", "'inconclusive'") + r'''
base.status='inconclusive';base.verdict='UNSUPPORTED';base.summary=null;base.record=null;
base.plan={verdict:'unsupported',reason:'Missing groups parameter'};base.independent_review={assessment:'supported',reason:'The concern is testable'};
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
setImmediate(()=>{assert.equal(el('controlHeading').textContent,'Proposed control · unmeasured');assert(el('evidenceMetrics').hidden);assert(el('evidenceReviews').children.some(child=>child.children.some(c=>String(c.textContent).includes('The recorded reviewers disagree'))));assert.equal(base.verdict,'UNSUPPORTED');});
'''
    node(script, "evidence.js")


def test_measured_descriptive_group_result_explains_interval_limit_next_to_numbers():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'group-audit',revision_id:p.brief.id}];projects.p=p;
const caveat='Group/time control measured descriptively only: worker output lacks the group/time identity required for dependence-aware inference. Conditional row intervals do not establish calibrated inflation evidence here.';
jobs['group-audit']={id:'group-audit',evidence_verified:true,status:'inconclusive',result:{status:'inconclusive',verdict:'INCONCLUSIVE',mode:'live',summary:{claimed:.974,controlled:.290,metric:'accuracy',ci_per_seed:{42:[.5,.8]}},record:{},events:[],limitations:[caveat],evidence:{schema:'test'}}};
window.location.search='?project=p&run=group-audit&view=results';load();await drain();
assert.equal(el('runTitle').textContent,'The evidence is inconclusive');assert(!el('runInferenceNote').hidden);
assert(el('runInferenceNote').textContent.includes('do not account for repeated entities or time dependence'));
assert(el('runInferenceNote').textContent.includes(caveat));assert.equal(el('runControlled').textContent,'0.290');
jobs['group-audit'].result.limitations=[];await open('p');assert(el('runInferenceNote').hidden); // do not infer this caveat without the recorded limitation
''')


def test_saved_evidence_shows_descriptive_inference_limit_separately_from_secom_population():
    script = EVIDENCE.replace("status:JOB_STATUS,result:base", "status:JOB_STATUS,evidence_verified:true,result:base").replace("JOB_STATUS", "'inconclusive'") + r'''
base.status='inconclusive';base.verdict='INCONCLUSIVE';base.case='user-group-study';
base.limitations=['Group/time control measured descriptively only: worker output lacks the group/time identity required for dependence-aware inference. Conditional row intervals do not establish calibrated inflation evidence here.'];
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
setImmediate(()=>{assert(!el('inferenceNote').hidden);assert(el('inferenceNote').textContent.includes('do not account for repeated entities or time dependence'));assert(el('populationNote').hidden);assert(!el('evidenceMetrics').hidden);assert.equal(el('recordTitle').textContent,'The evidence is inconclusive');});
'''
    node(script, "evidence.js")


def test_default_truncated_title_uses_complete_question_but_custom_title_is_respected():
    run_node(r'''
const p=makeProject('p');p.question='Does random-row validation on repeated sensor readings estimate performance on entirely new rigs? I want to preserve the supplied model.';p.title=p.question.slice(0,90);projects.p=p;
window.location.search='?project=p';load();await drain();
assert.equal(el('investigationTitle').textContent,p.question);
p.title='Rig protocol review';await open('p');assert.equal(el('investigationTitle').textContent,'Rig protocol review');
''')


def test_returning_project_list_keeps_run_counts_from_api_projection():
    run_node(r'''
const p=makeProject('saved');p.runs=[{job_id:'done',status:'completed'}];projects.saved=p;projects.empty=makeProject('empty');
load();await drain();
const saved=el('projectList').children.find(e=>e.dataset.projectId==='saved');
const empty=el('projectList').children.find(e=>e.dataset.projectId==='empty');
assert(saved.textContent.includes('1 run'));assert(empty.textContent.includes('0 runs'));
await el('refreshProjects').click();await drain();
assert(el('projectList').children.find(e=>e.dataset.projectId==='saved').textContent.includes('1 run'));
''')
