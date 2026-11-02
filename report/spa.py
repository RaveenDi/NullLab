"""Assembles report/index.html: one self-contained page (HTML + inlined CSS/JS + embedded run data).
No external requests, no build step. Assets live in report/assets/; data comes from report/spa_data.py."""
import json
from pathlib import Path

from report import spa_data

ASSETS = Path(__file__).resolve().parent / "assets"

NAV = (("readout", "Readout"), ("layers", "Evidence"), ("deliverable", "Deliverable"))

FAVICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 28 28'%3E%3Ccircle cx='14' cy='14' r='10' fill='none' "
           "stroke='%23161616' stroke-width='1.5'/%3E%3Cpath d='M8 20L20 8' stroke='%23C2410C' stroke-width='1.5'/%3E%3C/svg%3E")


def _asset(name):
    return (ASSETS / name).read_text(encoding="utf-8")


def page(data: dict) -> str:
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    nav = "".join(f'<a href="#{i}">{t}</a>' for i, t in NAV)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NullLab</title>
<meta name="description" content="NullLab re-runs a machine-learning claim's suspect step and measures how inflated it was. Every number carries its n and its file.">
<link rel="icon" href="{FAVICON}">
<script>try{{var t=localStorage.getItem("nl-theme");if(t==="light"||t==="dark")document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<style>{_asset("nulllab.css")}</style></head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="top"><div class="wrap"><div class="bar">
  <a class="brand" href="#top" aria-label="NullLab, back to top"><i></i><span>NullLab</span></a>
  <nav class="nav" aria-label="Sections">{nav}</nav>
  <div class="tools">
    <button class="pillbtn" data-open="limits" type="button" aria-haspopup="dialog">Limits</button>
    <button class="pillbtn" id="btnTheme" type="button" aria-label="Switch theme">Dark</button>
    <button class="pillbtn" id="btnHelp" type="button" aria-label="Keyboard shortcuts" aria-haspopup="dialog">?</button>
  </div></div></div></header>

<main id="main">
<section class="hero" id="top" aria-labelledby="headline"><div class="wrap">
  <span class="cap">A claim, re-run with one step changed</span>
  <h1 id="headline" style="margin-top:16px;max-width:18ch"><span>Reading an AI's answer is cheap.</span> <em>Measuring it is the work.</em></h1>
  <p class="sub">Re-runs an ML claim's suspect step and measures how inflated it was.</p>
  <div id="dataStatus" class="status" role="status">Loading run data</div>
  <div class="flow" id="flowBox"></div>
  <div id="heroBody"><p class="muted">Loading</p></div>
  <div class="sr" aria-live="polite" aria-atomic="true" id="live"></div>
  <noscript><p>NullLab re-runs a machine-learning claim under control and reports the measured inflation. This page needs JavaScript to draw its numbers from the run files.</p></noscript>
</div></section>

<section class="sec" id="readout" aria-labelledby="readout-h"><div class="wrap">
  <span class="cap kicker">02 &middot; Readout</span>
  <h2 id="readout-h"><span>One dial,</span> <em>three numbers.</em></h2>
  <div id="readoutBody"></div>
</div></section>

<section class="sec" id="intervals" aria-labelledby="intervals-h"><div class="wrap">
  <span class="cap kicker">03 &middot; Intervals</span>
  <h2 id="intervals-h"><span>Every repeat, failures included,</span> <em>on one scale.</em></h2>
  <div id="intervalsBody"></div>
</div></section>

<section class="sec" id="layers" aria-labelledby="layers-h"><div class="wrap">
  <span class="cap kicker">04 &middot; Layers of evidence</span>
  <h2 id="layers-h"><span>Two runs on the real case, side by side.</span> <em>Then everything else.</em></h2>
  <p class="lede">The core is the disguised real case. Each ring outward is a weaker test of the same idea. A run that failed its bar sits beside the run that met its clauses, at the same size.</p>
  <div id="layersBody"></div>
</div></section>

<section class="sec" id="deliverable" aria-labelledby="deliv-h"><div class="wrap">
  <span class="cap kicker">05 &middot; Deliverable</span>
  <h2 id="deliv-h"><span>What a reviewer receives,</span> <em>in plain type.</em></h2>
  <div id="delivBody"></div>
  <div class="drawrow" role="group" aria-label="More detail">
    <button class="pillbtn" data-open="steps" type="button">Step log and diff</button>
    <button class="pillbtn" data-open="factorial" type="button">2x2 factorial</button>
    <button class="pillbtn" data-open="score" type="button">Scoreboard</button>
    <button class="pillbtn" data-open="wonder" type="button">Wonder swap</button>
    <button class="pillbtn" data-open="ci" type="button">CI and bundle commands</button>
    <button class="pillbtn" data-open="sandbox" type="button">Sandbox limits</button>
    <button class="pillbtn" data-open="flaw" type="button">The untouched second flaw</button>
  </div>
</div></section>
</main>

<footer><div class="wrap" id="footBody"></div></footer>

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-labelledby="drawerTitle" aria-hidden="true" inert>
  <header><span id="drawerTitle"></span><button class="pillbtn" id="closeDrawer" type="button" aria-label="Close">Close</button></header>
  <div class="body" id="drawerBody"></div>
</aside>
<dialog id="help" aria-labelledby="help-h"><h2 id="help-h">Keyboard</h2>
  <div class="keys"><span><kbd>&larr;</kbd> <kbd>&rarr;</kbd></span><span>move between flow nodes</span><kbd>Enter</kbd><span>jump to a node's section</span><kbd>Space</kbd><span>play or pause the hero replay</span>
  <kbd>R</kbd><span>replay</span><kbd>S</kbd><span>skip to the end state</span><kbd>T</kbd><span>light or dark</span><kbd>L</kbd><span>limits</span><kbd>Esc</kbd><span>close</span></div>
  <form method="dialog" style="margin-top:20px"><button class="pillbtn solid" id="closeHelp" type="submit">Got it</button></form></dialog>
<div class="toast" id="toast" role="status" aria-live="polite"></div>
<script>window.__NL_DATA={payload};</script>
<script>{_asset("viz.js")}</script>
<script>{_asset("app.js")}</script>
</body></html>
"""


def build_page() -> str:
    return page(spa_data.build())
