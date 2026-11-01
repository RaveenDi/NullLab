"""G5 guarded 2x2 factorial panel for report/index.html (data: runs_g5/). Everything shown is SYNTHETIC."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """.fx{display:flex;gap:14px;align-items:flex-end;height:230px;padding:24px 8px 0;border-bottom:2px solid var(--line);
position:relative;max-width:100%}.fx .b{flex:1;min-width:0;background:var(--blue);border-radius:6px 6px 0 0;position:relative;
transition:height 1s ease}.fx .b b{position:absolute;top:-22px;width:100%;text-align:center;font-size:13px}
.fx .b small{position:absolute;bottom:-40px;width:100%;text-align:center;color:var(--dim);font-size:12px}
.fx .b.o{background:var(--dim)}.fx .b.both{background:var(--red)}.fxwm{position:absolute;right:8px;top:4px;font-weight:800;
letter-spacing:.2em;color:var(--mock);opacity:.55;font-size:20px}.kpi{display:flex;flex-wrap:wrap;gap:10px;margin-top:50px}
.kpi div{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:8px 12px;font-size:13px;flex:1 1 200px}
.kpi b{display:block;font-size:20px}.fid{font-family:ui-monospace,monospace;font-size:12px}
.mono{font-family:ui-monospace,monospace;font-size:12px;word-break:break-all}"""


def payload():
    g5 = ROOT / "runs_g5"
    if not (g5 / "score.json").exists():
        return None
    score = json.loads((g5 / "score.json").read_text())
    prereg = [json.loads(x) for x in (g5 / "prereg_log.jsonl").read_text().splitlines() if x.strip()]
    runs = {}
    for r in (1, 2, 3):
        p = g5 / f"r{r}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        for c, lr in d["loop"].items():
            sc = score["cases"][c][f"r{r}"]
            fp = lr.get("final_plan", {})
            item = {"case": c, "repeat": r, "status": lr["status"], "loop": sc["loop"], "b3": sc["b3"],
                    "truth": score["truth"][c], "log": lr["log"], "plan_A": fp.get("A"), "plan_B": fp.get("B"),
                    "pred": fp.get("predicted_drop_pp"), "plan_sha": d["plan"][c].get("prereg_sha256"),
                    "b3_sha": d["b3"].get(c, {}).get("prereg_sha256")}
            if lr["status"] == "ok":
                item["seeds"] = {s: {"acc": v["full"]["acc"], "drop_ci": v["full"]["drop_ci"], "I": v["full"]["I"],
                                     "I_ci": v["full"]["I_ci"]} for s, v in lr["stats"].items()}
                item["fidelity"] = lr.get("fidelity")
            runs[f"{c} · r{r}"] = item
    rule = next((x for x in prereg if x["kind"] == "scoring_rule"), {})
    return {"runs": runs, "acceptance": score["acceptance"], "rule_sha": rule.get("sha256", ""),
            "rule_utc": rule.get("utc", ""), "n_prereg": len(prereg)}


JS = r"""
const G=G5DATA;const g$=id=>document.getElementById(id);
function pp(x){return (x>=0?'+':'')+(x*100).toFixed(1)}
function sg(x){return (x>=0?'+':'')+x}
function g5show(k){const r=G.runs[k];if(!r)return;const L=r.loop;let h='';
 if(r.status!=='ok'){g$('g5bars').innerHTML='<p><b class=INCONCLUSIVE>INCONCLUSIVE</b> (guard or execution still failing after one retry; never reported as FALSIFIED)</p>';}
 else{const ss=Object.keys(r.seeds);const mean=c=>ss.reduce((a,s)=>a+r.seeds[s].acc[c],0)/ss.length;
  const cf=[['orig','original claim','o'],['fix_A','fix A only',''],['fix_B','fix B only',''],['fix_both','fix both','both']];
  g$('g5bars').innerHTML='<div class=fx><span class=fxwm>SYNTHETIC</span>'+cf.map(([c,l,cl])=>
   `<div class="b ${cl}" data-h="${(mean(c)*200).toFixed(0)}" style="height:4px"><b>${(mean(c)*100).toFixed(1)}%</b><small>${l}</small></div>`).join('')+'</div>';
  requestAnimationFrame(()=>requestAnimationFrame(()=>document.querySelectorAll('#g5bars .b').forEach(b=>b.style.height=b.dataset.h+'px')));
  const v=L.sign==='+'?'FALSIFIED':(L.sign==='0'?'SURVIVED':(L.sign==='-'?'UNDERSTATED':'INCONCLUSIVE'));
  h=`<div class=kpi><div>Verdict (fix-both CI, ≥2 of 3 seeds)<b class=${v==='UNDERSTATED'?'INCONCLUSIVE':v}>${v}</b>per seed ${esc((L.per_seed||[]).join(' '))} · truth sign ${esc(r.truth.sign)}</div>
  <div>Interaction I = drop(both) − drop(A) − drop(B)<b>${sg(L.components_pp.AxB)} pp</b>${ss.map(s=>`seed ${s}: 95% CI [${pp(r.seeds[s].I_ci[0])}, ${pp(r.seeds[s].I_ci[1])}]`).join('<br>')}</div>
  <div>Fix-both drop (unpaired bootstrap)<b>${sg(L.components_pp.both)} pp</b>${ss.map(s=>`seed ${s}: [${pp(r.seeds[s].drop_ci.fix_both[0])}, ${pp(r.seeds[s].drop_ci.fix_both[1])}]`).join('<br>')}</div>
  <div>Reading only (B3: 1 call, no execution)<b>${sg(r.b3.fix_both_pp)} pp · ${esc(r.b3.verdict)}</b>top culprit ${esc(r.b3.culprit_raw)} · ${r.b3.wrong===true?'<span class=FALSIFIED>wrong vs truth</span>':(r.b3.wrong===false?'<span class=SURVIVED>right</span>':'')}</div></div>
  <h3>Patch-fidelity guard</h3><div class=fid>${Object.entries(r.fidelity||{}).map(([c,x])=>`${c}: ✓ ${esc(x)}`).join('<br>')}</div>`;}
 h+=`<p class=sub>Planner A: ${esc(r.plan_A||'')}<br>Planner B: ${esc(r.plan_B||'')}<br>Predicted drops, committed before running: ${esc(JSON.stringify(r.pred||{}))}</p>
 <p class=mono>prereg sha256 · rule ${G.rule_sha.slice(0,16)} (${G.rule_utc}) · planner ${esc((r.plan_sha||'').slice(0,16))} · B3 ${esc((r.b3_sha||'').slice(0,16))}</p>
 <h3>Plan → Act → Verify → Recover</h3><div class=log>${r.log.map(e=>`<div class=ev><b>${esc(e.phase)}</b> ${esc(e.verdict||e.status||'')}${e.violations&&e.violations.length?'<br><span class=sub>'+esc(e.violations.slice(0,2).join(' | ').slice(0,400))+'</span>':''}${e.runtime_violations&&e.runtime_violations.length?'<br><span class=sub>'+esc(e.runtime_violations[0].slice(0,300))+'</span>':''}${e.prereg_sha256?' <span class=mono>sha '+esc(e.prereg_sha256.slice(0,12))+'</span>':''}</div>`).join('')}</div>`;
 g$('g5detail').innerHTML=h;}
