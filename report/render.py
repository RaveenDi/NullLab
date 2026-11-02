"""Polished single-page demo + per-case verdict pages. Run: python -m report.render
Writes report/<case>.html + report/index.html (SPA, data inlined, works served or from file://).
No build step: plain HTML/CSS/JS. Mock runs are always labelled MOCK, never presented as model results."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """:root{--bg:#F2EFEA;--panel:#ffffff;--line:#E3DED6;--txt:#111111;--dim:#6B655E;
--blue:#111111;--red:#B23A0E;--green:#111111;--amber:#6B655E;--mock:#A8A096}
[data-theme=dark]{--bg:#121110;--panel:#1B1A18;--line:#2E2B28;--txt:#F3EFE9;--dim:#A39C92;
--blue:#F3EFE9;--red:#FF8A5B;--green:#F3EFE9;--amber:#A39C92;--mock:#6F685F}
*{box-sizing:border-box}body{font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
background:var(--bg);color:var(--txt);margin:0;padding:16px}
#ctrl{background:#E8501F!important}
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
document.documentElement.dataset.theme==='dark'?'light':'dark';try{{localStorage.setItem('nl-theme',document.documentElement.dataset.theme)}}catch(e){{}}">
light / dark</button></div>
<script>try{{var t=localStorage.getItem('nl-theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
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
    """Per-case verdict pages from runs/*.json (MOCK plumbing runs, labelled as such) + the demo SPA (index.html).
    The SPA is assembled by report/spa.py from report/assets/ and the data built by report/spa_data.py."""
    out = ROOT / "report"
    runs = {}
    for p in sorted((ROOT / "runs").glob("*.json")):
        if p.stem in ("ablation", "live_calls"):
            continue
        run = json.loads(p.read_text())
        runs[run["case"]] = run
        (out / f"{run['case']}.html").write_text(render_case(run), encoding="utf-8")
    from report import spa
    (out / "index.html").write_text(spa.build_page(), encoding="utf-8")
    return len(runs)


if __name__ == "__main__":
    print(render_all(), "pages")
