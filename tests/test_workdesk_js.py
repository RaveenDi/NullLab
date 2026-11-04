"""Workdesk lifecycle/provenance regressions in a minimal DOM; no browser/network."""
from pathlib import Path
import shutil
import subprocess

import pytest

HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const nodes={},calls=[],timers=new Map(),projects={},jobs={};let counter=0,nextProject=0,nextMaterial=0;
const defaults={briefPopulation:'undecided',briefAvailability:'unknown',sourceMode:'generated',runMode:'rules',exampleCase:'secom'};
function el(id){if(!nodes[id])nodes[id]={id,value:defaults[id]||'',hidden:false,disabled:false,checked:false,files:[],children:[],handlers:{},dataset:{},style:{},open:false,_text:'',
 get textContent(){return this._text+this.children.map(c=>c.textContent).join(' ')},set textContent(v){this._text=String(v);this.children=[]},
 addEventListener(k,f){this.handlers[k]=f},append(...values){this.children.push(...values)},replaceChildren(...values){this._text='';this.children=[...values]},
 setAttribute(k,v){this[k]=v},removeAttribute(k){delete this[k]},querySelector(){return el('live-option')},querySelectorAll(){return this.children},
 getClientRects(){return this.hidden?[]:[{}]},focus(){document.activeElement=this},scrollIntoView(){},showModal(){this.open=true},close(){this.open=false},click(){return this.handlers.click?.({preventDefault(){}})}};return nodes[id]}
