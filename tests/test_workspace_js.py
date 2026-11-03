"""Client workflow/state checks in a minimal DOM; no browser or model calls."""

from pathlib import Path
import shutil
import subprocess

import pytest

HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes={},calls=[],timers=new Map();let timerId=0,postJobs=0,importCount=0,revisionCount=0;
function el(id){if(!nodes[id])nodes[id]={value:'',checked:false,files:[],children:[],handlers:{},hidden:false,disabled:false,classList:{toggle(){}},
 addEventListener(k,f){this.handlers[k]=f},replaceChildren(){this.children=[]},append(...items){this.children.push(...items)},
 setAttribute(k,v){this[k]=v},querySelector(){return el('live-option')},scrollIntoView(){},focus(){},click(){return this.handlers.click?.()}};return nodes[id];}
function content(n){return String(n.textContent||'')+n.children.map(content).join(' ');}
let cases=[{id:'secom',title:'Example',claim:'Original claim'}],details={secom:{id:'secom',title:'Example',claim:'Original claim',generated_pipeline:false}};
let history=[],activeIds=[],states={},overrides=()=>undefined;
const recorded={case:'secom',mode:'live',status:'completed',verdict:'DISPUTED',events:[],limitations:[]};
global.window={location:{search:''},history:{replaceState(){}}};
global.document={getElementById:el,createElement:()=>el('new-'+Math.random()),querySelectorAll:()=>[]};
global.setTimeout=fn=>{timers.set(++timerId,fn);return timerId};global.clearTimeout=id=>timers.delete(id);
global.fetch=async(path,opts={})=>{calls.push({path,opts});let data=await overrides(path,opts);
 if(data===undefined){
  if(path==='/api/cases')data={cases,live_enabled:false};
  else if(path.startsWith('/api/cases/')&&!path.endsWith('/revisions'))data=details[decodeURIComponent(path.split('/').pop())];
  else if(path==='/api/demo')data={cases:[recorded]};
  else if(path.startsWith('/api/jobs?'))data={jobs:history,active_job_ids:activeIds};
  else if(path==='/api/jobs'){postJobs++;const body=JSON.parse(opts.body),id='job-'+postJobs;states[id]={id,case:body.case,status:'running',result:{case:body.case,status:'running',mode:'rules',events:[],limitations:[]}};data={id,case:body.case,status:'queued'};}
  else if(path.endsWith('/cancel'))data={status:'running',cancel_requested:true};
  else data=states[path.split('/').pop()];
 }
 if(data===undefined)throw Error('Unexpected request '+path);
 return {ok:true,json:async()=>JSON.parse(JSON.stringify(data))};};
const settle=()=>new Promise(setImmediate);
async function tick(){const next=timers.entries().next().value;assert(next,'Expected pending poll');timers.delete(next[0]);await next[1]();await settle();}
function load(){vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));}
'''


def run_node(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed")
    path = Path(__file__).resolve().parents[1] / "app" / "static" / "workspace.js"
    script = HARNESS + "\n(async()=>{\n" + scenario + "\n})().catch(e=>{console.error(e);process.exitCode=1});"
    result = subprocess.run([node, "-e", script, str(path)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr


def test_active_job_blocks_import_and_second_run_even_after_recording():
    run_node(r'''
load();await settle();el('executionMode').value='rules';
await el('runButton').handlers.click();assert.equal(postJobs,1);
assert(el('importCsv').disabled);assert(el('runButton').disabled);
el('csvFile').files=[{size:10,text:async()=> 'a,y\n1,0'}];
await el('importCsv').handlers.click();await el('runButton').handlers.click();
assert(!calls.some(c=>c.path==='/api/intake'));assert.equal(postJobs,1);
el('openRecording').handlers.click();await tick();await el('cancelButton').handlers.click();
assert(calls.some(c=>c.path==='/api/jobs/job-1'));assert(calls.some(c=>c.path==='/api/jobs/job-1/cancel'));
assert(!calls.some(c=>c.path.includes('/null')));assert(el('assessmentLink').hidden);
''')


def test_measured_result_offers_control_bundle_instead_of_unmeasured_assessment():
    run_node(r'''
