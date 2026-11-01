"""Polished single-page demo + per-case verdict pages. Run: python -m report.render
Writes report/<case>.html + report/index.html (SPA, data inlined, works served or from file://).
No build step: plain HTML/CSS/JS. Mock runs are always labelled MOCK, never presented as model results."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """:root{--bg:#0e1116;--panel:#161b22;--line:#30363d;--txt:#e6e9ef;--dim:#9aa4b2;
--blue:#58a6ff;--red:#f85149;--green:#3fb950;--amber:#d29922;--mock:#f0883e}
[data-theme=light]{--bg:#ffffff;--panel:#f3f4f6;--line:#d7dce2;--txt:#16191e;--dim:#5b6572;
--blue:#0969da;--red:#cf222e;--green:#1a7f37;--amber:#9a6700;--mock:#bc4c00}
*{box-sizing:border-box}body{font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--txt);margin:0;padding:20px}
.wrap{max-width:1020px;margin:auto}
.topbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;justify-content:space-between}
h1{font-size:22px;margin:8px 0}h2{font-size:17px;margin:26px 0 8px}.sub{color:var(--dim)}
.wm{display:inline-block;padding:3px 10px;border:2px solid;border-radius:4px;font-weight:700;letter-spacing:.08em;font-size:13px}
.REAL{color:var(--green)}.SYNTH{color:var(--mock)}
.mock{display:inline-block;background:var(--mock);color:#000;font-weight:700;border-radius:4px;
padding:2px 8px;font-size:12px;margin-left:6px}
.bars{display:flex;gap:48px;align-items:flex-end;min-height:250px;margin:26px 0 10px;
border-bottom:2px solid var(--line);position:relative;padding:30px 10px 0}
.bar{width:min(200px,34vw);border-radius:6px 6px 0 0;position:relative;transition:height 1.6s cubic-bezier(.2,.7,.2,1)}
.bar b{position:absolute;top:-26px;width:100%;text-align:center;font-size:20px}
.bar small{position:absolute;bottom:-46px;width:100%;text-align:center;color:var(--dim);font-size:12px}
#claim{background:var(--blue)}#ctrl{background:var(--red)}
.ci{text-align:center;color:var(--dim);font-size:12px;margin-top:52px}
.stamp{position:absolute;right:6px;top:6px;transform:rotate(-8deg) scale(0);font-size:clamp(24px,6vw,40px);
font-weight:900;padding:4px 14px;border:5px solid;border-radius:8px;opacity:0}
.stamp.show{animation:pop .5s ease-out 1.5s both}
@keyframes pop{from{transform:rotate(-8deg) scale(2.2);opacity:0}to{transform:rotate(-8deg) scale(1);opacity:.92}}
.FALSIFIED{color:var(--red)}.SURVIVED{color:var(--green)}.INCONCLUSIVE{color:var(--amber)}
.grid4{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:16px 0}
@media(max-width:700px){.grid4{grid-template-columns:1fr 1fr}.bars{gap:20px}}
.step{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:13px}
.step h4{margin:0 0 6px;font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--dim)}
.htree{display:grid;gap:8px}.hyp{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
.hyp.primary{border-color:var(--blue);border-width:2px}
.hyp .tag{font-size:11px;font-weight:700;color:var(--dim)}
.dir{font-weight:700}.sig{color:var(--dim);font-size:13px}
.log{border-left:3px solid var(--line);margin:8px 0 0 4px;padding-left:12px;display:grid;gap:6px}
.log .ev b{color:var(--blue)}table{border-collapse:collapse;width:100%;font-size:13px;margin-top:8px}
td,th{padding:5px 10px;border-bottom:1px solid var(--line);text-align:left}
select,button,input{font:inherit;color:var(--txt);background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:6px 10px}
button{cursor:pointer}button.go{background:var(--blue);color:#fff;border-color:transparent;font-weight:700}
.cite{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:13px;margin:8px 0}
.cite code{font-family:ui-monospace,Consolas,monospace}
.toolbar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0}
.score td:nth-child(n+2),.score th:nth-child(n+2){text-align:center}
footer{color:var(--dim);font-size:12px;margin:30px 0 10px}"""


def _seeds(run):
    return run.get("seeds", {})


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0


def _bars(run):
    seeds = _seeds(run)
    claimed = _mean([s["claimed_acc"] for s in seeds.values()])
    ctrl = _mean([s["controlled_acc"] for s in seeds.values()])
    ci = ", ".join(f"[{s['ci_lo']:+.3f}, {s['ci_hi']:+.3f}]" for s in seeds.values())
    deltas = ", ".join(f"{s['delta']:+.3f}" for s in seeds.values())
    return claimed, ctrl, ci, deltas


def _steps(run):
    steps = {"Plan": [], "Act": [], "Verify": [], "Recover": []}
    for e in run.get("log", []):
        steps[e["phase"]].append(e["msg"])
    return "".join(
        f"<div class=step><h4>{p}</h4>{'<br>'.join(html.escape(m) for m in steps[p]) or '<span class=sub>not needed</span>'}"
        f"</div>" for p in steps)


def _hyps(run):
    h = run["hyp"]
    out = []
    for x in h["hypotheses"]:
        cls = "hyp primary" if x["id"] == h["primary"] else "hyp"
        star = " ★ primary" if x["id"] == h["primary"] else ""
        out.append(
            f"<div class='{cls}'><span class=tag>{html.escape(x['id'])}{star}</span><br>{html.escape(x['text'])}"
            f"<br><span class=dir>{html.escape(x['direction'])}</span> "
            f"<span class=sig>predicted signature: {html.escape(x['predicted_signature'])}</span></div>")
    return ("".join(out)
            + f"<p class=sub>Preregistered before any run · sha256 {html.escape(h['prereg_sha256'][:16])} · "
              f"split key: {html.escape(h.get('split_key', ''))}</p>")


def _table(run):
    v = run["verdict"]
    rows = "".join(
        f"<tr><td>{s}<td>{r['claimed_acc']:.3f}<td>{r['controlled_acc']:.3f}<td>{r['delta']:+.3f}"
        f"<td>[{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]<td>{v['per_seed'].get(s, '')}"
        for s, r in _seeds(run).items())
    return (f"<table><tr><th>seed<th>claimed acc<th>controlled acc<th>delta<th>95% CI of delta<th>call</tr>{rows}</table>"
            f"<p class=sub>Verdict rule: FALSIFIED only if the delta CI excludes 0 and delta ≥ 0.03 on all 3 seeds "
            f"(42, 43, 44); SURVIVED if all three CIs include 0; otherwise INCONCLUSIVE.</p>")


def _cites(run):
    cl = run["claim"]
    mno = cl.get("methods_line_no") or (cl.get("grounding", {}).get("line_numbers", {}) or {}).get("methods_line_no")
    cno = cl.get("code_line_no") or (cl.get("grounding", {}).get("line_numbers", {}) or {}).get("code_line_no")
    return (f"<div class=cite><b>Methods line</b>{f' (line {mno})' if mno else ''}: “{html.escape(cl.get('methods_line', ''))}”</div>"
            f"<div class=cite><b>Code line</b>{f' (line {cno})' if cno else ''}: "
            f"<code>{html.escape(cl.get('code_line', ''))}</code></div>"
            f"<p class=sub>Grounding precision {cl.get('grounding', {}).get('precision', '?')} "
            f"(normalised-whitespace match at the reported line number; one live retry on mismatch).</p>")


def render_case(run: dict) -> str:
    v = run["verdict"]
    claimed, ctrl, ci, deltas = _bars(run)
    wm = "REAL" if run["provenance"] == "REAL-PINNED" else "SYNTH"
    return f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>NullLab verdict: {html.escape(run['case'])}</title><style>{CSS}</style>
<div class=wrap>
<div class=topbar><h1>NullLab</h1><button onclick="document.documentElement.dataset.theme=
document.documentElement.dataset.theme==='light'?'':'light';try{{localStorage.nlt=document.documentElement.dataset.theme}}catch(e){{}}">
dark / light</button></div>
<p class=sub>Every AI can give you an answer; this one tries to prove it wrong.</p>
<span class="wm {wm}">{run['provenance']}</span><span class=mock>{html.escape(run['mode'])}</span>
<h2>Claim</h2><p>{html.escape(run['claim']['claim'])}</p>
<div class=bars>
 <div class=bar id=claim style="height:{claimed * 260:.0f}px"><b>{claimed * 100:.1f}%</b><small>claimed protocol</small></div>
 <div class=bar id=ctrl style="height:{ctrl * 260:.0f}px"><b>{ctrl * 100:.1f}%</b><small>controlled re-evaluation</small></div>
 <div class="stamp {v['verdict']} show">{v['verdict']}</div></div>
<p class=ci>Paired delta per seed {deltas} · 95% CIs {ci}</p>
<h2>Why</h2><p>{html.escape(run['hyp']['broken_assumption'])}</p>
<h2>Hypothesis tree (preregistered)</h2><div class=htree>{_hyps(run)}</div>
<h2>Plan → Act → Verify → Recover</h2><div class=grid4>{_steps(run)}</div>
<h2>Evidence</h2>{_table(run)}
<h2>Citations (verbatim)</h2>{_cites(run)}
<p><a href="index.html">← all cases</a></p>
<footer>NullLab · {html.escape(run['case'])} · {html.escape(run['mode'])} · sandbox: restricted subprocess (not Docker)</footer>
</div>"""


def _ablation_table(ab) -> str:
    if not ab:
        return "<p class=sub>No ablation yet — run <code>python -m eval.score</code>.</p>"
    b3 = ab.get("B3", {})
    if "recall" in b3:
        b3cells = f"<td>{b3['recall']}<td>{b3['false_alarms']}"
    else:
        b3cells = f"<td colspan=2>{html.escape(b3.get('status', 'NOT RUN'))}"
    wins = ab.get("non_checklist_win", {})
    win_txt = ", ".join(f"{c} ✓" for c, w in wins.items() if w) or "none yet"
    return (f"<table class=score><tr><th>method<th>recall (leaky)<th>false alarms (clean)"
            f"<tr><td>B0 Deepchecks-style checklist<td>{ab['B0']['recall']}<td>{ab['B0']['false_alarms']}"
            f"<tr><td>B1 fixed GroupKFold<td>{ab['B1']['recall']}<td>{ab['B1']['false_alarms']}"
            f"<tr><td>B3 single-prompt (no execution){b3cells}"
            f"<tr><td>NullLab [{html.escape(ab['NullLab']['mode'])}]<td>{ab['NullLab']['recall']}<td>{ab['NullLab']['false_alarms']}</table>"
            f"<p class=sub>Non-checklist wins (baselines miss, loop falsifies): {html.escape(win_txt)}. "
            f"Grounding precision {ab.get('grounding_precision', '?')}. "
            f"Real suites: deepchecks {html.escape(str(ab.get('real_suites', {}).get('deepchecks', '?')))}; "
            f"giskard {html.escape(str(ab.get('real_suites', {}).get('giskard', '?')))}.</p>")


def render_all() -> int:
    out = ROOT / "report"
    runs = {}
    for p in sorted((ROOT / "runs").glob("*.json")):
        if p.stem in ("ablation", "live_calls"):
            continue
        run = json.loads(p.read_text())
        runs[run["case"]] = run
        (out / f"{run['case']}.html").write_text(render_case(run), encoding="utf-8")
    ab = {}
    abp = ROOT / "runs" / "ablation.json"
    if abp.exists():
        ab = json.loads(abp.read_text())
    payload = json.dumps({"runs": runs, "ablation": ab}).replace("</", "<\\/")
    from report import g5_panel
    G5_CSS = g5_panel.CSS
    g5_html, g5_js = g5_panel.section()
    g6_html, g6_js = "", ""
    links = "".join(
        f"<option value='{html.escape(c)}'>{html.escape(c)} · {r['provenance']} · {r['verdict']['verdict']}</option>"
        for c, r in runs.items())
    page = f"""<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>
<title>NullLab — adversarial falsification demo</title><style>{CSS}{G5_CSS}</style>
<div class=wrap>
<div class=topbar><h1>NullLab</h1><div class=toolbar>
<button onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='light'?'':'light';
try{{localStorage.nlt=document.documentElement.dataset.theme}}catch(e){{}}">dark / light</button>
<button class=go onclick="replay()">↻ replay the collapse</button></div></div>
<p class=sub>Every AI can give you an answer; this one tries to prove it wrong. Pick a case — watch the
claimed accuracy collapse under a controlled re-evaluation. <span class=mock>MOCK runs are labelled, never model results</span></p>
{g6_html}
<h2>Early single-case demos</h2>
<div class=toolbar><label>case <select id=sel>{links}</select></label>
<label title="Preview a runs/*.json file">upload <input type=file id=up accept=.json></label>
<a id=plink href="#">open verdict page →</a></div>
<div id=stage></div>
<h2>Hypothesis tree (preregistered)</h2><div class=htree id=tree></div>
<h2>Plan → Act → Verify → Recover</h2><div class=grid4 id=steps></div>
<h2>Evidence</h2><div id=ev></div>
<h2>Citations (verbatim)</h2><div id=cites></div>
<h2>Baselines scoreboard</h2><div id=score>{_ablation_table(ab)}</div>
{g5_html}
<footer>NullLab · plan→act→verify→recover · sandbox: restricted subprocess (not Docker) ·
<a href="https://arxiv.org/abs/2207.07048">Kapoor–Narayanan leakage taxonomy</a></footer>
</div>
<script>const DATA={payload};
const $=id=>document.getElementById(id);
function esc(s){{return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;')}}
function show(c){{const r=DATA.runs[c];if(!r)return;
 const seeds=Object.entries(r.seeds||{{}});const m=k=>seeds.length?seeds.reduce((a,[,s])=>a+s[k],0)/seeds.length:0;
 const cl=m('claimed_acc'),ct=m('controlled_acc');
 const ci=seeds.map(([s,v])=>`[${{v.ci_lo>=0?'+':''}}${{v.ci_lo.toFixed(3)}}, ${{v.ci_hi>=0?'+':''}}${{v.ci_hi.toFixed(3)}}]`).join(' ');
 const dl=seeds.map(([,v])=>`${{v.delta>=0?'+':''}}${{v.delta.toFixed(3)}}`).join(' ');
 const wm=r.provenance==='REAL-PINNED'?'REAL':'SYNTH';
 $('stage').innerHTML=`<span class="wm ${{wm}}">${{r.provenance}}</span><span class=mock>${{esc(r.mode)}}</span>
 <p><b>Claim:</b> ${{esc(r.claim.claim)}}</p>
 <div class=bars><div class=bar id=claim style="height:${{(cl*260).toFixed(0)}}px"><b>${{(cl*100).toFixed(1)}}%</b>
 <small>claimed protocol</small></div>
 <div class=bar id=ctrl style="height:${{(cl*260).toFixed(0)}}px"><b>${{(ct*100).toFixed(1)}}%</b>
 <small>controlled re-evaluation</small></div>
 <div class="stamp ${{r.verdict.verdict}}" id=stamp>${{r.verdict.verdict}}</div></div>
 <p class=ci>Paired delta per seed ${{dl}} · 95% CIs ${{ci}}</p>
 <p><b>Why:</b> ${{esc(r.hyp.broken_assumption)}}</p>`;
 requestAnimationFrame(()=>requestAnimationFrame(()=>{{
   const b=document.querySelector('#stage #ctrl');if(b)b.style.height=(ct*260).toFixed(0)+'px';
   const s=$('stamp');if(s)s.classList.add('show');}}));
 $('tree').innerHTML=r.hyp.hypotheses.map(x=>
  `<div class="${{x.id===r.hyp.primary?'hyp primary':'hyp'}}"><span class=tag>${{esc(x.id)}}${{x.id===r.hyp.primary?' ★ primary':''}}</span><br>${{esc(x.text)}}<br><span class=dir>${{esc(x.direction)}}</span> <span class=sig>predicted signature: ${{esc(x.predicted_signature)}}</span></div>`).join('')
  +`<p class=sub>Preregistered before any run · sha256 ${{esc(r.hyp.prereg_sha256.slice(0,16))}} · split key: ${{esc(r.hyp.split_key||'')}}</p>`;
 const ph=['Plan','Act','Verify','Recover'];
 $('steps').innerHTML=ph.map(p=>{{const ms=r.log.filter(e=>e.phase===p).map(e=>esc(e.msg)).join('<br>');
  return `<div class=step><h4>${{p}}</h4>${{ms||'<span class=sub>not needed</span>'}}</div>`}}).join('');
 $('ev').innerHTML=`<table><tr><th>seed<th>claimed acc<th>controlled acc<th>delta<th>95% CI<th>call</tr>${{seeds.map(([s,v])=>
  `<tr><td>${{s}}<td>${{v.claimed_acc.toFixed(3)}}<td>${{v.controlled_acc.toFixed(3)}}<td>${{v.delta>=0?'+':''}}${{v.delta.toFixed(3)}}<td>[${{v.ci_lo.toFixed(3)}}, ${{v.ci_hi.toFixed(3)}}]<td>${{r.verdict.per_seed[s]||''}}`).join('')}}</table>`;
 const g=r.claim.grounding||{{}},ln=g.line_numbers||{{}};
 $('cites').innerHTML=`<div class=cite><b>Methods line</b>${{r.claim.methods_line_no||ln.methods_line_no?' (line '+(r.claim.methods_line_no||ln.methods_line_no)+')':''}}: “${{esc(r.claim.methods_line)}}”</div>
 <div class=cite><b>Code line</b>${{r.claim.code_line_no||ln.code_line_no?' (line '+(r.claim.code_line_no||ln.code_line_no)+')':''}}: <code>${{esc(r.claim.code_line)}}</code></div>
 <p class=sub>Grounding precision ${{g.precision}} (normalised-whitespace match at the reported line number).</p>`;
 $('plink').href=c+'.html';try{{localStorage.nlc=c}}catch(e){{}}}}
function replay(){{show($('sel').value)}}
$('sel').onchange=e=>show(e.target.value);
$('up').onchange=e=>{{const f=e.target.files[0];if(!f)return;const rd=new FileReader();
 rd.onload=()=>{{try{{const r=JSON.parse(rd.result);DATA.runs['uploaded:'+f.name]=r;
  $('sel').insertAdjacentHTML('beforeend',`<option value="uploaded:${{f.name}}">uploaded:${{esc(f.name)}}</option>`);
  $('sel').value='uploaded:'+f.name;show('uploaded:'+f.name);}}catch(err){{alert('not a run JSON: '+err)}}}};
 rd.readAsText(f);}};
try{{document.documentElement.dataset.theme=localStorage.nlt||''}}catch(e){{}}
show(localStorage.nlc&&DATA.runs[localStorage.nlc]?localStorage.nlc:$('sel').value);</script>{g5_js}{g6_js}"""
    (out / "index.html").write_text(page, encoding="utf-8")
    return len(runs)


if __name__ == "__main__":
    print(render_all(), "pages")