const tabs=['research','brief','results','materials'].map(name=>{const e=el('tab-'+name);e.dataset.view=name;return e});
global.document={getElementById:el,createElement:()=>el('node-'+(++counter)),querySelectorAll:()=>tabs,activeElement:el('researchQuestion'),body:el('body'),addEventListener(){}};
global.window={location:{search:''},history:{replaceState(a,b,url){window.lastUrl=url}},matchMedia:()=>({matches:false}),addEventListener(){}};
global.setTimeout=fn=>{const id=++counter;timers.set(id,fn);return id};global.clearTimeout=id=>timers.delete(id);
let liveEnabled=false,overrides=async()=>undefined;
const clone=v=>JSON.parse(JSON.stringify(v));
function makeProject(id,title='Study '+id){return{id,title,question:'Does my evaluation support this claim?',created_at:'2026-11-04T05:00:00Z',updated_at:'2026-11-04T05:00:00Z',materials:[],messages:[],brief:null,plan:null,runs:[],brief_dirty:false,outbound_preview:{context_sha256:'context-'+id}}}
function detail(p){const d=clone(p);d.dashboard={active_job_ids:d.runs.filter(r=>jobs[r.job_id]&&!['completed','failed','inconclusive','cancelled'].includes(jobs[r.job_id].status)).map(r=>r.job_id)};d.runs=d.runs.map(r=>({...r,status:jobs[r.job_id]?.status||r.status,verdict:jobs[r.job_id]?.result?.verdict}));d.suggested_source_mode=d.materials.some(m=>m.kind==='python')?'custom':'generated';return d}
function file(name,data){const bytes=Buffer.from(data);return{name,size:bytes.length,lastModified:1,arrayBuffer:async()=>bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.length),text:()=>{throw Error('File.text must not be used: it can strip BOM')}}}
function addCsv(p){p.materials.push({id:'csv-'+p.id,filename:'data.csv',kind:'csv',sha256:'csv-sha',bytes:100,profile:{rows:60,columns:['sensor','event'],target_candidates:['event'],missing_cells:0}});return p}
function addBrief(p){p.brief={id:'brief-'+p.id,target:'event',intended_use:'Screen independent components',source_mode:'generated',trust_code:false,study:{population:'independent_records',decision_time:'Before inspection',predictor_availability:'confirmed',excluded_columns:[]}};return p}
global.fetch=async(path,opts={})=>{const body=opts.body?JSON.parse(opts.body):undefined;calls.push({path,body,method:opts.method||'GET'});let data=await overrides(path,body,opts);
 if(data===undefined){
  if(path==='/api/workdesk/config')data={live_enabled:liveEnabled};
  else if(path==='/api/investigations'&&!body)data={investigations:Object.values(projects).map(detail)};
  else if(path==='/api/investigations'&&body){const p=makeProject('new-'+(++nextProject),body.title||body.question);projects[p.id]=p;data=detail(p)}
  else if(path.startsWith('/api/investigations/')){const parts=path.split('/'),p=projects[parts[3]];assert(p,'Unknown test project '+path);
   if(parts.length===4)data=detail(p);
   else if(parts[4]==='materials'&&body){const bytes=Buffer.from(body.content_b64,'base64'),kind=body.filename.endsWith('.py')?'python':body.filename.endsWith('.csv')?'csv':'notes';p.materials.push({id:'material-'+(++nextMaterial),filename:body.filename,kind,bytes:bytes.length,sha256:crypto.createHash('sha256').update(bytes).digest('hex'),profile:kind==='csv'?{rows:60,columns:['sensor','event'],target_candidates:['event']}:null,compatibility:kind==='python'?{compatible:true,reason:'Compatible adapter'}:null});p.brief_dirty=!!p.brief;p.plan=null;p.outbound_preview.context_sha256='changed-material-'+nextMaterial;data=detail(p)}
   else if(parts[4]==='messages'){p.messages.push({id:'m'+(++counter),role:'assistant',kind:body.live?'meta_guidance':'local_guidance',text:'Review the stated decision time.',references:[]});p.outbound_preview.context_sha256='changed-thread-'+counter;data=detail(p)}
   else if(parts[4]==='runs'){const j='job-'+(++counter);jobs[j]={id:j,case:'user-test',status:'queued',result:{status:'queued',verdict:'NOT_TESTED',events:[],limitations:[]}};p.runs.push({job_id:j,revision_id:p.brief.id,plan_id:p.plan.id});data={...detail(p),job:jobs[j]}}
   else if(parts[4]==='example'){addCsv(p);data=detail(p)}
   else throw Error('Unexpected project request '+path)
  }
  else if(path.startsWith('/api/jobs/')){const parts=path.split('/');data=jobs[parts[3]];assert(data,'Unknown test job '+path);if(parts[4]==='cancel')data={status:'running',cancel_requested:true}}
  else throw Error('Unexpected request '+path)
 }
 if(data?.__error)return{ok:false,json:async()=>({detail:data.__error})};
 return{ok:true,json:async()=>clone(data)};
};
const settle=()=>new Promise(setImmediate);async function drain(){for(let i=0;i<5;i++)await settle()}
function defer(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve}}
function load(){el('investigationView').hidden=true;vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'))}
async function open(id){const button=el('projectList').children.find(e=>e.dataset.projectId===id);assert(button,'Missing project '+id);await button.click();await drain()}
async function tick(){const entry=timers.entries().next().value;assert(entry,'Expected poll');timers.delete(entry[0]);await entry[1]();await drain()}
'''


def run_node(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed")
    script = HARNESS + "\n(async()=>{\n" + scenario + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
    path = Path(__file__).resolve().parents[1] / "app/static/workdesk.js"
    result = subprocess.run([node, "-e", script, str(path)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr


def test_empty_workdesk_never_starts_example_inference_or_execution():
    run_node(r'''
load();await drain();
assert.deepEqual(calls.map(c=>c.path),['/api/workdesk/config','/api/investigations']);
assert(!calls.some(c=>c.method==='POST'));assert(el('investigationView').hidden);
assert(!el('startView').hidden);assert(el('useMetaIntake').disabled);
''')


def test_late_new_investigation_response_does_not_steal_selected_view():
    run_node(r'''
projects.other=makeProject('other','A different investigation');
const pending=defer();overrides=async(path,body)=>path==='/api/investigations'&&body?pending.promise:undefined;
load();await drain();el('researchQuestion').value='The original submitted question';
el('startForm').handlers.submit({preventDefault(){}});await drain();
await open('other');const created=makeProject('created','The original submitted question');projects.created=created;pending.resolve(detail(created));await drain();
assert.equal(el('investigationTitle').textContent,'A different investigation');
assert(window.lastUrl.includes('project=other'));assert(!window.lastUrl.includes('project=created'));
''')


def test_exact_upload_bytes_reset_trust_for_changed_python_identity():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.materials.push({id:'python-old',kind:'python',filename:'train.py',sha256:'old',bytes:30,compatibility:{compatible:true}});p.brief.source_mode='custom';p.brief.trust_code=true;p.brief.python_material_id='python-old';projects.p=p;
window.location.search='?project=p';load();await drain();assert(el('trustCode').checked);
const bytes=Buffer.from('\ufeff# new pipeline\r\ndef load(path): pass\r\n');
el('materialInput').files=[file('train.py',bytes)];el('materialInput').handlers.change();await drain();
const request=calls.find(c=>c.path.endsWith('/materials')&&c.body);
assert(request);assert.equal(request.body.content,undefined);assert(Buffer.from(request.body.content_b64,'base64').equals(bytes));
assert(!el('trustCode').checked);assert.equal(el('sourceMode').value,'custom');
''')


