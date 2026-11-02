"""G6 hero panel for report/index.html (data: runs_g6/score.json, eval/g6_truth.json for the published numbers).
Watermarks are honest: the civil-war case is REAL-PINNED (published paper + published reanalysis, pinned data),
the ESL case is TEXTBOOK (not a paper reanalysis)."""
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CSS = """.g6{position:relative;overflow:hidden;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:14px 0 22px}
.g6 .row{display:flex;gap:28px;align-items:flex-end;height:210px;border-bottom:2px solid var(--line);padding:26px 6px 0;position:relative}
.g6 .col{flex:1;min-width:0;border-radius:6px 6px 0 0;position:relative;transition:height 1.4s cubic-bezier(.2,.7,.2,1)}
.g6 .col b{position:absolute;top:-24px;width:100%;text-align:center;font-size:18px}
.g6 .col small{position:absolute;bottom:-40px;width:100%;text-align:center;color:var(--dim);font-size:12px;line-height:1.2}
.g6 .c1{background:var(--blue)}.g6 .c2{background:var(--red)}.g6 .c3{background:transparent;border:2px dashed var(--green)}
.g6 .meta{margin-top:50px;font-size:13px}.g6 .wmk{position:absolute;right:8px;top:2px;font-weight:800;letter-spacing:.18em;
opacity:.6;font-size:18px}.g6 .REALk{color:var(--green)}.g6 .TEXTk{color:var(--amber)}
.g6 table td,.g6 table th{font-size:12px;padding:4px 8px}.g6 .tw{overflow-x:auto;max-width:100%}
@media(min-width:600px){.g6 h3{margin-right:130px}}@media(max-width:599px){.g6 .wmk{position:static;display:block}.g6 .row{gap:10px}}select,input[type=file]{max-width:100%}.toolbar label{max-width:100%}"""


def payload():
    sp = ROOT / "runs_g6" / "score.json"
    if not sp.exists():
        return None
    score = json.loads(sp.read_text())
    truth = json.loads((ROOT / "eval" / "g6_truth.json").read_text())
    return {"score": score, "truth": {c: {k: truth[c].get(k) for k in ("provenance", "metric", "flaw", "original_claim",
                                                                         "reanalysis", "source", "published_numbers", "data")}
                                      for c in truth}}


def _case_block(c, label, d):
    sc, tr = d["score"]["cases"].get(c, {}), d["truth"][c]
    pub = tr["published_numbers"]
    met = "PR-AUC" if tr["metric"] == "pr_auc" else "accuracy"
    claimed_pub = pub.get("procedure5_apparent_pr_auc", pub.get("wrong_cv_accuracy"))
    corrected_pub = pub.get("procedure6_out_of_sample_pr_auc", pub.get("true_accuracy"))
    reps = [(r, x["loop"]) for r, x in sorted(sc.items()) if "claimed" in x["loop"]]
    if not reps:
        return f"<p class=sub>{html.escape(c)}: no measured repeat.</p>"
    cl = sum(sum(lo["claimed"]) / 3 for _, lo in reps) / len(reps)
    ct = sum(sum(lo["controlled"]) / 3 for _, lo in reps) / len(reps)
    wm, cls = ("REAL-PINNED", "REALk") if tr["provenance"] == "REAL-PINNED" else ("TEXTBOOK", "TEXTk")
    rows = "".join(
        f"<tr><td>{r}<td>{lo['sign']} {''.join(lo.get('per_seed') or [])}<td>{lo['inflation_mean']:+.3f}"
        f"<td>{' '.join('[%+.2f,%+.2f]' % tuple(ci) for ci in lo['inflation_ci'])}<td>{'yes' if lo.get('reproduces') else 'no'}"
        f"<td>{html.escape(str((x['b3'].get('fix_both_pp'))))} pp · {'yes' if x['b3'].get('gets_it') else 'no'}"
        for r, x in sorted(sc.items()) for lo in [x["loop"]] if "claimed" in lo)
    src = tr.get("reanalysis") or tr.get("source")
    top = max(cl, float(claimed_pub), 0.01)  # bars scaled to the largest value shown (axis noted below)
    h = lambda v: max(4, int(float(v) / top * 170))  # noqa: E731
    return f"""<div class=g6><span class="wmk {cls}">{wm}</span>
<h3>{html.escape(label)}</h3>
<p class=sub><b>Published flaw:</b> {html.escape(tr['flaw'])}<br><b>Source:</b> {html.escape(src)}</p>
<div class=row data-g6>
<div class="col c1" style="height:{h(cl)}px" data-h="{h(cl)}"><b>{cl:.2f}</b><small>claimed protocol<br>(published {claimed_pub})</small></div>
<div class="col c2" style="height:{h(cl)}px" data-h="{h(ct)}"><b>{ct:.2f}</b><small>NullLab controlled<br>(mean of repeats)</small></div>
<div class="col c3" style="height:{h(corrected_pub)}px"><b>{corrected_pub}</b><small>published corrected<br>value</small></div>
</div>
<div class=meta>{met} (bar heights relative to the largest value). Measured inflation (claimed − controlled), UNPAIRED bootstrap 95% CI per seed 42/43/44:
<div class=tw><table><tr><th>repeat<th>loop sign<th>mean inflation<th>CIs<th>reproduces published?<th>B3 (reading only) predicted · gets it?{rows}</table></div></div></div>"""


def section():
    d = payload()
    if d is None:
        return "", ""
    acc = d["score"]["acceptance"]
    body = (_case_block("civilwar_apparent", "Civil-war onset: a published claim and its published correction", d)
            + _case_block("esl_selection", "Feature screening before cross-validation (Elements of Statistical Learning §7.10.2)", d))
    clean = (f"<p class=sub>Correct variants of the same pipelines (temporal hold-out; screening inside folds): loop false alarms "
             f"{acc['c_clean_false_alarms']}, B3 false alarms {acc['b3_clean_false_alarms']}. Preregistered acceptance: "
             f"<b>{'PASS' if acc['PASS'] else 'FAIL'}</b> (rule sha256 {d['score']['rule_sha256'][:16]}).</p>")
    html_ = f"<h2>Does it find a real documented flaw? (G6)</h2>{body}{clean}"
    js = """<script>(function(){const go=()=>document.querySelectorAll('[data-g6] .c2').forEach(b=>{b.style.height=b.dataset.h+'px'});
requestAnimationFrame(()=>requestAnimationFrame(()=>setTimeout(go,400)));})();</script>"""
    return html_, js
