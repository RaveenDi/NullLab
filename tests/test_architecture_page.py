"""Architecture explorer behavior without browser, model or network calls."""

from pathlib import Path
import shutil
import subprocess

import pytest

HARNESS = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={},calls=[];let focused=null;
function el(id){return elements[id]??=(
 {id,dataset:{},handlers:{},children:[],style:{},disabled:false,textContent:'',
  setAttribute(k,v){this[k]=v},addEventListener(k,f){this.handlers[k]=f},
  replaceChildren(){this.children=[]},append(x){this.children.push(x)},
  focus(){focused=this.id},scrollIntoView(options){this.scrollOptions=options},
  getBoundingClientRect(){return {left:0,top:0,width:636,height:610}},
  classList:{contains(){return false}}});}
const keys=['inputs','baseline','independent','planner','guard','measurement','critique','evidence'];
const nodes=keys.map((key,i)=>{const n=el('stage-'+key);n.dataset.stage=key;
 n.classList.contains=name=>name==='arch-node-meta'&&[2,3,6].includes(i);
 n.parentElement=el('wrapper-'+key);n.parentElement.getBoundingClientRect=()=>({left:0,top:i*220,right:636,bottom:i*220+188,width:636,height:188});
 n.getBoundingClientRect=()=>({left:0,top:i*220,right:636,bottom:i*220+110,width:636,height:110});return n;});
const media={matches:false,addEventListener(k,f){this[k]=f}};
global.window={innerWidth:1200,matchMedia:()=>media,addEventListener(){}};
global.document={getElementById:el,querySelectorAll:()=>nodes,createElementNS:()=>el('path-'+Math.random()),fonts:{ready:Promise.resolve()}};
global.getComputedStyle=()=>({gridTemplateColumns:'300px 300px'});
global.fetch=(...args)=>{calls.push(args);throw Error('Architecture must not dispatch network/model calls');};
function load(){vm.runInThisContext(fs.readFileSync(process.argv[1],'utf8'));}
'''


def run_node(scenario):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node not installed")
    path = Path(__file__).resolve().parents[1] / "app/static/architecture.js"
    script = HARNESS + "\n" + scenario
    result = subprocess.run([node, "-e", script, str(path)], capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr


def test_stage_selection_keyboard_navigation_and_evidence_boundaries():
    run_node(r'''
load();assert.equal(el('architectureDetailIndex').textContent,'01 / 08');
assert(el('architecturePrevious').disabled);
nodes[3].handlers.click();assert.equal(el('architectureDetailTag').textContent,'MUSE SPARK');
assert(el('architectureArtifact').textContent.includes('move_into_fold'));
assert.equal(nodes[3]['aria-pressed'],'true');assert.equal(nodes[3].tabIndex,0);
let prevented=false;nodes[3].handlers.keydown({key:'End',preventDefault(){prevented=true}});
assert(prevented);assert(el('architectureNext').disabled);assert.equal(focused,'stage-evidence');
assert(el('architectureDetailBoundary').textContent.includes('cannot inherit old measurements'));
nodes[7].handlers.keydown({key:'Home',preventDefault(){}});
assert.equal(focused,'stage-inputs');assert(el('architecturePrevious').disabled);
assert.equal(calls.length,0);
''')


def test_motion_preference_pause_and_mobile_detail_navigation():
    run_node(r'''
media.matches=true;window.innerWidth=390;load();
assert.equal(el('architecture-content').dataset.motion,'paused');
assert(el('architectureMotion').disabled);assert.equal(el('architectureMotionLabel').textContent,'Reduced motion');
nodes[6].handlers.click();assert.equal(nodes[6].parentElement.scrollOptions.behavior,'auto');
assert(el('architectureDetailBoundary').textContent.includes('Deterministic uncertainty limits'));
media.matches=false;media.change();assert.equal(el('architecture-content').dataset.motion,'playing');
assert(!el('architectureMotion').disabled);
el('architectureMotion').handlers.click();assert.equal(el('architecture-content').dataset.motion,'paused');
nodes[3].handlers.click();assert.equal(el('architecture-content').dataset.motion,'paused');
el('architectureMotion').handlers.click();assert.equal(el('architecture-content').dataset.motion,'playing');
assert.equal(calls.length,0);
''')


def test_vertical_step_order_inline_detail_and_downward_connectors():
    run_node(r'''
load();assert(nodes[0].parentElement.children.includes(el('architectureDetail')));
nodes[0].handlers.keydown({key:'ArrowDown',preventDefault(){}});
assert.equal(focused,'stage-baseline');assert.equal(el('architectureDetailIndex').textContent,'02 / 08');
assert.equal(nodes[1]['aria-expanded'],'true');assert.equal(nodes[0]['aria-expanded'],'false');
assert(nodes[1].parentElement.children.includes(el('architectureDetail')));
el('architectureNext').handlers.click();assert.equal(focused,'stage-independent');
el('architecturePrevious').handlers.click();assert.equal(focused,'stage-baseline');
const paths=el('architectureConnections').children.filter(path=>path.class==='arch-path-base');
assert.equal(paths.length,7);
for(const path of paths){const nums=path.d.match(/[-\d.]+/g).map(Number);assert.equal(nums[0],nums[2]);assert(nums[3]>nums[1]);}
assert.equal(calls.length,0);
''')