def test_navigation_during_upload_preserves_unsent_message_and_brief_draft():
    run_node(r'''
projects.p=addBrief(addCsv(makeProject('p','Original study')));projects.other=makeProject('other','Other study');
window.location.search='?project=p';load();await drain();
const pending=defer();overrides=async(path,body)=>path==='/api/investigations/p/materials'?pending.promise:undefined;
el('materialInput').files=[file('notes.md','Author note')];el('materialInput').handlers.change();await drain();
el('followupQuestion').value='An unsent follow-up';el('briefDecisionTime').value='A carefully edited decision time';el('briefForm').handlers.input();
await open('other');projects.p.materials.push({id:'notes-new',kind:'notes',filename:'notes.md',sha256:'notes-hash',bytes:11});projects.p.brief_dirty=true;
pending.resolve(detail(projects.p));await drain();await open('p');
assert.equal(el('followupQuestion').value,'An unsent follow-up');
assert.equal(el('briefDecisionTime').value,'A carefully edited decision time');
assert.equal(el('threadPendingFiles').children.length,0);
''')


def test_running_checkpoint_never_displays_default_verdict_as_conclusion():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'active',revision_id:p.brief.id}];projects.p=p;
jobs.active={id:'active',status:'running',result:{status:'running',verdict:'NOT_TESTED',mode:'rules',baseline:{score:0.983,metric:'pr_auc'},events:[{phase:'Baseline',status:'ok',detail:'Original protocol completed'}],limitations:[]}};
window.location.search='?project=p&view=results';load();await drain();
assert.equal(el('runTitle').textContent,'Investigation in progress');assert(el('runExplanation').textContent.includes('no final conclusion'));
assert(el('runBundle').hidden&&el('runAssessment').hidden);
jobs.active={id:'active',evidence_verified:true,status:'inconclusive',result:{status:'inconclusive',verdict:'NOT_TESTED',mode:'rules',baseline:{score:0.983,metric:'pr_auc'},events:[],limitations:[],evidence:{schema:'test'}}};
await tick();assert.equal(el('runTitle').textContent,'No supported control was measured');assert(!el('runAssessment').hidden);
''')


def test_live_guidance_sends_checkbox_bound_context_and_resets_after_reply():
    run_node(r'''