g$('g5sel').innerHTML=Object.keys(G.runs).map(k=>`<option>${esc(k)}</option>`).join('');
g$('g5sel').onchange=e=>g5show(e.target.value);
document.querySelectorAll('[data-g5]').forEach(b=>b.onclick=()=>{g$('g5sel').value=b.dataset.g5;g5show(b.dataset.g5)});
g$('g5sel').value='g4_assay_replicates · r1';g5show('g4_assay_replicates · r1');
"""


def section():
    """-> (html, script) or ("", "") when runs_g5/score.json is missing."""
    d = payload()
    if d is None:
        return "", ""
    a = d["acceptance"]
    ok = lambda b: "PASS" if b else "FAIL"  # noqa: E731
    rows = (f"<tr><td>(i) loop false alarms on clean runs (≤ 1/12)<td>{a['i_clean_false_alarms']}<td>{ok(a['i_pass'])}"
            f"<tr><td>(ii) loop sign right on hard runs (≥ 10/12)<td>{a['ii_hard_sign_correct']}<td>{ok(a['ii_pass'])}"
            f"<tr><td>(iii) reading-only B3 wrong on hard runs (≥ 6/12)<td>{a['iii_b3_wrong_hard']}<td>{ok(a['iii_pass'])}"
            f"<tr><td>(iv) every executed patch passes the fidelity check<td>{len(a['iv_fidelity_audit_failures'])} failures<td>{ok(a['iv_pass'])}"
            f"<tr><td>B3 false alarms on clean runs (reported only)<td>{a['b3_clean_false_alarms']}<td>")
    html = f"""<h2>Guarded 2×2 factorial (G5) <span class="wm SYNTH">SYNTHETIC</span></h2>
<p class=sub>8 synthetic cases × 3 independent live repeats. The planner (muse-spark-1.3) names two suspect steps and edits only those
functions of train.py. A deterministic guard rejects any edit that touches the model, the features, the split or the sample size
outside the declared step. The sandbox runs original / fix A / fix B / fix both on 3 seeds. {d['n_prereg']} hashed preregistration records.</p>
<div class=toolbar><label>case · repeat <select id=g5sel></select></label>
<button data-g5="g4_assay_replicates · r1">interaction</button><button data-g5="g4_freight_delay · r1">cancellation</button>
<button data-g5="clean_group_correct · r1">SURVIVED control</button><button data-g5="clean_control · r1">recover</button></div>
<div id=g5bars></div><div id=g5detail></div>
<h3>Preregistered acceptance · rule sha256 {d['rule_sha'][:16]} · overall {ok(a['PASS'])}</h3>
<table class=score><tr><th>clause<th>measured<th>result{rows}</table>"""
    return html, "<script>const G5DATA=" + json.dumps(d).replace("</", "<\\/") + ";" + JS + "</script>"
