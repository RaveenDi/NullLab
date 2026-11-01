"""Static verdict page: claim bar collapses to the controlled bar, stamp, REAL-PINNED/SYNTHETIC watermark,
Plan->Act->Verify->Recover log. Run: python -m report.render  (writes report/<case>.html + report/index.html)"""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = """body{font:15px system-ui;background:#0e1116;color:#e6e9ef;margin:0;padding:24px;max-width:900px;margin:auto}
.wm{display:inline-block;padding:3px 10px;border:2px solid;border-radius:4px;font-weight:700;letter-spacing:.08em}
.REAL{color:#3fb950}.SYNTH{color:#f0883e}.mock{color:#f0883e;font-weight:700}
.bars{display:flex;gap:60px;align-items:flex-end;height:260px;margin:24px 0;border-bottom:1px solid #444;position:relative}
.bar{width:140px;position:relative;border-radius:4px 4px 0 0}.bar b{position:absolute;top:-24px;width:100%;text-align:center}
.bar small{position:absolute;bottom:-42px;width:100%;text-align:center;color:#9aa4b2}
#claim{background:#58a6ff;animation:none}#ctrl{background:#f85149;animation:grow 1.4s ease-out both}
@keyframes grow{from{height:var(--from)}to{height:var(--to)}}
.stamp{position:absolute;right:0;top:20px;transform:rotate(-8deg);font-size:34px;font-weight:900;padding:4px 14px;border:5px solid;border-radius:6px;opacity:.9}
.FALSIFIED{color:#f85149}.SURVIVED{color:#3fb950}.INCONCLUSIVE{color:#d29922}
.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin:20px 0}.step{background:#161b22;border-radius:6px;padding:8px;font-size:13px}
.step h4{margin:0 0 6px}table{border-collapse:collapse}td,th{padding:3px 10px;border-bottom:1px solid #30363d;text-align:left}small.c{color:#9aa4b2}"""


def render_case(run: dict) -> str:
    v = run["verdict"]
    seeds = run.get("seeds", {})
    mean = lambda k: sum(s[k] for s in seeds.values()) / len(seeds) if seeds else 0
    claimed, ctrl = mean("claimed_acc"), mean("controlled_acc")
    ci = ", ".join(f"[{s['ci_lo']:+.3f}, {s['ci_hi']:+.3f}]" for s in seeds.values())
    wm_cls = "REAL" if run["provenance"] == "REAL-PINNED" else "SYNTH"
    steps = {"Plan": [], "Act": [], "Verify": [], "Recover": []}
    for e in run["log"]:
        steps[e["phase"]].append(e["msg"])
    boxes = "".join(f"<div class=step><h4>{p}</h4>{'<br>'.join(html.escape(m) for m in steps[p]) or '<small class=c>not needed</small>'}</div>"
                    for p in steps)
    mode_note = f'<span class=mock>{html.escape(run["mode"])}</span>'
    rows = "".join(f"<tr><td>{s}<td>{r['claimed_acc']:.3f}<td>{r['controlled_acc']:.3f}<td>{r['delta']:+.3f}<td>[{r['ci_lo']:+.3f}, {r['ci_hi']:+.3f}]<td>{v['per_seed'].get(s, '')}"
                   for s, r in seeds.items())
    cl = run["claim"]
    return f"""<!doctype html><meta charset=utf-8><title>NullLab verdict: {run['case']}</title><style>{CSS}</style>
<h1>NullLab <small class=c>every AI can give you an answer; this one tries to prove it wrong</small></h1>
<span class="wm {wm_cls}">{run['provenance']}</span> {mode_note}
<p><b>Claim:</b> {html.escape(cl['claim'])}</p>
<div class=bars style="--from:{claimed*260:.0f}px;--to:{ctrl*260:.0f}px">
 <div class=bar id=claim style="height:{claimed*260:.0f}px"><b>{claimed*100:.1f}%</b><small>claimed protocol</small></div>
 <div class=bar id=ctrl style="height:{ctrl*260:.0f}px"><b>{ctrl*100:.1f}%</b><small>controlled re-evaluation</small></div>
 <div class="stamp {v['verdict']}">{v['verdict']}</div></div>
<p style="margin-top:50px"><b>Why:</b> {html.escape(run['hyp']['broken_assumption'])}</p>
<div class=steps>{boxes}</div>
<table><tr><th>seed<th>claimed acc<th>controlled acc<th>delta<th>95% CI of delta<th>call</tr>{rows}</table>
<p><small class=c>Cites (verbatim): methods line "{html.escape(cl['methods_line'])}" | code line "<code>{html.escape(cl['code_line'])}</code>"<br>
Verdict rule: FALSIFIED only if the delta CI excludes 0 and delta &gt;= 0.03 on all 3 seeds (42,43,44); SURVIVED if all three CIs include 0; otherwise INCONCLUSIVE.
Prereg sha256 {run['hyp']['prereg_sha256'][:16]}. CIs: {ci}</small></p>"""


def render_all():
    out = ROOT / "report"
    links = []
    for p in sorted((ROOT / "runs").glob("*.json")):
        if p.stem in ("ablation",):
            continue
        run = json.loads(p.read_text())
        (out / f"{run['case']}.html").write_text(render_case(run), encoding="utf-8")
        links.append(f"<li><a href='{run['case']}.html'>{run['case']}</a> {run['provenance']} {run['verdict']['verdict']}")
    ab = ROOT / "runs" / "ablation.json"
    abl = ""
    if ab.exists():
        a = json.loads(ab.read_text())
        abl = (f"<h2>Ablation (3 cases, same blind inputs)</h2><table><tr><th>method<th>recall (2 leaky)<th>false alarms (1 clean)"
               f"<tr><td>B0 Deepchecks-style checklist<td>{a['B0']['recall']}<td>{a['B0']['false_alarms']}"
               f"<tr><td>B1 fixed GroupKFold<td>{a['B1']['recall']}<td>{a['B1']['false_alarms']}"
               f"<tr><td>B3 generic coder<td colspan=2>NOT RUN (UNVERIFIED)"
               f"<tr><td>NullLab [{html.escape(a['NullLab']['mode'])}]<td>{a['NullLab']['recall']}<td>{a['NullLab']['false_alarms']}</table>")
    (out / "index.html").write_text(f"<!doctype html><meta charset=utf-8><title>NullLab</title><style>{CSS}</style><h1>NullLab</h1><ul>{''.join(links)}</ul>{abl}", encoding="utf-8")
    return len(links)


if __name__ == "__main__":
    print(render_all(), "pages")