liveEnabled=true;projects.p=addCsv(makeProject('p'));window.location.search='?project=p';load();await drain();
el('useMetaIntake').checked=true;el('useMetaIntake').handlers.change();el('intakeConsent').checked=true;el('intakeConsent').handlers.change();
el('followupQuestion').value='Which study facts are still missing?';el('messageForm').handlers.submit({preventDefault(){}});await drain();
const request=calls.find(c=>c.path.endsWith('/messages'));assert.equal(request.body.context_sha256,'context-p');assert(request.body.outbound_confirmed&&request.body.live);
assert(!el('intakeConsent').checked);const count=calls.filter(c=>c.path.endsWith('/messages')).length;
el('followupQuestion').value='One more question';el('messageForm').handlers.submit({preventDefault(){}});await drain();assert.equal(calls.filter(c=>c.path.endsWith('/messages')).length,count);
''')


def test_run_request_uses_reviewed_plan_identity_and_real_job_link():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.plan={id:'plan-reviewed',status:'ready',revision_id:p.brief.id,steps:['Reproduce starting protocol'],source_mode:'generated'};projects.p=p;
window.location.search='?project=p';load();await drain();el('reviewRun').click();assert(el('runDialog').open);
el('startRun').click();await drain();
const request=calls.find(c=>c.path.endsWith('/runs'));assert.equal(request.body.plan_id,'plan-reviewed');assert.equal(request.body.live,false);
assert.equal(el('runTitle').textContent,'Investigation in progress');assert(window.lastUrl.includes('run=job-'));assert(el('runBundle').hidden);
''')


def test_cancel_targets_active_job_while_older_result_is_displayed():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'old',revision_id:p.brief.id},{job_id:'active',revision_id:p.brief.id}];projects.p=p;
jobs.old={id:'old',evidence_verified:true,status:'completed',result:{status:'completed',verdict:'MODEL_NO_FLAW',events:[],limitations:[]}};
jobs.active={id:'active',status:'running',result:{status:'running',verdict:'NOT_TESTED',events:[],limitations:[]}};
window.location.search='?project=p&run=old';load();await drain();el('cancelRun').click();await drain();
assert(calls.some(c=>c.path==='/api/jobs/active/cancel'));assert(!calls.some(c=>c.path==='/api/jobs/old/cancel'));assert.equal(el('runTitle').textContent,'The model proposed no flaw');
''')


def test_followup_context_identifies_latest_run_when_viewing_older_evidence():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'old-123456',revision_id:p.brief.id},{job_id:'latest-9876',revision_id:p.brief.id}];projects.p=p;
jobs['old-123456']={id:'old-123456',evidence_verified:true,status:'completed',result:{status:'completed',verdict:'MODEL_NO_FLAW',events:[],limitations:[]}};
jobs['latest-9876']={id:'latest-9876',evidence_verified:true,status:'completed',result:{status:'completed',verdict:'NOT_TESTED',events:[],limitations:[]}};
window.location.search='?project=p&run=old-123456';load();await drain();
assert(el('composerContext').textContent.includes('Viewing run old-1234'));
assert(el('composerContext').textContent.includes('Follow-ups use the latest run latest-9'));
assert.equal(el('composerContext').dataset.older,'true');
const latest=el('runList').children.find(button=>button.textContent.includes('latest-9'));assert(latest);await latest.click();await drain();
assert.equal(el('composerContext').textContent,'Follow-up context: latest run latest-9.');
assert.equal(el('composerContext').dataset.older,'false');
''')


def test_selected_result_requires_fresh_verified_identity_and_revokes_numbers_and_exports():
    run_node(r'''
const p=addBrief(addCsv(makeProject('p')));p.runs=[{job_id:'audit',revision_id:p.brief.id}];projects.p=p;
jobs.audit={id:'audit',evidence_verified:true,status:'completed',result:{status:'completed',verdict:'INFLATED',events:[],limitations:[],baseline:{score:.9,metric:'accuracy'},summary:{claimed:.9,controlled:.5,metric:'accuracy',ci_per_seed:{}},record:{},evidence:{schema:'test'}}};
window.location.search='?project=p&run=audit';load();await drain();
assert(!el('runMetrics').hidden&&!el('runBundle').hidden);
jobs.audit.evidence_verified=false;jobs.audit.evidence_error='Saved input/control identity could not be verified.';
await open('p');
assert.equal(el('runTitle').textContent,'Saved evidence cannot be verified');
assert(el('runMetrics').hidden&&el('runBundle').hidden&&el('runAssessment').hidden);
assert(el('runExplanation').textContent.includes('could not be verified'));
assert(jobs.audit.result.summary.claimed===.9); // preserved diagnostic bytes are not a verified conclusion
delete jobs.audit.evidence_verified;await open('p');assert(el('runMetrics').hidden);
''')