history=[{id:'measured',case:'secom',status:'completed'}];
states.measured={id:'measured',case:'secom',status:'completed',result:{case:'secom',status:'completed',verdict:'NO_EFFECT_DETECTED',evidence:{schema:'recorded-test'},record:{},summary:{metric:'accuracy',claimed:0.7,controlled:0.7,inflation:0,ci_per_seed:{}},events:[],limitations:[]}};
load();await settle();assert(!el('bundleLink').hidden);assert(el('assessmentLink').hidden);
''')


def test_history_recovers_active_audit_and_viewing_other_job_keeps_cancel_target():
    run_node(r'''
history=[{id:'saved-active',case:'secom',title:'Active',status:'running'},{id:'saved-old',case:'secom',title:'Old',status:'completed'}];activeIds=['saved-active'];
states['saved-active']={id:'saved-active',case:'secom',status:'running',result:{case:'secom',status:'running',events:[],limitations:[]}};
states['saved-old']={id:'saved-old',case:'secom',status:'completed',result:{case:'secom',status:'completed',verdict:'NOT_TESTED',evidence:{schema:'recorded-test'},events:[],limitations:[]}};
load();await settle();assert(el('runButton').disabled);assert(el('importCsv').disabled);assert(content(el('activeAuditStatus')).includes('saved-active'));
await el('historyList').children[1].children[0].handlers.click();await settle();
assert.equal(el('assessmentLink').href,'/api/jobs/saved-old/assessment');
await tick();await el('cancelButton').handlers.click();
assert(calls.some(c=>c.path==='/api/jobs/saved-active/cancel'));
assert(!calls.some(c=>c.path==='/api/jobs/saved-old/cancel'));
''')


def test_intake_sends_explicit_study_roles_and_retains_active_lock():
    run_node(r'''
overrides=(path,opts)=>{if(path==='/api/intake'){importCount++;const body=JSON.parse(opts.body);assert.equal(body.study.population,'unseen_entities');assert.equal(body.study.entity_column,'line_id');assert.deepEqual(body.study.excluded_columns,['post_test']);assert.equal(body.study.predictor_availability,'unknown');cases.push({id:'user-new',title:'My study',claim:body.intended_use});details['user-new']={id:'user-new',title:'My study',target:'event',intended_use:body.intended_use,study:body.study,predictor_columns:['sensor'],generated_pipeline:true};return {case:'user-new',rows:120,predictors:1};}};
load();await settle();el('csvFile').files=[{size:30,text:async()=> 'sensor,line_id,event\n1,0,0'}];el('targetColumn').value='event';el('intendedUse').value='New production lines';el('caseTitle').value='My study';el('studyPopulation').value='unseen_entities';el('entityColumn').value='line_id';el('excludedColumns').value='post_test, post_test';
await el('importCsv').handlers.click();assert.equal(importCount,1);assert.equal(el('caseSelect').value,'user-new');assert(content(el('predictorPreview')).includes('sensor'));assert(!el('revisionActions').hidden);
await el('runButton').handlers.click();assert(el('importCsv').disabled);assert(el('reviseCase').disabled);assert.equal(postJobs,1);
''')


def test_permalink_opens_a_result_outside_the_recent_history_without_losing_active_job():
    run_node(r'''
window.location.search='?job=older-linked';history=[{id:'active-now',case:'secom',status:'running'}];activeIds=['active-now'];
states['active-now']={id:'active-now',case:'secom',status:'running',result:{case:'secom',status:'running',events:[],limitations:[]}};
states['older-linked']={id:'older-linked',case:'secom',status:'completed',result:{case:'secom',status:'completed',verdict:'NOT_TESTED',evidence:{schema:'recorded-test'},events:[],limitations:[]}};
load();await settle();assert.equal(el('assessmentLink').href,'/api/jobs/older-linked/assessment');assert(el('runButton').disabled);
await tick();await el('cancelButton').handlers.click();assert(calls.some(c=>c.path==='/api/jobs/active-now/cancel'));
''')


def test_revision_creates_new_case_and_keeps_old_result_and_download_identity():
    run_node(r'''
