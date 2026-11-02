/* NullLab demo page. Plain JS, no external requests. Data: window.__NL_DATA (embedded at render time) or /api/demo. */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const DM = window.DotMatrix;
  const RM = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const ease = p => 1 - Math.pow(1 - p, 3);
  const sg = (x, d) => (x == null ? "n/a" : (x >= 0 ? "+" : "") + Number(x).toFixed(d));
  const fv = (v, unit) => v == null ? "n/a" : unit === "pct" ? (v * 100).toFixed(1) + "%" : Number(v).toFixed(3);
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
                  set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* storage blocked */ } } };

  const IC = {
    x: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" fill="none"/></svg>',
    check: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 5" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>',
    q: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.6 5.8a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.2.9-1.2 1.8" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" fill="none"/><circle cx="8" cy="13" r="1.3" fill="currentColor"/></svg>',
    dash: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 8h8" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>',
    play: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3.5v9l7-4.5z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4.5 3.5h2.5v9H4.5zM9 3.5h2.5v9H9z" fill="currentColor"/></svg>',
    replay: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.5 8a4.5 4.5 0 1 0 1.4-3.3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round"/><path d="M3 2.5v3h3" stroke="currentColor" stroke-width="2" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    skip: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 3.5v9l6-4.5zM9 3.5v9l6-4.5z" fill="currentColor"/></svg>',
    info: '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="6.5" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M8 7v4.2" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="4.8" r="1" fill="currentColor"/></svg>'
  };
  const VICON = { FALSIFIED: IC.x, SURVIVED: IC.check, INCONCLUSIVE: IC.q };
  const vchip = (v, extra) => `<span class="vd ${esc(v)}">${VICON[v] || IC.q}${esc(v)}${extra ? " " + esc(extra) : ""}</span>`;
  const badge = b => `<span class="badge ${esc(b)}" title="${esc(BADGE_HELP[b] || "")}">${esc(b)}</span>`;
  const BADGE_HELP = {
    "REAL-PINNED": "Real public data pinned by checksum or bundled with scikit-learn",
    "TEXTBOOK": "A textbook-documented setting, not a published reanalysis of a paper",
    "SYNTHETIC": "A case we generated with planted flaws",
    "MOCK": "Scripted stand-in, not a model result", "LIVE": "Model calls to muse-spark-1.3"
  };
  const src = s => `<span class="badge SRC">source: ${esc(s)}</span>`;

  let D = null;
  const S = { case: null, fx: "g4_assay_replicates.r1", step: null };

  /* ------------------------------------------------------------------ hash state */
  function readHash() {
    const h = new URLSearchParams(location.hash.replace(/^#/, ""));
    if (h.get("case")) S.case = h.get("case");
    if (h.get("fx")) S.fx = h.get("fx");
    if (h.get("step")) S.step = h.get("step");
  }
  function writeHash() {
    const h = new URLSearchParams();
    if (S.case) h.set("case", S.case);
    if (S.fx) h.set("fx", S.fx);
    if (S.step) h.set("step", S.step);
    try { history.replaceState(null, "", "#" + h.toString()); } catch (e) { /* file:// in some browsers */ }
  }

  /* ------------------------------------------------------------------ hero art */
  function pill(x, y, label, fs) {
    const w = Math.round(label.length * fs * 0.62 + fs * 1.8), h = Math.round(fs * 2);
    return { w, svg: `<g class="pill"><rect x="${x}" y="${y - h / 2}" width="${w}" height="${h}" rx="${h / 2}"/><text x="${x + w / 2}" y="${y + fs * 0.36}" text-anchor="middle" style="font-size:${fs}px">${esc(label)}</text></g>` };
  }
  function mark(cx, cy, r, sw) {
    const d = r * 0.98;
    return `<circle class="mark" cx="${cx}" cy="${cy}" r="${r}" stroke-width="${sw}"/><path class="mark mark-s" d="M${cx - d} ${cy + d}L${cx + d} ${cy - d}" stroke-width="${sw}" stroke-linecap="round"/>`;
  }
  let heroWide = null;
  function drawHero(animate) {
    const svg = $("#heroArt"); if (!svg) return;
    const wide = svg.parentElement.clientWidth >= 760;
    if (wide === heroWide && !animate) return;
    heroWide = wide;
    let s = "";
    if (wide) {
      svg.setAttribute("viewBox", "0 34 1200 312");
      const cx = 600, cy = 190;
      s += `<path class="rail" d="M24 60H430"/><path class="rail" d="M60 320H430"/><path class="rail" d="M770 60H1176"/><path class="rail" d="M770 320H1140"/>`;
      s += `<path class="conn" d="M430 60C472 60 486 78 512 104"/><path class="conn" d="M430 320C472 320 486 302 512 276"/>`;
      s += `<path class="conn" d="M688 104C714 78 728 60 770 60"/><path class="conn" d="M688 276C714 302 728 320 770 320"/>`;
      s += `<circle class="end" cx="430" cy="60" r="4.5"/><circle class="end" cx="430" cy="320" r="4.5"/><circle class="end" cx="770" cy="60" r="4.5"/><circle class="end" cx="770" cy="320" r="4.5"/>`;
      s += `<circle class="end" cx="24" cy="60" r="3" opacity=".5"/><circle class="end" cx="1176" cy="60" r="3" opacity=".5"/>`;
      [[110, 60, "Claim"], [250, 60, "Hypothesis"], [170, 320, "Edit"], [860, 60, "Run"], [980, 60, "Verdict"], [880, 320, "Inflation"]]
        .forEach(([x, y, t]) => { s += pill(x, y, t, 13).svg; });
      s += `<rect class="tile-o" x="${cx - 100}" y="${cy - 100}" width="200" height="200" rx="44"/><rect class="tile-i" x="${cx - 74}" y="${cy - 74}" width="148" height="148" rx="30"/>`;
      s += mark(cx, cy, 34, 9);
      const L = DM.group("DOUBT. TEST.", 0, 0, 6), R = DM.group("MEASURE.", 0, 0, 6);
      s += `<g class="dm">${DM.group("DOUBT. TEST.", 470 - L.w, cy - L.h / 2, 6).svg}${DM.group("MEASURE.", 730, cy - R.h / 2, 6).svg}</g>`;
    } else {
      svg.setAttribute("viewBox", "0 0 400 340");
      const cx = 200, cy = 174;
      const top = DM.group("DOUBT. TEST.", 0, 0, 5), bot = DM.group("MEASURE.", 0, 0, 6);
      const lp = [["Claim", 124], ["Hypothesis", 174], ["Edit", 224]], rp = [["Run", 124], ["Verdict", 174], ["Inflation", 224]];
      const ty = [148, 174, 200];
      lp.forEach(([t, y], i) => { const p = pill(6, y, t, 11); s += `<path class="conn" d="M${6 + p.w} ${y}C${118} ${y} ${110} ${ty[i]} ${cx - 72} ${ty[i]}"/>` + p.svg; });
      rp.forEach(([t, y], i) => { const w = pill(0, y, t, 11).w; const p = pill(394 - w, y, t, 11); s += `<path class="conn" d="M${cx + 72} ${ty[i]}C${290} ${ty[i]} ${282} ${y} ${394 - w} ${y}"/>` + p.svg; });
      s += `<rect class="tile-o" x="${cx - 72}" y="${cy - 72}" width="144" height="144" rx="32"/><rect class="tile-i" x="${cx - 52}" y="${cy - 52}" width="104" height="104" rx="22"/>`;
      s += mark(cx, cy, 24, 7);
      s += `<g class="dm">${DM.group("DOUBT. TEST.", (400 - top.w) / 2, 14, 5).svg}${DM.group("MEASURE.", (400 - bot.w) / 2, 290, 6).svg}</g>`;
    }
    svg.innerHTML = s;
    svg.style.maxWidth = wide ? "" : "460px";
    $$(".conn,.rail", svg).forEach(p => { try { p.style.setProperty("--len", Math.ceil(p.getTotalLength()) + 1); } catch (e) { /* old engines */ } });
    if (animate && !RM) { svg.classList.remove("draw"); void svg.getBoundingClientRect(); svg.classList.add("draw"); }
  }

  /* ------------------------------------------------------------------ the 10-second wow (timeline) */
  const T = { RUN0: 300, RUN1: 2700, COL: 2800, COLD: 900, STAMP: 3800, WHY: 3950, END: 4400 };
  const TL = { t: 0, playing: false, speed: 1, last: null, raf: 0, announced: false };
  const hero = () => D.heroes.find(h => h.id === S.case) || D.heroes[0];
  const trace = () => (D.traces || {})[hero().id];

  function renderCases() {
    const el = $("#cases");
    el.innerHTML = D.heroes.map((h, i) => `<button role="tab" id="tab-${esc(h.id)}" aria-controls="wowBody" aria-selected="${h.id === S.case}" tabindex="${h.id === S.case ? 0 : -1}" data-i="${i}"><span class="k ${esc(h.verdict)}"></span>${esc(h.short)}</button>`).join("");
    $$("button", el).forEach(b => b.addEventListener("click", () => selectCase(D.heroes[+b.dataset.i].id, true)));
  }

  function pct(h, v) { return clamp(v / h.axis_max * 100, 0, 100); }
  function renderWow() {
    const h = hero(), tr = trace();
    const end = h.end ? h.end.value : null;
    const mk = (h.markers || []).filter(m => m.value != null).map((m, i) => {
      const p = pct(h, m.value), tx = p > 82 ? "translateX(-100%)" : p < 14 ? "translateX(0)" : "translateX(-50%)";
      return `<div class="mk ${i % 2 ? "alt" : ""}" style="left:${p}%"><span style="transform:${tx}">${esc(m.label)}: ${esc(fv(m.value, h.unit))}</span></div>`;
    }).join("");
    const seeds = (h.seeds || []).map(s => `<tr><td>${esc(s.seed)}</td><td>${fv(s.claimed, h.unit)}</td><td>${fv(s.controlled, h.unit)}</td><td>${sg(s.delta, 3)}</td><td>[${sg(s.ci[0], 3)}, ${sg(s.ci[1], 3)}]</td><td>${s.n != null ? s.n : "see n below"}</td></tr>`).join("");
    const ex = (h.seeds || []).filter(s => s.ci[0] > 0 || s.ci[1] < 0).length;
    $("#wowBody").innerHTML = `
      <p class="claim">“${esc(h.claim_text)}”</p>
      <div class="meta">${h.provenance.map(badge).join("")}<span class="badge LIVE">${esc(h.mode)}</span>${src(h.source)}<span class="xs muted">${esc(h.prov_note)}</span></div>
      <div class="meter">
        <div class="labels">
          <div><div class="bignum" id="numA">${DM.svg(fv(h.start.value, h.unit), { pitch: 6, label: "claimed " + fv(h.start.value, h.unit) })}</div><div class="numcap">${esc(h.start.label)}</div></div>
          <div style="text-align:right"><div class="bignum acc" id="numB" style="display:flex;justify-content:flex-end"></div><div class="numcap" style="margin-left:auto">${esc(h.end ? h.end.label : "no measured number")}${h.n_text ? " · " + esc(h.n_text) : ""}</div></div>
        </div>
        <div class="track" role="img" aria-label="${esc(h.metric)} bar: claimed ${esc(fv(h.start.value, h.unit))}, measured ${esc(fv(end, h.unit))}">
          <div class="ghost" id="ghost" style="left:${pct(h, h.start.value)}%"></div>
          <div class="fill" id="fill"></div>${mk}
        </div>
        <div class="axis"><span>0</span><span>${esc(h.metric)} axis, 0 to ${esc(fv(h.axis_max, h.unit))}</span><span>${esc(fv(h.axis_max, h.unit))}</span></div>
        <div class="stamp ${esc(h.verdict)}" id="stamp" aria-hidden="true">${VICON[h.verdict]}${esc(h.verdict)}</div>
      </div>
      <div class="steps-mini" id="mini" aria-hidden="true">${["Plan", "Act", "Verify", "Recover"].map(p => `<span data-p="${p}">${p}</span>`).join("")}</div>
      <div class="ticker" id="ticker" aria-hidden="true"></div>
      <p class="why" id="why"><b>${esc(h.verdict)}.</b> ${esc(h.why)}</p>
      ${seeds ? `<details class="more"><summary>Per-seed numbers and how sure we are</summary>
        <div class="tw"><table class="seeds"><thead><tr><th>seed</th><th>claim's protocol</th><th>controlled</th><th>drop</th><th>95% interval of drop</th><th>n</th></tr></thead><tbody>${seeds}</tbody></table></div>
        <p class="xs muted">How sure: each interval comes from an unpaired bootstrap of that seed's test rows; an interval that excludes 0 is a measured drop. ${ex} of ${h.seeds.length} intervals exclude 0. ${esc(h.n_text)}.</p></details>` : ""}`;
    TL.lines = (tr && tr.lines) || [];
    TL.lastNum = null;
    renderSteps();
  }

  function paint() {
    const h = hero(), t = TL.t;
    const startP = pct(h, h.start.value), end = h.end ? h.end.value : null;
    const pr = ease(clamp((t - T.COL) / T.COLD, 0, 1));
    const fill = $("#fill");
    if (!fill) return;
    if (end == null) {
      fill.style.width = startP + "%";
      fill.className = "fill" + (t >= T.COL ? " hatch" : "");
    } else {
      fill.style.width = (startP + (pct(h, end) - startP) * pr) + "%";
      fill.className = "fill" + (t >= T.STAMP && h.verdict === "FALSIFIED" ? " FALSIFIED" : "");
    }
    $("#ghost").classList.toggle("on", t >= T.COL);
    const num = end == null ? (t >= T.COL ? "--" : fv(h.start.value, h.unit)) : fv(h.start.value + (end - h.start.value) * pr, h.unit);
    if (num !== TL.lastNum) { $("#numB").innerHTML = DM.svg(num, { pitch: 6, label: (t >= T.STAMP ? "measured " : "") + num }); TL.lastNum = num; }
    $("#stamp").classList.toggle("on", t >= T.STAMP);
    $("#why").classList.toggle("on", t >= T.WHY);
    // log lines
    const n = TL.lines.length, idx = n ? Math.floor((t - T.RUN0) / ((T.RUN1 - T.RUN0) / n)) : -1;
    const cur = t >= T.RUN1 ? n : clamp(idx, -1, n - 1);
    const line = TL.lines[clamp(cur, 0, n - 1)];
    $("#ticker").textContent = t < T.RUN0 ? "Re-running the claim under control…" : t >= T.STAMP ? "Done: " + (TL.lines.length ? TL.lines.length + " log lines, all from " + (trace() || {}).source : "") : line ? "[" + line.phase + "] " + line.text : "";
    const phases = ["Plan", "Act", "Verify", "Recover"];
    const curPh = cur >= 0 && cur < n ? TL.lines[cur].phase : null;
    const seenPh = new Set(TL.lines.slice(0, clamp(cur + 1, 0, n)).map(l => l.phase));
    $$("#mini span").forEach(sp => {
      const p = sp.dataset.p;
      sp.className = p === curPh ? "on" : seenPh.has(p) ? "done" : "";
      if (p === "Recover" && t >= T.RUN1 && !seenPh.has("Recover")) sp.textContent = "Recover: not needed";
      else sp.textContent = p;
    });
    $$("#log li").forEach((li, i) => { li.className = i === cur ? "cur" : i < cur || t >= T.RUN1 ? "seen" : ""; });
    $$(".step").forEach(b => b.classList.toggle("live", b.dataset.p === curPh && t < T.RUN1));
    $("#prog").style.width = (t / T.END * 100) + "%";
    if (t >= T.STAMP && !TL.announced) {
      TL.announced = true;
      $("#live").textContent = `${h.verdict}: ${h.short}. Claimed ${fv(h.start.value, h.unit)}, measured ${fv(end, h.unit)}. ${h.why}`;
    }
  }

  /* rAF drives the replay; a slow timer keeps it moving when the browser throttles rAF (hidden or background tab). */
  function frame() {
    const now = performance.now();
    if (TL.last == null) TL.last = now;
    const dt = Math.min(1000, now - TL.last); TL.last = now;
    if (!TL.playing) return;
    TL.t = Math.min(T.END, TL.t + dt * TL.speed);
    paint();
    if (TL.t >= T.END) { TL.playing = false; syncCtrl(); }
  }
  function loop() { TL.raf = 0; frame(); if (TL.playing) TL.raf = requestAnimationFrame(loop); }
  function play() {
    if (TL.t >= T.END) TL.t = 0;
    TL.playing = true; TL.last = null;
    if (!TL.raf) TL.raf = requestAnimationFrame(loop);
    clearInterval(TL.iv); TL.iv = setInterval(() => { if (!TL.playing) { clearInterval(TL.iv); return; } if (performance.now() - (TL.last || 0) > 120) frame(); }, 150);
    syncCtrl();
  }
  function pause() { TL.playing = false; syncCtrl(); }
  function replay() {
    TL.announced = false; $("#live").textContent = "";
    if (RM) { TL.playing = false; TL.t = 0; paint(); setTimeout(() => { TL.t = T.END; paint(); syncCtrl(); }, 40); return; }
    TL.t = 0; paint(); play();
  }
  function skip() { TL.t = T.END; TL.playing = false; paint(); syncCtrl(); }
  function syncCtrl() {
    const b = $("#btnPause");
    const on = TL.playing;
    b.innerHTML = on ? IC.pause + "Pause" : IC.play + (TL.t >= T.END ? "Play again" : "Resume");
    b.setAttribute("aria-label", on ? "Pause the replay" : "Play the replay");
    $$("#speed button").forEach(x => x.setAttribute("aria-pressed", String(+x.dataset.s === TL.speed)));
  }

  function selectCase(id, focus) {
    if (!D.heroes.some(h => h.id === id)) id = D.heroes[0].id;
    S.case = id; writeHash();
    $$("#cases button").forEach(b => { const on = D.heroes[+b.dataset.i].id === id; b.setAttribute("aria-selected", on); b.tabIndex = on ? 0 : -1; if (on && focus) b.focus({ preventScroll: true }); });
    renderWow(); replay();
  }
  function stepCase(d) {
    const i = D.heroes.findIndex(h => h.id === S.case);
    selectCase(D.heroes[(i + d + D.heroes.length) % D.heroes.length].id, document.activeElement && document.activeElement.closest("#cases"));
  }

  /* ------------------------------------------------------------------ Plan / Act / Verify / Recover */
  const STEP_TXT = {
    Plan: "Name what could be wrong and commit to it, hashed, before anything runs.",
    Act: "Write the smallest edit that fixes only the suspect step and run it in a sandbox.",
    Verify: "A deterministic guard checks that only the named step changed, then the stats are read.",
    Recover: "If the guard or the run fails: one retry with the error text, else INCONCLUSIVE."
  };
  function renderSteps() {
    const tr = trace(), h = hero();
    const box = $("#stepsBody");
    if (!tr) { box.innerHTML = `<div class="empty">No trace for this case in the run files.</div>`; return; }
    const cnt = p => tr.lines.filter(l => l.phase === p).length;
    $("#stepsCase").innerHTML = `Trace of <b>${esc(h.short)}</b> ${h.provenance.map(badge).join(" ")} ${src(tr.source)}`;
    box.innerHTML = `<div class="steps" role="list">${["Plan", "Act", "Verify", "Recover"].map((p, i) => `
      <button class="step" role="listitem" data-p="${p}" aria-expanded="${S.step === p.toLowerCase()}" aria-controls="stepDetail">
        <span class="n">0${i + 1}</span><h3>${p}</h3><p>${STEP_TXT[p]}</p>
        <span class="state">${p === "Recover" ? (tr.recover.used ? "used" : "not needed") : cnt(p) + " log line" + (cnt(p) === 1 ? "" : "s")}</span></button>`).join("")}</div>
      <div id="stepDetail" class="detail" aria-live="polite"></div>
      <ol class="log" id="log" aria-label="Agent log">${tr.lines.map(l => `<li><b>${esc(l.phase)}</b> ${esc(l.text)}${l.detail ? `<span class="d">${esc(l.detail)}</span>` : ""}</li>`).join("")}</ol>`;
    $$(".step", box).forEach(b => b.addEventListener("click", () => {
      const p = b.dataset.p.toLowerCase(); S.step = S.step === p ? null : p; writeHash(); renderDetail();
    }));
    renderDetail();
  }
  function renderDetail() {
    const tr = trace(), el = $("#stepDetail"); if (!el || !tr) return;
    $$(".step").forEach(b => b.setAttribute("aria-expanded", String(b.dataset.p.toLowerCase() === S.step)));
    if (!S.step) { el.innerHTML = `<p class="xs muted">Tap a step to see what the agent actually did in this run.</p>`; return; }
    let h = "";
    if (S.step === "plan") {
      const P = tr.plan;
      if (P.hypotheses) h += `<h4>Preregistered hypotheses</h4>` + P.hypotheses.map(x => `<div class="hyp ${x.primary ? "p" : ""}"><b>${esc(x.id)}${x.primary ? " · primary" : ""} · ${esc(x.direction)}</b><br>${esc(x.text)}</div>`).join("");
      if (P.suspects) h += `<h4>Suspect steps named by the planner</h4>` + P.suspects.map(x => `<div class="hyp"><b>${esc(x.id)}</b> ${esc(x.text)}${x.code_line ? `<br><code class="xs">${esc(x.code_line)}</code>` : ""}</div>`).join("");
      if (P.pred) h += `<p class="small">Predicted drops before running (pp): ${Object.entries(P.pred).map(([k, v]) => esc(k) + " " + esc(v)).join(", ")}</p>`;
      h += `<p class="src">${esc(P.note)} · sha256 ${esc(P.sha)}</p>`;
    } else if (S.step === "act") {
      h += `<h4>The edit</h4>` + (tr.act.edits.length ? tr.act.edits.map(e => `<p class="xs muted" style="margin:10px 0 0">${esc(e.label)}</p><pre class="code" tabindex="0">${esc(e.code)}</pre>`).join("") : `<p class="muted small">No edit was executed.</p>`);
      h += `<p class="src">${esc(tr.act.note)}</p>`;
    } else if (S.step === "verify") {
      if (tr.verify.fidelity.length) h += `<h4>Fidelity verdict</h4><ul class="fid">${tr.verify.fidelity.map(f => `<li>${IC.check}<span>${esc(f)}</span></li>`).join("")}</ul>`;
      h += `<h4>Log</h4><ul class="fid">${tr.verify.lines.map(f => `<li>${IC.dash}<span>${esc(f)}</span></li>`).join("")}</ul>`;
    } else {
      h += tr.recover.used ? `<h4>Recover was used</h4><ul class="fid">${tr.recover.lines.map(f => `<li>${IC.x}<span>${esc(f)}</span></li>`).join("")}</ul><p class="small">After one retry with the violation text, the run ${tr.recover.status === "ok" ? "passed the guard and was measured." : "still failed, so it is reported as INCONCLUSIVE, never as FALSIFIED."}</p>`
        : `<p class="small">Not needed in this run: the first patch passed every check.</p>`;
    }
    el.innerHTML = `<div class="panel" style="padding:16px">${h}</div>`;
  }

  /* ------------------------------------------------------------------ factorial (G5, SYNTHETIC) */
  const QUICK = [["g4_assay_replicates.r1", "Interaction"], ["g4_freight_delay.r1", "Cancellation"], ["g4_pump_inspection.r1", "Wrong culprit"],
                 ["g4_crop_irrigation.r2", "Benign"], ["clean_group_correct.r1", "Correct pipeline"], ["clean_wine_correct.r2", "Our false alarm"],
                 ["g4_crop_irrigation.r1", "Inconclusive"]];
  function renderFactorialShell() {
    const F = D.factorial || {};
    if (!Object.keys(F).length) { $("#fxBody").innerHTML = `<div class="empty">No G5 run files found (runs_g5/). Run <code>python g5.py</code>.</div>`; return false; }
    $("#fxQuick").innerHTML = QUICK.filter(([k]) => F[k]).map(([k, l]) => `<button data-k="${k}" aria-pressed="false">${l}</button>`).join("");
    $$("#fxQuick button").forEach(b => b.addEventListener("click", () => selectFx(b.dataset.k)));
    $("#fxSel").innerHTML = Object.keys(F).map(k => `<option value="${esc(k)}">${esc(F[k].case.replace(/^g4_/, ""))} · ${esc(F[k].kind)} · repeat ${F[k].repeat}</option>`).join("");
    $("#fxSel").addEventListener("change", e => selectFx(e.target.value));
    return true;
  }
  function selectFx(k) {
    const F = D.factorial || {};
    if (!F[k]) k = Object.keys(F)[0];
    S.fx = k; writeHash();
    $("#fxSel").value = k;
    $$("#fxQuick button").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.k === k)));
    renderFx(); renderVs();
  }
  function fxVerdict(r) {
    const s = r.loop.sign;
    if (r.status !== "ok" || !["+", "0", "-"].includes(s)) return ["INCONCLUSIVE", ""];
    return s === "+" ? ["FALSIFIED", "(inflated)"] : s === "-" ? ["SURVIVED", "(understated, not inflated)"] : ["SURVIVED", ""];
  }
  function renderFx() {
    const r = D.factorial[S.fx], box = $("#fxBody");
    if (r.status !== "ok") {
      box.innerHTML = `<div class="panel"><div class="row">${vchip("INCONCLUSIVE")}<span class="small">${esc(r.case)} · repeat ${r.repeat}</span>${src(r.source)}</div>
        <p>No measurement. The guard or the run still failed after one retry, so this counts as wrong in the score and is never reported as FALSIFIED.</p>
        <pre class="code" tabindex="0">${esc(r.reason)}</pre></div>`;
      return;
    }
    const cf = [["orig", "original", "o"], ["fix_A", "fix A only", ""], ["fix_B", "fix B only", ""], ["fix_both", "fix both", "both"]];
    const C = r.loop.components_pp, W = 560, H = 300, x0 = 46, y0 = 24, ch = 210, bw = 78, gap = (W - x0 - 4 * bw) / 4;
    const y = v => y0 + ch - v * ch;
    let g = "";
    [0, .25, .5, .75, 1].forEach(v => { g += `<line class="gl" x1="${x0}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text class="ax" x="${x0 - 8}" y="${y(v) + 4}" text-anchor="end">${v * 100}%</text>`; });
    cf.forEach(([k, l, c], i) => {
      const v = r.acc[k], bx = x0 + gap / 2 + i * (bw + gap);
      const drop = k === "orig" ? "" : `drop ${sg(k === "fix_A" ? C.A : k === "fix_B" ? C.B : C.both, 1)} pp`;
      const seeds = Object.entries(r.acc_seed).map(([s, a]) => `seed ${s}: ${(a[k] * 100).toFixed(1)}%`).join(", ");
      g += `<rect class="b ${c}" tabindex="0" role="img" data-tip="${esc(l)}: mean ${(v * 100).toFixed(1)}% (${esc(seeds)}); n = ${esc(r.n.join("/"))} test rows per seed" aria-label="${esc(l)}: ${(v * 100).toFixed(1)} percent accuracy, mean of 3 seeds. ${esc(drop)}" x="${bx}" y="${y(v)}" width="${bw}" height="${(v * ch).toFixed(1)}" rx="8"/>`;
      g += `<text class="vl" x="${bx + bw / 2}" y="${y(v) - 8}" text-anchor="middle">${(v * 100).toFixed(1)}%</text>`;
      g += `<text class="lb" x="${bx + bw / 2}" y="${y0 + ch + 22}" text-anchor="middle">${esc(l)}</text>`;
      if (drop) g += `<text class="dl" x="${bx + bw / 2}" y="${y0 + ch + 40}" text-anchor="middle">${esc(drop)}</text>`;
    });
    const I = C.AxB, Ici = Object.entries(r.loop.I_ci_pp || {});
    const lo = Math.min(0, ...Ici.map(([, c]) => c[0])) - 2, hi = Math.max(0, ...Ici.map(([, c]) => c[1])) + 2;
    const sx = v => 52 + (v - lo) / (hi - lo) * 190;
    let ci = `<line class="z" x1="${sx(0)}" x2="${sx(0)}" y1="4" y2="${16 + Ici.length * 24}"/><text class="t" x="${sx(0)}" y="${28 + Ici.length * 24}" text-anchor="middle">0</text>`;
    let excl = 0;
    Ici.forEach(([s, c], i) => {
      const ex = c[0] > 0 || c[1] < 0; if (ex) excl++;
      const yy = 16 + i * 24;
      ci += `<text class="t" x="0" y="${yy + 4}">seed ${esc(s)}</text><line class="${ex ? "w" : "wd"}" x1="${sx(c[0])}" x2="${sx(c[1])}" y1="${yy}" y2="${yy}"/><text class="t" x="356" y="${yy + 4}" text-anchor="end">[${sg(c[0], 1)}, ${sg(c[1], 1)}]</text>`;
    });
    const [v, extra] = fxVerdict(r);
    const sent = `Fix A alone: drop ${sg(C.A, 1)} pp. Fix B alone: drop ${sg(C.B, 1)} pp. Both: drop ${sg(C.both, 1)} pp. ` +
      (excl === Ici.length && Ici.length ? `The interaction (${sg(I, 1)} pp) is away from 0 on all ${Ici.length} seeds: ${I > 0 ? "the two flaws compound, so fixing either one alone undercounts the inflation." : "the flaws offset each other, so the sum of single fixes overstates the effect."}`
        : `The interaction's interval includes 0 on ${Ici.length - excl} of ${Ici.length} seeds, so there is no clear interaction here.`);
    box.innerHTML = `<div class="fxwrap">
      <div class="panel chart"><div class="row" style="justify-content:space-between"><span class="eyebrow" style="margin:0">Accuracy under each fix · mean of 3 seeds</span>${badge("SYNTHETIC")}</div>
        <svg viewBox="0 0 ${W} ${H}" role="group" aria-label="Four bars: original, fix A only, fix B only, fix both">${g}</svg>
        <p class="small" style="margin:8px 0 0">${esc(sent)}</p><p class="xs muted">Drop = original minus fixed accuracy, in percentage points (pp); positive means the claim was inflated. Hover or tap a bar for the per-seed numbers.</p></div>
      <div class="panel"><p class="eyebrow">Interaction I = drop(both) − drop(A) − drop(B)</p>
        <div class="row" style="align-items:flex-end"><div class="dmI">${DM.svg(sg(I, 1), { pitch: 6, label: "interaction " + sg(I, 1) + " points" })}</div><span class="muted">pp</span>${vchip(v, extra)}</div>
        <div class="ci" style="margin-top:14px"><svg viewBox="0 0 360 ${36 + Ici.length * 24}" role="img" aria-label="95 percent intervals of the interaction per seed">${ci}</svg></div>
        <p class="xs muted">How sure: 95% interval per seed from an unpaired bootstrap (1,000 resamples). Orange = excludes 0 (${excl} of ${Ici.length}).</p>
        <h4 class="small" style="margin:16px 0 4px">Fidelity guard: only the named step changed</h4>
        <ul class="fid">${Object.entries(r.fidelity).map(([k, f]) => `<li>${IC.check}<span>${esc(f)}</span></li>`).join("")}</ul>
        <p class="src">${esc(r.source)} · ${r.retries ? r.retries + " retry" : "no retry"} · truth from the builder's reference patches</p></div></div>`;
    bindTips(box);
  }
  function bindTips(root) {
    const tip = $("#tip");
    const show = (el, x, yy) => { tip.textContent = el.dataset.tip; tip.classList.add("on"); const w = tip.offsetWidth; tip.style.left = clamp(x - w / 2, 8, innerWidth - w - 8) + "px"; tip.style.top = (yy - tip.offsetHeight - 12) + "px"; };
    const hide = () => tip.classList.remove("on");
    $$("[data-tip]", root).forEach(el => {
      el.addEventListener("mousemove", e => show(el, e.clientX, e.clientY));
      el.addEventListener("mouseleave", hide);
      el.addEventListener("focus", () => { const b = el.getBoundingClientRect(); show(el, b.left + b.width / 2, b.top); });
      el.addEventListener("blur", hide);
      el.addEventListener("click", () => { const b = el.getBoundingClientRect(); tip.classList.contains("on") ? hide() : show(el, b.left + b.width / 2, b.top); });
    });
  }

  /* ------------------------------------------------------------------ reading vs running */
  function mark3(state, word) {
    const m = { right: [IC.check, "RIGHT"], wrong: [IC.x, "WRONG"], na: [IC.dash, "NOT SCORED"] }[state];
    return `<span class="m ${state}">${m[0]}${word || m[1]}</span>`;
  }
  function renderVs() {
    const r = D.factorial[S.fx], b = r.b3, L = r.loop, tr = r.truth, box = $("#vsBody");
    let readItems, runItems, runSay;
    if (r.clean) {
      const fa = b.verdict === "INFLATED";
      readItems = `<li>${mark3(fa ? "wrong" : "right", fa ? "FALSE ALARM" : "RIGHT")}<span>Verdict: ${esc(b.verdict)} on a pipeline that is correct.</span></li>`;
      runItems = r.status === "ok" ? `<li>${mark3(L.false_alarm ? "wrong" : "right", L.false_alarm ? "FALSE ALARM" : "RIGHT")}<span>Sign per seed ${esc((L.per_seed || []).join(" "))} → ${L.sign === "+" ? "inflated" : "not inflated"}.</span></li>` :
        `<li>${mark3("na", "INCONCLUSIVE")}<span>No measurement (guard or run failed after one retry).</span></li>`;
    } else {
      readItems = `<li>${mark3(b.sign_wrong ? "wrong" : "right")}<span>Sign: predicted ${esc(b.sign)} (truth ${esc(tr.sign)}).</span></li>
        <li>${mark3(b.verdict_wrong ? "wrong" : "right")}<span>Verdict: ${esc(b.verdict)} (truth ${esc(tr.verdict)}).</span></li>
        <li>${tr.culprit ? mark3(b.culprit_wrong ? "wrong" : "right") : mark3("na")}<span>Ranking: top culprit ${esc(b.culprit_mapped || b.culprit_raw)}${tr.culprit ? " (truth " + esc(tr.culprit) + ")" : " (no single culprit in the truth)"}.</span></li>`;
      runItems = r.status === "ok" ? `<li>${mark3(L.correct ? "right" : "wrong")}<span>Sign: measured ${esc(L.sign)} (seeds ${esc((L.per_seed || []).join(" "))}; truth ${esc(tr.sign)}).</span></li>
        <li>${mark3(L.correct ? "right" : "wrong")}<span>Verdict follows the sign: ${L.sign === "+" ? "INFLATED" : "NOT INFLATED"}.</span></li>
        <li>${mark3("na")}<span>Ranking: measured culprit ${esc(L.measured_culprit)} in the planner's own A/B labels; the rule does not score it.</span></li>`
        : `<li>${mark3("wrong", "INCONCLUSIVE")}<span>No measurement; counted as wrong.</span></li>`;
    }
    runSay = r.status === "ok" ? `measured a fix-both drop of ${sg(L.components_pp.both, 1)} pp` : "could not measure this repeat";
    const size = `<li>${mark3("na")}<span>Size: reading ${sg(b.fix_both_pp, 1)} pp, running ${r.status === "ok" ? sg(L.components_pp.both, 1) + " pp" : "n/a"}${tr.both != null ? ", truth " + sg(tr.both, 1) + " pp" : ""}. G5 does not score size.</span></li>`;
    box.innerHTML = `<div class="vs">
      <div class="card"><p class="eyebrow">Reading only · one prompt, no execution</p>
        <p class="say">“Fixing it would drop accuracy by ${sg(b.fix_both_pp, 1)} pp: ${esc(b.verdict)}.”</p><ul class="chk">${readItems}${size}</ul></div>
      <div class="card run"><p class="eyebrow">NullLab · ran the guarded fixes</p>
        <p class="say">It ${esc(runSay)}.</p><ul class="chk">${runItems}${size}</ul></div></div>
      <p class="xs muted" style="margin-top:12px">${badge("SYNTHETIC")} ${esc(r.case)} · repeat ${r.repeat} · ${r.clean ? "correct pipeline (truth: no inflation)" : "truth from the builder's reference patches (runs_g4/ref.json)"} · ${src("runs_g5/score.json")}</p>`;
  }

  /* ------------------------------------------------------------------ real + textbook cases (G6) */
  function link(text) {
    const m = String(text || "").match(/https?:\/\/[^\s;,)]+/) || String(text || "").match(/doi:(10\.[^\s;,)]+)/);
    if (!m) return "";
    const href = m[0].startsWith("http") ? m[0] : "https://doi.org/" + m[1];
    return `<a href="${esc(href)}" target="_blank" rel="noopener noreferrer">${esc(m[0])}</a>`;
  }
  function renderReal() {
    const R = D.real, box = $("#realBody");
    if (!R) { box.innerHTML = `<div class="empty">No G6 run files found (runs_g6/).</div>`; return; }
    const tol = R.tol, acc = R.acceptance;
    const card = (key) => {
      const c = R.cases[key], P = c.published, isCW = key === "civilwar_apparent";
      const maxX = Math.max(P.inflation + tol, ...c.reps.map(r => r.inflation || 0), ...c.reps.flatMap(r => (r.ci || []).map(x => x[1]))) + 0.05;
      const minX = Math.min(0, ...c.reps.flatMap(r => (r.ci || []).map(x => x[0]))) - 0.02;
      const sx = v => 60 + (v - minX) / (maxX - minX) * 300;
      let g = `<rect x="${sx(P.inflation - tol)}" y="0" width="${sx(P.inflation + tol) - sx(P.inflation - tol)}" height="${c.reps.length * 34 + 8}" fill="var(--accent-soft)"/>`;
      g += `<line x1="${sx(P.inflation)}" x2="${sx(P.inflation)}" y1="0" y2="${c.reps.length * 34 + 8}" stroke="var(--accent)" stroke-width="2" stroke-dasharray="4 3"/>`;
      g += `<line x1="${sx(0)}" x2="${sx(0)}" y1="0" y2="${c.reps.length * 34 + 8}" stroke="var(--line-2)"/>`;
      c.reps.forEach((r, i) => {
        const yy = 20 + i * 34;
        (r.ci || []).forEach((ci, j) => { g += `<line x1="${sx(ci[0])}" x2="${sx(ci[1])}" y1="${yy - 6 + j * 6}" y2="${yy - 6 + j * 6}" stroke="var(--faint)" stroke-width="2" stroke-linecap="round"/>`; });
        g += r.magnitude_ok ? `<circle cx="${sx(r.inflation)}" cy="${yy}" r="7" fill="var(--ink)"/>` : `<circle cx="${sx(r.inflation)}" cy="${yy}" r="6.5" fill="var(--panel)" stroke="var(--accent)" stroke-width="3"/>`;
        g += `<text x="0" y="${yy + 4}" fill="var(--muted)" style="font:500 12px var(--f-mono)">${esc(r.r)}</text>`;
        g += `<text x="372" y="${yy + 4}" fill="var(--ink)" style="font:600 12px var(--f-mono)">${sg(r.inflation, 3)} ${r.magnitude_ok ? "within" : "outside"}</text>`;
      });
      const H = c.reps.length * 34 + 30;
      g += `<text x="${sx(P.inflation)}" y="${H - 4}" text-anchor="middle" fill="var(--accent-ink)" style="font:500 11px var(--f-mono)">published ${sg(P.inflation, 2)} ±${tol}</text>`;
      const within = c.reps.filter(r => r.magnitude_ok).length, dir = c.reps.filter(r => r.sign === "+").length;
      const b3 = c.reps.map(r => sg(r.b3_pp, 0)).join(" / "), b3n = c.reps.filter(r => r.b3_gets).length;
      const pr = (R.probe || {})[key] || {};
      const ex = pr.excerpt_only || {}, fu = pr.full_agent_view || {};
      return `<article class="card">
        <div class="row">${badge(c.provenance)}<span class="badge LIVE">LIVE muse-spark-1.3 · 3 repeats</span></div>
        <h3>${esc(c.label)}</h3>
        <p class="small muted" style="margin:0">${esc(c.flaw)}</p>
        <div class="pub"><div><div class="c">${isCW ? "published apparent" : "book: wrong-way CV"}</div><div class="v">${esc(P.claimed)}</div></div>
          <div><div class="c">${isCW ? "published corrected" : "book: true"}</div><div class="v">${esc(P.corrected)}</div></div>
          <div><div class="c">published inflation (${esc(c.metric)})</div><div class="v" style="color:var(--accent-ink)">${sg(P.inflation, 2)}</div></div></div>
        <p class="eyebrow" style="margin-top:8px">NullLab measured inflation per repeat (dot = mean of 3 seeds, lines = per-seed 95% intervals)</p>
        <svg viewBox="0 0 490 ${H}" style="width:100%;height:auto" role="img" aria-label="Measured inflation per repeat against the published value ${sg(P.inflation, 2)} with a tolerance of ${tol}">${g}</svg>
        <p class="small"><b>Direction right in ${dir}/${c.reps.length}; size within ±${tol} of published in ${within}/${c.reps.length}.</b> Reading alone (one prompt) predicted ${esc(b3)} points and matched in ${b3n}/${c.reps.length}.</p>
        ${isCW ? `<div class="note wrong"><b>What it got wrong</b>Its fix replaced in-sample scoring with a random stratified 80/20 hold-out, not the temporal hold-out that a forecasting claim needs and that the reanalysis used. So it under-measured: ${c.reps.map(r => sg(r.inflation, 3)).join(" / ")} against the published ${sg(P.inflation, 2)}. The preregistered acceptance FAILED on this clause (${esc(acc.a_civilwar_reproduces)}). <span class="src">docs/EVAL-6.md §4–5</span></div>` : ""}
        <div class="note"><b>Contamination</b>The model recognises this source. Asked from the excerpt alone it answered “${esc(ex.answer)}”; from the full view, “${esc(fu.answer)}”. This case cannot prove that running beats remembering. <span class="src">runs_g6/probe.json</span></div>
        <p class="src" style="margin-top:12px">${isCW ? "Original: " + esc(c.original) + "<br>Correction: " : "Source: "}${esc(String(c.reanalysis).split(";")[0].split(" (PDF")[0])} ${link(c.reanalysis)}</p>
      </article>`;
    };
    const cl = R.clean, row = (k, lab) => (cl[k] || []).map(r => `${esc(r.r)}: ${r.sign === "INCONCLUSIVE" ? "INCONCLUSIVE" : esc(r.sign) + " (" + sg(r.inflation, 3) + ")"}`).join(", ");
    const b3c = k => (cl[k] || []).filter(r => r.b3_leak).length + "/" + (cl[k] || []).length;
    box.innerHTML = `<div class="grid2 real">${card("civilwar_apparent")}${card("esl_selection")}</div>
      <div class="panel" style="margin-top:16px"><p class="eyebrow">The corrected versions of both pipelines</p>
        <div class="tw"><table class="seeds"><thead><tr><th>case</th><th>NullLab (sign per repeat)</th><th>reading only: called it leaky</th></tr></thead><tbody>
        <tr><td>Civil war, temporal hold-out ${badge("REAL-PINNED")}</td><td>${row("civilwar_temporal_clean")}</td><td>${b3c("civilwar_temporal_clean")}</td></tr>
        <tr><td>ESL, screening inside folds ${badge("TEXTBOOK")}</td><td>${row("esl_selection_clean")}</td><td>${b3c("esl_selection_clean")}</td></tr></tbody></table></div>
        <p class="xs muted">Loop false alarms ${esc(acc.c_clean_false_alarms)} (${esc(acc.clean_inconclusive)} INCONCLUSIVE); reading-only false alarms ${esc(acc.b3_clean_false_alarms)}. Preregistered G6 acceptance: <b>${acc.PASS ? "PASS" : "FAIL"}</b> · rule sha256 ${esc(R.rule_sha.slice(0, 16))} · ${src(R.source)}</p></div>`;
  }

  /* ------------------------------------------------------------------ stats strip + scoreboard */
  function renderStats() {
    const box = $("#statsBody");
    if (!D.stats || !D.stats.length) { box.innerHTML = `<div class="empty">No measured numbers found.</div>`; return; }
    box.innerHTML = D.stats.map((s, i) => `<div class="stat"><div class="dmN" data-v="${esc(s.value)}" id="st${i}">${DM.svg(RM ? s.value : s.value.replace(/^\d+/, "0"), { pitch: 6, label: s.value })}</div>
      <p>${esc(s.caption)} <span class="muted">(n = ${esc(s.value.split("/")[1])})</span></p><p class="s">${esc(s.sub)}</p><div class="row" style="gap:6px">${s.badges.map(badge).join("")}</div><p class="src" style="margin-top:6px">${esc(s.src)}</p></div>`).join("");
    if (RM) return;
    const run = el => {
      const v = el.dataset.v, m = v.match(/^(\d+)(.*)$/); if (!m) return;
      const target = +m[1], t0 = performance.now();
      const step = now => { const p = clamp((now - t0) / 900, 0, 1), cur = Math.round(target * ease(p)); el.innerHTML = DM.svg(cur + m[2], { pitch: 6, label: v }); if (p < 1) requestAnimationFrame(step); };
      requestAnimationFrame(step);
    };
    const els = $$(".dmN", box);
    if ("IntersectionObserver" in window) {
      const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { run(e.target); io.unobserve(e.target); } }), { threshold: .4 });
      els.forEach(e => io.observe(e));
    } else els.forEach(run);
  }
  function renderScore() {
    const sb = D.scoreboard, box = $("#scoreBody");
    box.innerHTML = `<div class="panel"><div class="tw"><table class="sb"><thead><tr><th>evaluation</th><th>measure</th><th>NullLab loop</th><th>reading only (B3)</th><th>note</th></tr></thead><tbody>
      ${sb.rows.map(r => `<tr><td class="e"><b>${esc(r.eval)}</b><div class="row" style="gap:4px;margin-top:6px">${r.badges.map(badge).join("")}</div></td><td data-h="measure">${esc(r.metric)}</td><td class="n" data-h="loop">${esc(r.loop)}</td><td class="n" data-h="reading">${esc(r.b3)}</td><td data-h="note"><span class="small">${esc(r.note)}</span><div class="src">${esc(r.src)}</div></td></tr>`).join("")}
      </tbody></table></div>
      <p class="eyebrow" style="margin-top:28px">Off-the-shelf checkers on the same 9 blind inputs (data only)</p>
      <div class="tw"><table class="sb"><thead><tr><th>tool</th><th>flag rule</th><th>recall (6 leaky)</th><th>false alarms (3 correct)</th></tr></thead><tbody>
      ${sb.tools.map(t => `<tr><td class="e"><b>${esc(t.tool)}</b></td><td data-h="rule">${esc(t.rule)}</td><td class="n" data-h="recall">${esc(t.recall)}</td><td class="n" data-h="false alarms">${esc(t.fa)}</td></tr>`).join("")}
      </tbody></table></div><p class="src">${esc(sb.tools_src)}. Neither tool can see code-level leaks or estimate an interaction.</p>
      <div class="caveat" role="note">${IC.info}<span><b>Not a population estimate.</b> These are counts on cases we built or picked (n shown in every cell), not rates you can expect in the wild. Reading only does better than the loop on the two famous real cases, and the model recognises both.</span></div></div>`;
  }

  /* ------------------------------------------------------------------ limits drawer, help, toast */
  function renderLimits() {
    const mock = (D.mock_cases || []).map(c => `<a href="${esc(c)}.html">${esc(c)}</a>`).join(", ");
    $("#limitsBody").innerHTML = `
      <h3>${badge("SYNTHETIC")} What is synthetic</h3><ul>
        <li>The 2×2 factorial, the hard cases and the reading-vs-running cards: 8 cases we generated with planted flaws, 3 repeats each. Counts, not rates.</li>
        <li>Repeats ran at temperature 0, so they are only weakly independent (hard-case numbers were identical across repeats).</li>
        <li>The EVAL-2 corpus uses real UCI data in 3 cases, but every pipeline and flaw was written by us.</li></ul>
      <h3>${badge("REAL-PINNED")} What is real, and its limits</h3><ul>
        <li>Civil war: a Python port of the published R pipeline on the pinned Dataverse file (300 trees instead of 1,000; PR-AUC via scikit-learn average precision).</li>
        <li>A second documented flaw in that paper (outcome-aware imputation, Kapoor &amp; Narayanan 2023) is baked into the data file and is not corrected here.</li>
        <li>The model recognises both famous sources (memorisation probe), so they cannot separate experiment from recall.</li></ul>
      <h3>${badge("TEXTBOOK")} Textbook case</h3><ul><li>ESL §7.10.2 is one random draw (seed 7) of the book's setting, not a reanalysis of a paper. n = 50, so intervals are wide.</li></ul>
      <h3>UNVERIFIED</h3><ul><li>ROC-AUC values read off the reanalysis' Figure 1 (about 0.97 → 0.89).</li><li>Whether the civil-war variables the planner wanted to drop really leak: the guard blocked that experiment.</li></ul>
      <h3>Known gaps in the guard</h3><ul><li>It checks that a fix stays inside its declared step, not that the fix is the right one. It does not require a temporal split for a forecasting claim.</li>
        <li>One synthetic false alarm (clean_wine_correct, repeat 2) came from a declared but unjustified fix.</li></ul>
      <h3>Engineering</h3><ul><li>The sandbox is a restricted subprocess (network cut, timeout, evaluator paths blocked), not a locked container.</li><li>No model is called by this page; it shows recorded runs.</li></ul>
      <h3>${badge("MOCK")} Mock runs (muted on purpose)</h3><p class="mocklist">runs/*.json are produced by a scripted regex stand-in that only exercises the plumbing. They are never model results and never appear in a headline. Per-case pages: ${mock}</p>
      <p class="src" style="margin-top:20px">Sources: docs/EVAL-5.md, docs/EVAL-6.md, docs/KILL-LOG.md, README.md</p>`;
  }
  let lastFocus = null;
  function openLimits() { lastFocus = document.activeElement; $("#scrim").classList.add("on"); const d = $("#limits"); d.classList.add("on"); d.removeAttribute("inert"); d.setAttribute("aria-hidden", "false"); $("#closeLimits").focus(); }
  function closeLimits() { $("#scrim").classList.remove("on"); const d = $("#limits"); d.classList.remove("on"); d.setAttribute("inert", ""); d.setAttribute("aria-hidden", "true"); if (lastFocus) lastFocus.focus(); }
  function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("on"); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("on"), 2400); }

  /* ------------------------------------------------------------------ copy summary, download report */
  function summary() {
    const h = hero(), lines = [];
    lines.push(`NullLab: ${h.short} [${h.provenance.join(", ")}] ${h.verdict}. Claimed ${fv(h.start.value, h.unit)} (${h.start.label}); measured ${fv(h.end ? h.end.value : null, h.unit)}${h.n_text ? " (" + h.n_text + ")" : ""}. Source: ${h.source}.`);
    if (D.g5) { const a = D.g5.acceptance; lines.push(`G5 [SYNTHETIC, 8 cases x 3 repeats]: loop direction right on hard runs ${a.ii_hard_sign_correct} (reading only wrong ${a.iii_b3_wrong_hard}); false alarms on correct pipelines ${a.i_clean_false_alarms} (reading only ${a.b3_clean_false_alarms}). runs_g5/score.json`); }
    if (D.real) {
      const cw = D.real.cases.civilwar_apparent, es = D.real.cases.esl_selection, a = D.real.acceptance;
      lines.push(`Civil war [REAL-PINNED]: direction right ${cw.reps.filter(r => r.sign === "+").length}/${cw.reps.length}; inflation ${cw.reps.map(r => sg(r.inflation, 3)).join(" / ")} vs published ${sg(cw.published.inflation, 2)}; within +-${D.real.tol} in ${a.a_civilwar_reproduces}. Preregistered acceptance FAILED on this clause.`);
      lines.push(`ESL 7.10.2 [TEXTBOOK]: ${es.reps.map(r => sg(r.inflation, 3)).join(" / ")} vs published ${sg(es.published.inflation, 2)}, ${a.b_esl_reproduces}. Corrected pipelines: loop false alarms ${a.c_clean_false_alarms}, reading only ${a.b3_clean_false_alarms}.`);
      lines.push("Contamination: the model recognises both sources, so these cases cannot show that running beats remembering. Counts on cases we built or picked; not a population estimate.");
    }
    lines.push(location.href);
    return lines.join("\n");
  }
  function copySummary() {
    const txt = summary();
    const fallback = () => { const ta = document.createElement("textarea"); ta.value = txt; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0"; document.body.appendChild(ta); ta.select(); let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; } ta.remove(); toast(ok ? "Summary copied" : "Copy blocked by the browser"); };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(txt).then(() => toast("Summary copied"), fallback); else fallback();
  }
  function reportHtml() {
    const td = s => `<td>${esc(s)}</td>`;
    const heroes = D.heroes.map(h => `<tr>${td(h.label)}${td(h.provenance.join(", "))}${td(fv(h.start.value, h.unit) + " (" + h.start.label + ")")}${td(fv(h.end ? h.end.value : null, h.unit))}${td(h.verdict)}${td(h.n_text)}${td(h.source)}</tr>`).join("");
    const stats = (D.stats || []).map(s => `<tr>${td(s.value)}${td(s.caption)}${td(s.sub)}${td(s.badges.join(", "))}${td(s.src)}</tr>`).join("");
    const score = D.scoreboard.rows.map(r => `<tr>${td(r.eval)}${td(r.badges.join(", "))}${td(r.metric)}${td(r.loop)}${td(r.b3)}${td(r.note)}${td(r.src)}</tr>`).join("");
    const tools = D.scoreboard.tools.map(t => `<tr>${td(t.tool)}${td(t.rule)}${td(t.recall)}${td(t.fa)}</tr>`).join("");
    let real = "";
    if (D.real) real = Object.values(D.real.cases).map(c => `<h3>${esc(c.label)} [${esc(c.provenance)}]</h3><p>Published ${esc(c.published.claimed)} → ${esc(c.published.corrected)} (inflation ${sg(c.published.inflation, 2)} ${esc(c.metric)}). Source: ${esc(c.reanalysis)}</p><table><tr><th>repeat</th><th>sign</th><th>measured inflation</th><th>within ±${D.real.tol}</th><th>reading only (points)</th></tr>${c.reps.map(r => `<tr>${td(r.r)}${td(r.sign)}${td(sg(r.inflation, 3))}${td(r.magnitude_ok ? "yes" : "no")}${td(sg(r.b3_pp, 0))}</tr>`).join("")}</table>`).join("");
    const css = "body{font:15px/1.5 system-ui,sans-serif;max-width:960px;margin:32px auto;padding:0 16px;color:#111;background:#fff}h1{font-weight:400}table{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0 20px}td,th{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}th{color:#666;font-weight:500}.n{border:1px solid #E8501F;border-radius:12px;padding:10px 14px;background:#FCE9E1}";
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>NullLab report</title><style>${css}</style></head><body>
      <h1>NullLab report</h1><p>Reading an AI's answer is cheap. Measuring it is the work. Generated from the run files ${esc(D.generated_utc)}; exported ${esc(new Date().toISOString().slice(0, 16).replace("T", " "))} UTC.</p>
      <h2>Claims re-evaluated</h2><table><tr><th>case</th><th>provenance</th><th>claimed</th><th>measured</th><th>verdict</th><th>n</th><th>source</th></tr>${heroes}</table>
      <h2>Measured counts</h2><table><tr><th>value</th><th>what</th><th>alongside</th><th>provenance</th><th>source</th></tr>${stats}</table>
      <h2>Real and textbook cases</h2>${real}
      <p class="n"><b>Contamination.</b> The language model recognises both sources (runs_g6/probe.json). These two cases cannot prove that running beats remembering. NullLab does not claim to reproduce published corrections.</p>
      <h2>Scoreboard (counts, not a population estimate)</h2><table><tr><th>evaluation</th><th>provenance</th><th>measure</th><th>loop</th><th>reading only</th><th>note</th><th>source</th></tr>${score}</table>
      <table><tr><th>tool</th><th>rule</th><th>recall</th><th>false alarms</th></tr>${tools}</table><p>${esc(D.scoreboard.tools_src)}</p>
      <h2>Limits</h2>${$("#limitsBody").innerHTML.replace(/<span class="badge[^>]*>([^<]*)<\/span>/g, "[$1]")}
      <p>Test suite: ${esc(D.tests_doc.value)} (${esc(D.tests_doc.src)}).</p></body></html>`;
  }
  function download() {
    try {
      const blob = new Blob([reportHtml()], { type: "text/html" });
      const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = "nulllab-report.html";
      document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500);
      toast("Report downloaded (one self-contained HTML file)");
    } catch (e) { toast("Download failed: " + e.message); }
  }

  /* ------------------------------------------------------------------ theme, keyboard, nav */
  function curTheme() { const t = document.documentElement.dataset.theme; if (t) return t; return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  function syncTheme() { const t = curTheme(), b = $("#btnTheme"); b.setAttribute("aria-label", t === "dark" ? "Switch to light theme" : "Switch to dark theme"); b.innerHTML = t === "dark" ? '<svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="3.2" fill="currentColor"/><path d="M8 1v2M8 13v2M1 8h2M13 8h2M3 3l1.4 1.4M11.6 11.6L13 13M3 13l1.4-1.4M11.6 4.4L13 3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>' : '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M13 9.5A5.5 5.5 0 0 1 6.5 3a5.5 5.5 0 1 0 6.5 6.5z" fill="currentColor"/></svg>'; }
  function toggleTheme() { const n = curTheme() === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = n; store.set("nl-theme", n); syncTheme(); }

  function keys(e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (["input", "select", "textarea"].includes(tag)) return;
    const dlg = $("#help");
    if (e.key === "Escape") { if ($("#limits").classList.contains("on")) closeLimits(); return; }
    if (dlg.open) return;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { if (e.target.closest && (e.target.closest("pre") || e.target.closest(".tw"))) return; e.preventDefault(); stepCase(e.key === "ArrowRight" ? 1 : -1); }
    else if (e.key === " " && !["button", "summary", "a"].includes(tag)) { e.preventDefault(); TL.playing ? pause() : play(); }
    else if (e.key === "?") { e.preventDefault(); dlg.showModal ? dlg.showModal() : dlg.setAttribute("open", ""); }
    else if (e.key === "r" || e.key === "R") replay();
    else if (e.key === "s" || e.key === "S") skip();
    else if (e.key === "t" || e.key === "T") toggleTheme();
    else if (e.key === "l" || e.key === "L") openLimits();
  }
  function trapLimits(e) {
    if (e.key !== "Tab" || !$("#limits").classList.contains("on")) return;
    const f = $$("#limits a, #limits button").filter(x => x.offsetParent !== null);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  }
  function navSpy() {
    if (!("IntersectionObserver" in window)) return;
    const links = $$(".nav a");
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) links.forEach(a => a.setAttribute("aria-current", String(a.getAttribute("href") === "#" + e.target.id))); }), { rootMargin: "-40% 0px -55% 0px" });
    $$("main section[id]").forEach(s => io.observe(s));
  }

  /* ------------------------------------------------------------------ data loading */
  function setStatus(kind, html) { const s = $("#dataStatus"); s.className = "status " + kind; s.innerHTML = `<i></i><span>${html}</span>`; }
  async function load() {
    const EMB = window.__NL_DATA || null;
    if (/^https?:$/.test(location.protocol)) {
      try {
        const ctl = "AbortController" in window ? new AbortController() : null;
        const to = setTimeout(() => ctl && ctl.abort(), 2500);
        const r = await fetch("/api/demo", { cache: "no-store", signal: ctl ? ctl.signal : undefined });
        clearTimeout(to);
        if (!r.ok) throw new Error("HTTP " + r.status);
        const d = await r.json();
        setStatus("live", `Live API: read from the run files just now (${esc(d.generated_utc)})`);
        return d;
      } catch (e) {
        if (EMB) { setStatus("err", `API offline: showing the run data embedded at build time (${esc(EMB.generated_utc)})`); return EMB; }
        throw e;
      }
    }
    if (EMB) { setStatus("", `Opened as a file: showing the run data embedded at build time (${esc(EMB.generated_utc)})`); return EMB; }
    throw new Error("no embedded data");
  }

  function wire() {
    $("#btnReplay").addEventListener("click", replay);
    $("#btnPause").addEventListener("click", () => TL.playing ? pause() : play());
    $("#btnSkip").addEventListener("click", skip);
    $$("#speed button").forEach(b => b.addEventListener("click", () => { TL.speed = +b.dataset.s; syncCtrl(); }));
    $("#btnCopy").addEventListener("click", copySummary);
    $("#btnDownload").addEventListener("click", download);
    $("#btnTheme").addEventListener("click", toggleTheme);
    $$("[data-open-limits]").forEach(b => b.addEventListener("click", openLimits));
    $("#closeLimits").addEventListener("click", closeLimits);
    $("#scrim").addEventListener("click", closeLimits);
    $("#btnHelp").addEventListener("click", () => { const d = $("#help"); d.showModal ? d.showModal() : d.setAttribute("open", ""); });
    $("#closeHelp").addEventListener("click", () => { const d = $("#help"); d.close ? d.close() : d.removeAttribute("open"); });
    document.addEventListener("keydown", keys);
    document.addEventListener("keydown", trapLimits);
    let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(() => drawHero(false), 120); });
    if (window.matchMedia) { const mq = matchMedia("(prefers-color-scheme: dark)"); (mq.addEventListener ? mq.addEventListener.bind(mq, "change") : mq.addListener.bind(mq))(syncTheme); }
  }

  async function init() {
    drawHero(true); syncTheme(); wire(); readHash();
    try { D = await load(); }
    catch (e) {
      setStatus("err", "Could not load run data: " + esc(e.message));
      $("#wowBody").innerHTML = `<div class="empty">No run data available. Run <code>python -m report.render</code> to embed it, or start the API with <code>uvicorn app.server:app</code>.</div>`;
      return;
    }
    if (!D.heroes || !D.heroes.length) { $("#wowBody").innerHTML = `<div class="empty">No claims found in the run files.</div>`; return; }
    if (!D.heroes.some(h => h.id === S.case)) S.case = D.heroes[0].id;
    renderCases(); renderWow(); renderStats(); renderLimits();
    if (renderFactorialShell()) selectFx(S.fx);
    renderReal(); renderScore(); navSpy(); writeHash(); syncCtrl();
    if (S.step) { /* deep link to a step */ renderDetail(); }
    setTimeout(replay, RM ? 0 : 250);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
