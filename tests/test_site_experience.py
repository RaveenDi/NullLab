"""Separated landing/evidence behavior with no browser, model or real network."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def node(script, name):
    executable = shutil.which("node")
    if not executable:
        pytest.skip("Node not installed")
    result = subprocess.run([executable, "-e", script, str(ROOT / "app/static" / name)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr


def test_landing_has_three_sections_and_question_first_destination():
    html = (ROOT / "app/static/index.html").read_text(encoding="utf-8")
    assert html.count("<section ") == 3
    assert 'href="/workdesk"' in html and "Go to Workdesk" in html
    assert 'id="workspace"' not in html and "fullscreenButton" not in html
    assert 'id="evidenceField" aria-hidden="true"' in html
    assert not any(marker in html for marker in ("\u00c2", "\u00c3", "\u00e2"))


@pytest.mark.parametrize("reduced", [False, True])
def test_landing_continues_until_paused_and_respects_reduced_motion(reduced):
    node(r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const handlers={},listeners={},frames=new Map();let id=0;
const gradient={addColorStop(){}};const context=new Proxy({createRadialGradient:()=>gradient,createLinearGradient:()=>gradient},{get:(o,k)=>o[k]||(()=>{})});
const button={hidden:false,handlers,attributes:{},setAttribute(k,v){this.attributes[k]=v},addEventListener(k,f){handlers[k]=f}};
const canvas={getContext:()=>context};
global.innerWidth=1280;global.innerHeight=720;global.devicePixelRatio=1;
const preference={matches:REDUCED,addEventListener(){}};
global.window={matchMedia:()=>preference,addEventListener(){}};
global.document={hidden:false,body:{classList:{toggle(){}}},getElementById:k=>k==='evidenceField'?canvas:button,addEventListener(k,f){listeners[k]=f}};
global.performance={now:()=>0};global.requestAnimationFrame=f=>{frames.set(++id,f);return id};global.cancelAnimationFrame=i=>frames.delete(i);
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
if(preference.matches){assert.equal(frames.size,0);assert.equal(button.attributes['aria-pressed'],'true');handlers.click();}
for(let t=1000;t<=15000;t+=1000){assert.equal(frames.size,1);const [key,callback]=frames.entries().next().value;frames.delete(key);callback(t);}
handlers.click();assert.equal(frames.size,0);assert(button.textContent.includes('Play'));
handlers.click();assert.equal(frames.size,1);document.hidden=true;listeners.visibilitychange();assert.equal(frames.size,0);
'''.replace("REDUCED", str(reduced).lower()), "landing.js")


EVIDENCE = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const nodes={},calls=[];function el(id){return nodes[id]||(nodes[id]={textContent:'',hidden:false,attributes:{},handlers:{},children:[],setAttribute(k,v){this.attributes[k]=v},replaceChildren(){this.children=[]},append(...n){this.children.push(...n)},querySelector(){return el(id+'-p')},addEventListener(k,f){this.handlers[k]=f},focus(){},scrollIntoView(){},click(){}});}
global.document={getElementById:el,createElement:tag=>el(tag+Math.random())};
global.location={search:'?job=saved'};global.history={replaceState(){}};global.matchMedia=()=>({matches:true});global.window={};
const base={case:'secom',status:'completed',verdict:'INFLATED',summary:{claimed:.9,controlled:.5,inflation:.4,metric:'accuracy',ci_per_seed:{42:[.2,.5]}},baseline:{score:.9,metric:'accuracy'},record:{},evidence:{},events:[],limitations:[],plan:{reason:'Recorded control'}};
global.fetch=async path=>{calls.push(path);return {ok:true,json:async()=>path==='/api/demo'?{cases:[base]}:path.startsWith('/api/jobs?')?{jobs:[]}:{id:'saved',status:JOB_STATUS,result:base}}};
'''


def test_saved_measurement_checkpoint_during_critic_is_not_a_final_result():
    script = EVIDENCE.replace("JOB_STATUS", "'running'") + r'''
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
setImmediate(()=>{assert.equal(el('recordTitle').textContent,'Experiment in progress');assert(el('evidenceMetrics').hidden);assert(el('savedBundle').hidden);assert(el('savedAssessment').hidden);assert(el('evidenceBaseline-p').textContent.includes('still in progress'));});
'''
    node(script, "evidence.js")


def test_public_recorded_package_never_calls_a_backend_or_rewrites_history():
    script = EVIDENCE.replace("JOB_STATUS", "'completed'") + r'''
window.__NL_PUBLIC_EVIDENCE={cases:[base,{...base,case:'secom_clean',verdict:'NOT_TESTED',summary:null,record:null}]};
history.replaceState=()=>{throw Error('Static recording changed history')};
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
setImmediate(()=>{assert.equal(calls.length,0);assert(el('saved').hidden);assert(el('exampleInWorkdesk').hidden);el('showCleanRecord').handlers.click();assert.equal(el('recordTitle').textContent,'No supported control was tested');assert.equal(calls.length,0);});
'''
    node(script, "evidence.js")


@pytest.mark.parametrize("verified", [True, False])
def test_saved_evidence_headline_and_exports_require_verified_input_identity(verified):
    script = EVIDENCE.replace("JOB_STATUS", "'completed'").replace("status:'completed',result:base", f"status:'completed',evidence_verified:{str(verified).lower()},result:base") + r'''
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
setImmediate(()=>{assert.equal(el('evidenceMetrics').hidden,!VERIFIED);assert.equal(el('savedBundle').hidden,!VERIFIED);assert(el('studyContext').hidden);if(!VERIFIED)assert.equal(el('recordTitle').textContent,'Saved evidence cannot be verified');});
'''.replace("VERIFIED", str(verified).lower())
    node(script, "evidence.js")


def test_saved_audit_url_does_not_flash_unrelated_recording_while_loading():
    script = EVIDENCE.replace("JOB_STATUS", "'completed'") + r'''
const originalFetch=fetch;let release;
fetch=async path=>path==='/api/jobs/saved'?new Promise(resolve=>{release=resolve}):originalFetch(path);
vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));
setImmediate(()=>{
 assert.equal(el('recordTitle').textContent,'Loading saved audit…');
 assert(el('studyContext').hidden);assert.notEqual(el('evidenceOriginal').textContent,'0.900');
 release({ok:true,json:async()=>({id:'saved',status:'completed',evidence_verified:true,result:base})});
 setImmediate(()=>assert.equal(el('recordTitle').textContent,'The tested control lowered the score'));
});
'''
    node(script, "evidence.js")