cases=[{id:'user-parent',title:'Original',claim:'Screening'}];details={'user-parent':{id:'user-parent',title:'Original',target:'event',intended_use:'Screening',study:{population:'undecided',predictor_availability:'unknown'},generated_pipeline:true}};
history=[{id:'parent-job',case:'user-parent',title:'Original',status:'inconclusive',verdict:'NEEDS_INFORMATION'}];states['parent-job']={id:'parent-job',case:'user-parent',status:'inconclusive',result:{case:'user-parent',status:'inconclusive',verdict:'NEEDS_INFORMATION',evidence:{schema:'recorded-test'},questions:['When is the input available?'],events:[],limitations:[]}};
overrides=(path,opts)=>{if(path==='/api/cases/user-parent/revisions'){revisionCount++;const body=JSON.parse(opts.body);assert.equal(body.parent_job_id,'parent-job');assert.equal(body.reason,'Recorded before acceptance');assert.equal(body.study.predictor_availability,'confirmed');cases.push({id:'user-child',title:'Revised'});details['user-child']={...details['user-parent'],id:'user-child',study:body.study,lineage:{parent_case:'user-parent',reason:body.reason}};return {case:'user-child',rows:120,predictors:1};}};
load();await settle();assert.equal(el('assessmentLink').href,'/api/jobs/parent-job/assessment');el('predictorAvailability').value='confirmed';el('studyPopulation').value='independent_records';el('revisionReason').value='Recorded before acceptance';await el('reviseCase').handlers.click();
assert.equal(revisionCount,1);assert.equal(el('caseSelect').value,'user-child');assert.equal(el('assessmentLink').href,'/api/jobs/parent-job/assessment');assert(content(el('caseLineage')).includes('user-parent'));assert.equal(postJobs,0);
await el('runButton').handlers.click();const post=calls.find(c=>c.path==='/api/jobs'&&c.opts.method==='POST');assert.equal(JSON.parse(post.opts.body).case,'user-child');
''')


def test_recorded_demo_never_fetches_or_enables_mutating_controls():
    run_node(r'''
window.__NL_RECORDED={cases:[recorded]};load();await settle();assert.equal(calls.length,0);assert(el('preparePanel').hidden);assert(el('historyPanel').hidden);assert(el('runButton').disabled);assert(el('importCsv').disabled);
await el('refreshHistory').handlers.click();await el('compareRuns').handlers.click();await el('importCsv').handlers.click();await el('reviseCase').handlers.click();await el('runButton').handlers.click();assert.equal(calls.length,0);
''')


def test_room_renders_only_recorded_contributions_and_comparison_is_descriptive():
    run_node(r'''
history=[{id:'one',case:'secom',status:'completed',title:'First'},{id:'two',case:'secom',status:'completed',title:'Second'}];
states.one={id:'one',case:'secom',status:'completed',result:{case:'secom',status:'completed',verdict:'NOT_TESTED',events:[],limitations:[],baseline:{score:0.7,metric:'pr_auc'},review_room:{participants:[{role:'study_contract',kind:'deterministic',summary:'Missing declared population',items:[]}],open_questions:['Which population?']}}};states.two={...states.one,id:'two'};
overrides=path=>{if(path.startsWith('/api/jobs/compare?'))return {left:{case:'secom',baseline_score:0.7,status:'completed'},right:{case:'secom',baseline_score:0.8,status:'completed'},comparable:false,reasons:['Instrument differs'],differences:[{field:'instrument',left:'a',right:'b'}],interpretation:'Descriptive comparison; no new statistical conclusion.'};};
load();await settle();assert(!el('baselineOnly').hidden);assert(content(el('baselineScore')).includes('0.700'));assert(content(el('roomParticipants')).includes('study contract'));assert(!content(el('roomParticipants')).includes('Planner proposal'));assert(content(el('openQuestions')).includes('Which population?'));
await el('compareRuns').handlers.click();assert(content(el('comparisonResult')).includes('Instrument differs'));assert(content(el('comparisonResult')).includes('no new statistical conclusion'));assert(calls.some(c=>c.path==='/api/jobs/compare?left=one&right=two'));
''')


def test_overlapping_saved_views_keep_conclusion_and_export_on_the_same_audit():
    run_node(r'''
