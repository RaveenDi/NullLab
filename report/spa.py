"""Assembles report/index.html: one self-contained page (HTML + inlined CSS/JS + embedded run data).
No external requests, no build step. Assets live in report/assets/; data comes from report/spa_data.py."""
import json
from pathlib import Path

from report import spa_data

ASSETS = Path(__file__).resolve().parent / "assets"

MARK = ('<svg viewBox="0 0 28 28" aria-hidden="true"><rect x="1" y="1" width="26" height="26" rx="8" fill="var(--ink)"/>'
        '<circle cx="14" cy="14" r="6.5" fill="none" stroke="var(--bg)" stroke-width="2.4"/>'
        '<path d="M8.5 19.5L19.5 8.5" stroke="var(--accent)" stroke-width="2.6" stroke-linecap="round"/></svg>')

NAV = (("how", "How it works"), ("factorial", "2×2 factorial"), ("vs", "Reading vs running"),
       ("real", "Real case"), ("numbers", "Scoreboard"))

SK = '<div class="sk" style="height:28px;width:60%"></div><div class="sk" style="height:46px"></div><div class="sk" style="height:18px;width:40%"></div>'


def _asset(name):
    return (ASSETS / name).read_text(encoding="utf-8")


def page(data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NullLab</title>
<meta name="description" content="NullLab re-runs a machine-learning claim under control and reports the measured inflation, with every number labelled.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 28 28'%3E%3Crect x='1' y='1' width='26' height='26' rx='8' fill='%23111'/%3E%3Ccircle cx='14' cy='14' r='6.5' fill='none' stroke='%23fff' stroke-width='2.4'/%3E%3Cpath d='M8.5 19.5L19.5 8.5' stroke='%23E8501F' stroke-width='2.6' stroke-linecap='round'/%3E%3C/svg%3E">
<script>try{{var t=localStorage.getItem("nl-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>{_asset("nulllab.css")}</style></head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<div class="bgdots" aria-hidden="true"></div>
<header class="top"><div class="wrap"><div class="bar">
  <a class="brand" href="#top" aria-label="NullLab, back to top">{MARK}<span>NullLab</span></a>
  <nav class="nav" aria-label="Sections">{nav}</nav>
  <div class="tools">
    <button class="btn" data-open-limits type="button" aria-haspopup="dialog">Limits</button>
    <button class="btn icon" id="btnTheme" type="button" aria-label="Switch theme"></button>
    <button class="btn icon" id="btnHelp" type="button" aria-label="Keyboard shortcuts" aria-haspopup="dialog">?</button>
  </div></div></div></header>

<main id="main">
<section class="hero wrap" id="top" aria-labelledby="headline">
  <svg class="hero-art" id="heroArt" viewBox="0 34 1200 312" role="img" aria-label="DOUBT. TEST. MEASURE. A claim and a hypothesis go in; an edit is run; out comes a verdict and the measured inflation."></svg>
  <h1 class="headline" id="headline"><span class="g">Reading an AI's answer is cheap.</span> Measuring it is the work.</h1>
  <p class="promise">NullLab does not cry wolf. It re-runs a machine-learning claim under control, edits only the suspect step, and reports the measured inflation, with every number labelled.</p>
  <div id="dataStatus" class="status" role="status"><i></i><span>Loading run data…</span></div>

  <div class="panel wow" id="wow">
    <div class="wow-head"><p class="eyebrow" style="margin:0" id="casesLabel">Try another case · ← →</p>
      <div class="cases" role="tablist" aria-labelledby="casesLabel" id="cases"></div></div>
    <div id="wowBody" role="tabpanel" aria-label="Claim versus measured">{SK}</div>
    <div class="ctrl" role="group" aria-label="Replay controls">
      <button class="btn primary" id="btnReplay" type="button"><span class="ico">{'<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8a4.5 4.5 0 1 0 1.4-3.3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M3 2.5v3h3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>'}</span>Replay</button>
      <button class="btn" id="btnPause" type="button">Pause</button>
      <button class="btn outline" id="btnSkip" type="button">Skip to result</button>
      <div class="seg" id="speed" role="group" aria-label="Replay speed"><button type="button" data-s="0.5" aria-pressed="false">0.5×</button><button type="button" data-s="1" aria-pressed="true">1×</button><button type="button" data-s="2" aria-pressed="false">2×</button></div>
      <span class="grow"></span>
      <button class="btn" id="btnCopy" type="button">Copy summary</button>
      <button class="btn" id="btnDownload" type="button">Download report</button>
    </div>
    <div class="progress" aria-hidden="true"><i id="prog"></i></div>
  </div>
  <div class="sr" aria-live="polite" aria-atomic="true" id="live"></div>

  <div class="panel" style="margin-top:16px;text-align:left" aria-label="Measured counts"><div class="stats" id="statsBody">{SK}</div></div>
</section>

<section class="sec wrap" id="how" aria-labelledby="how-h">
  <p class="eyebrow">How it works</p>
  <h2 class="h2" id="how-h"><span class="g">Four steps,</span> every one logged and hashed.</h2>
  <p class="lede" id="stepsCase"></p>
  <div id="stepsBody">{SK}</div>
</section>

<section class="sec wrap" id="factorial" aria-labelledby="fx-h">
  <p class="eyebrow">The 2×2 factorial</p>
  <h2 class="h2" id="fx-h"><span class="g">Two suspect steps.</span> Fix each alone, then both.</h2>
  <p class="lede">The planner names two suspect steps. Code applies only those edits and runs four versions on three seeds. If fixing both removes more than the two fixes separately, the flaws interact. All of these cases are synthetic: we built them.</p>
  <div class="quick" id="fxQuick" role="group" aria-label="Example runs"></div>
  <label class="small muted" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:16px">Any case and repeat <select class="sel" id="fxSel"></select></label>
  <div id="fxBody">{SK}</div>
</section>

<section class="sec wrap" id="vs" aria-labelledby="vs-h">
  <p class="eyebrow">Reading vs running</p>
  <h2 class="h2" id="vs-h"><span class="g">One prompt reads the code.</span> NullLab runs it.</h2>
  <p class="lede">Same case and repeat as the factorial above. Marks are against the truth we planted; size is shown but not scored.</p>
  <div id="vsBody">{SK}</div>
</section>

<section class="sec wrap" id="real" aria-labelledby="real-h">
  <p class="eyebrow">A real published case and a textbook case</p>
  <h2 class="h2" id="real-h"><span class="g">The published correction</span> versus what we measured.</h2>
  <p class="lede">Direction is right on both. Size is right on the textbook case and only once in three on the real paper. Both sources are famous, so the model may remember them.</p>
  <div id="realBody">{SK}</div>
</section>

<section class="sec wrap" id="numbers" aria-labelledby="sb-h">
  <p class="eyebrow">Scoreboard</p>
  <h2 class="h2" id="sb-h"><span class="g">Counts with n,</span> including where we lose.</h2>
  <div id="scoreBody">{SK}</div>
</section>
</main>

<footer class="wrap"><div class="panel">
  <span>NullLab · Meta Global AI Developer Hackathon · model calls: muse-spark-1.3 (recorded runs; this page calls no model)</span>
  <span>Test suite: {data.get("tests_doc", {}).get("value", "")} ({data.get("tests_doc", {}).get("src", "")}) · data generated {data.get("generated_utc", "")}</span>
  <button class="btn" data-open-limits type="button">Read the limits</button>
</div></footer>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="limits" role="dialog" aria-modal="true" aria-labelledby="limits-h" aria-hidden="true" inert>
  <header><h2 id="limits-h">Limits: what is synthetic, mock or unverified</h2><button class="btn icon" id="closeLimits" type="button" aria-label="Close limits">✕</button></header>
  <div class="body" id="limitsBody"></div>
</aside>
<dialog class="help" id="help" aria-labelledby="help-h"><h2 id="help-h">Keyboard shortcuts</h2>
  <div class="keys"><span><kbd>←</kbd> <kbd>→</kbd></span><span>previous / next case</span><kbd>Space</kbd><span>play or pause the replay</span>
  <kbd>R</kbd><span>replay</span><kbd>S</kbd><span>skip to the result</span><kbd>T</kbd><span>light / dark theme</span><kbd>L</kbd><span>open the limits</span><kbd>?</kbd><span>this help</span><kbd>Esc</kbd><span>close</span></div>
  <form method="dialog" style="margin-top:20px"><button class="btn primary" id="closeHelp" type="submit"><span class="ico">✓</span>Got it</button></form></dialog>
<div class="tip" id="tip" role="tooltip"></div>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>window.__NL_DATA={payload};</script>
<script>{_asset("dotmatrix.js")}</script>
<script>{_asset("app.js")}</script>
</body></html>
"""


def build_page() -> str:
    return page(spa_data.build())