history=[{id:'one',case:'secom',status:'completed'},{id:'two',case:'secom',status:'inconclusive'}];
states.one={id:'one',case:'secom',status:'completed',result:{case:'secom',status:'completed',verdict:'NOT_TESTED',evidence:{schema:'test'},events:[],limitations:[]}};
states.two={id:'two',case:'secom',status:'inconclusive',result:{case:'secom',status:'inconclusive',verdict:'NEEDS_INFORMATION',evidence:{schema:'test'},events:[],limitations:[]}};
load();await settle();let release,held=false;
overrides=path=>{if(path==='/api/cases/secom'&&!held){held=true;return new Promise(resolve=>{release=()=>resolve(details.secom);});}};
const older=el('historyList').children[0].children[0].handlers.click();await settle();
await el('historyList').children[1].children[0].handlers.click();assert.equal(el('assessmentLink').href,'/api/jobs/two/assessment');
release();await older;await settle();assert(content(el('resultTitle')).includes('More information'));assert.equal(el('assessmentLink').href,'/api/jobs/two/assessment');
''')


def test_delayed_saved_view_cannot_replace_a_recording():
    run_node(r'''
history=[{id:'one',case:'secom',status:'completed'}];states.one={id:'one',case:'secom',status:'completed',result:{case:'secom',status:'completed',verdict:'NOT_TESTED',evidence:{schema:'test'},events:[],limitations:[]}};
load();await settle();let release;overrides=path=>path==='/api/cases/secom'?new Promise(resolve=>{release=()=>resolve(details.secom);}):undefined;
const pending=el('historyList').children[0].children[0].handlers.click();await settle();el('openRecording').handlers.click();release();await pending;await settle();
assert(content(el('modeBadge')).includes('RECORDED'));assert(content(el('resultTitle')).includes('disputed'));assert(el('assessmentLink').hidden);assert(el('bundleLink').hidden);
''')


def test_interrupted_saved_checkpoint_shows_terminal_state_without_export():
    run_node(r'''
history=[{id:'interrupted',case:'secom',status:'failed'}];states.interrupted={id:'interrupted',case:'secom',status:'failed',error:'Local server restarted before this audit finished.',result:{case:'secom',status:'running',verdict:'NOT_TESTED',evidence:{schema:'test'},events:[],limitations:[]}};
load();await settle();assert(content(el('modeBadge')).includes('failed'));assert(content(el('resultExplanation')).includes('restarted'));assert(el('assessmentLink').hidden);assert(el('bundleLink').hidden);assert(!el('runButton').disabled);
''')


def test_polling_a_failed_checkpoint_stops_and_preserves_restart_explanation():
    run_node(r'''
history=[{id:'interrupted',case:'secom',status:'running'}];activeIds=['interrupted'];states.interrupted={id:'interrupted',case:'secom',status:'running',result:{case:'secom',status:'running',events:[],limitations:[]}};
load();await settle();states.interrupted.status='failed';states.interrupted.error='Local server restarted before this audit finished.';await tick();
assert(content(el('modeBadge')).includes('failed'));assert(content(el('resultExplanation')).includes('restarted'));assert(el('assessmentLink').hidden);assert(el('cancelButton').hidden);
''')
