/* NullLab page. Plain JS, no external requests. Data: window.__NL_DATA (embedded at render time) or /api/demo (optional fetch).
   One animation clock (the rAF loop below). Everything else is a CSS transition on a class flip. */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const V = window.NLV, esc = V.esc, num = V.num, badge = V.badge, IC = V.IC, fmt = V.fmt;
  const RM = !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  const clamp = (x, a, b) => Math.max(a, Math.min(b, x));
  const store = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* blocked */ } } };
  let D = null;

  /* ------------------------------------------------------------------ easing */
  function bezier(x1, y1, x2, y2) {   // CSS cubic-bezier
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx, cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const X = t => ((ax * t + bx) * t + cx) * t, Y = t => ((ay * t + by) * t + cy) * t;
    return x => { let t = x; for (let i = 0; i < 8; i++) { const e = X(t) - x, d = (3 * ax * t + 2 * bx) * t + cx; if (Math.abs(e) < 1e-5 || !d) break; t -= e / d; } return Y(clamp(t, 0, 1)); };
  }
  const eSweep = bezier(.2, .7, .2, 1);
  const eQuint = p => 1 - Math.pow(1 - p, 5);
  const eSettle = p => { const u = p - 1; return 1 + 2 * u * u * u + u * u; };   // one overshoot of about 4 percent

  /* ------------------------------------------------------------------ the clock: players share one rAF loop */
  const clock = { raf: 0, last: null, players: [] };
  function player(end, paint) { const p = { t: 0, end, playing: false, paint, done: null }; clock.players.push(p); return p; }
  function tick(now) {
    clock.raf = 0;
    if (clock.last == null) clock.last = now;
    const dt = Math.min(400, now - clock.last); clock.last = now;
    let any = false;
    clock.players.forEach(p => {
      if (!p.playing) return;
      p.t = Math.min(p.end, p.t + dt); p.paint(p.t);
      if (p.t >= p.end) { p.playing = false; if (p.done) p.done(); } else any = true;
    });
    if (any) clock.raf = requestAnimationFrame(tick); else clock.last = null;
  }
  function start(p, from) {
    if (RM) { p.t = p.end; p.playing = false; p.paint(p.end); if (p.done) p.done(); return; }
    p.t = from == null ? 0 : from; p.playing = true; p.paint(p.t);
    if (!clock.raf) { clock.last = null; clock.raf = requestAnimationFrame(tick); }
  }
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) { if (clock.raf) cancelAnimationFrame(clock.raf); clock.raf = 0; clock.last = null; }
    else if (clock.players.some(p => p.playing) && !clock.raf) clock.raf = requestAnimationFrame(tick);
  });

  /* ------------------------------------------------------------------ hero timeline: connectors, nodes, count-down + ring, verdict */
  const T = { CX: 0, CXD: 800, N0: 900, ND: 180, CNT: 1900, CNTD: 1100, VERD: 3050, END: 3300 };
  const hero = player(T.END, paintHero);
  let H = {};   // cached elements
  function paintHero(t) {
    if (!H.big) return;
    const sw = 1 - eSweep(clamp((t - T.CX) / T.CXD, 0, 1));
    H.cx.forEach(c => c.style.strokeDashoffset = sw);
    const nN = H.nodes.length;
    H.nodes.forEach((g, i) => {
      const a = T.N0 + i * T.ND;
      g.classList.toggle("on", i === nN - 1 ? t >= a : t >= a && t < a + T.ND);
    });
    H.cx.forEach((c, i) => c.classList.toggle("act", t >= T.N0 + (i + 1) * T.ND));
    $$(".flow-v li").forEach((li, i) => li.style.opacity = t >= T.N0 + i * T.ND ? 1 : .55);
    const p = eQuint(clamp((t - T.CNT) / T.CNTD, 0, 1)), a = H.claimed, b = H.measured;
    H.big.textContent = (a + (b - a) * p).toFixed(3);
    H.ring.setAttribute("transform", `translate(120 120) scale(${(1 + (b / a - 1) * p).toFixed(4)})`);
    const on = t >= T.VERD;
    H.verdict.classList.toggle("on", on);
    if (on && !H.said) { H.said = true; $("#live").textContent = H.sentence; }
    H.scrub.value = t;
  }
  hero.done = () => { if (H.verdict) H.verdict.classList.add("settled"); const b = $("#btnPlay"); if (b) b.textContent = "Play"; };
  function replay() {
    H.said = false; $("#live").textContent = "";
    if (H.verdict) H.verdict.classList.toggle("settled", true);
    start(hero, 0); start(needle, 0);
  }
  function skip() { hero.playing = false; hero.t = T.END; paintHero(T.END); needle.playing = false; needle.t = needle.end; paintNeedle(needle.end); termP.playing = false; termP.t = termP.end; paintTerm(termP.end); }

  /* ------------------------------------------------------------------ needle: seeds 42/43/44 light, then settle from claimed to measured */
  const needle = player(1500, paintNeedle);
  function paintNeedle(t) {
    const n = $("#needle"); if (!n) return;
    $$("#seeds circle").forEach((c, i) => c.classList.toggle("on", t >= i * 150));
    const s = +n.dataset.s, e = +n.dataset.a, p = clamp((t - 600) / 900, 0, 1);
    n.setAttribute("transform", `rotate(${(s + (e - s) * eSettle(p)).toFixed(2)})`);
  }

  /* ------------------------------------------------------------------ terminal: reveals the recorded run in about 1.2 s */
  const termP = player(1200, paintTerm);
  let TERM = { lines: [] };
  function paintTerm(t) {
    const body = $("#termBody"); if (!body) return;
    const n = TERM.lines.length, k = Math.max(1, Math.ceil(n * clamp(t / 1200, 0, 1)));
    $$(".ln", body).forEach((l, i) => l.style.visibility = i < k ? "visible" : "hidden");
    const sk = $("#termSkip"); if (sk) sk.hidden = t >= termP.end;
  }

  /* ------------------------------------------------------------------ render */
  const SEC = (id, kick, h2, inner) => `<section class="sec" id="${id}" aria-labelledby="${id}-h"><div class="wrap"><span class="cap kicker">${kick}</span><h2 id="${id}-h">${h2}</h2>${inner}</div></section>`;

  function renderHero() {
    const G = D.g8, g7 = D.g7;
    if (!G || !G.claimed) { $("#heroBody").innerHTML = `<p class="muted">No scored run files found yet (runs_g8/).</p>`; return; }
    const claimed = G.claimed.k, measured = G.controlled.k;
    $("#flowBox").innerHTML = V.flow(D);
    $("#heroBody").innerHTML = `<div class="moment">
      <div><div class="cap">Claim's own protocol, re-run &rarr; controlled re-evaluation &middot; PR-AUC</div>
        <div class="bignum num" id="big" aria-hidden="true">${esc(fmt(G.claimed, "v3"))}</div>
        <p class="line">Claimed <b>${num(D, "g8.claimed", "v3")}</b>, measured <b>${num(D, "g8.controlled", "v3")}</b>. Mean of <b>${num(D, "g8.claimed", "n")}</b> executed repeats x 3 seeds ${badge(G.claimed.badge)} <span class="faint xs">${esc(G.claimed.src)}</span></p>
        <div class="verdict" id="verdict">${V.vd("FALSIFIED")}<span class="xs muted" style="max-width:34ch">Scored on the rows it was trained on; the controlled score is time-ordered.</span></div></div>
      <div class="rings-m"><svg viewBox="0 0 240 240" role="img" aria-label="Two rings: the outer ring is the claimed score, the inner ring the measured score, drawn to the same scale.">
        <g transform="translate(120 120)"><circle class="rm-ax" r="112"/></g>
        <g id="ringOuter" transform="translate(120 120) scale(1)"><circle class="rm-outer" r="108"/></g>
        <g transform="translate(120 120)"><circle class="rm-inner" r="${(108 * measured / claimed).toFixed(2)}"/></g>
        <text class="rm-t" x="120" y="14" text-anchor="middle" style="font-size:12px">CLAIMED</text>
        <text class="rm-t" x="120" y="236" text-anchor="middle" style="font-size:12px">MEASURED, same scale</text></svg></div></div>
      <div class="chips" aria-label="Two runs, equal weight">
        <div class="chip"><span class="cap">G7 &middot; preregistered</span><p>Preregistered bar <b>FAILED</b>: direction ${num(D, "g7.direction", "kn")}, clean false alarms ${num(D, "g7.false_alarms", "kn")}.</p>${V.vd("NOTMET", "bar failed")}</div>
        <div class="chip"><span class="cap">G8 &middot; new labelled run</span><p>Clauses (a) to (c) met: direction ${num(D, "g8.direction", "kn")}, clean false alarms ${num(D, "g8.false_alarms", "kn")}. Harness target missed: ${num(D, "g8.inconclusive", "kn")} INCONCLUSIVE.</p>${V.vd("SURVIVED", "clauses met")}</div></div>
      <div class="scrub"><button class="pillbtn solid" id="btnReplay" type="button">Replay</button>
        <button class="pillbtn" id="btnPlay" type="button" aria-pressed="false">Pause</button>
        <label class="sr" for="scrub">Replay timeline</label><input id="scrub" type="range" min="0" max="${T.END}" step="10" value="0">
        <span class="mk"><button type="button" data-t="${T.CX}">Connectors</button><button type="button" data-t="${T.N0}">Nodes</button><button type="button" data-t="${T.CNT}">Count</button><button type="button" data-t="${T.VERD}">Verdict</button></span></div>
      <p class="legendline"><span class="badge">REAL-PINNED</span> real public data, checksum-pinned, source disguised <span class="badge">TEXTBOOK</span> textbook setting <span class="badge">SYNTHETIC</span> built by us <span>Counts with n, not a population estimate.</span></p>`;
    H = { big: $("#big"), ring: $("#ringOuter"), verdict: $("#verdict"), scrub: $("#scrub"), cx: $$(".flow-h .cx[data-i]"), nodes: $$(".flow-h .fn"), claimed, measured,
      sentence: `FALSIFIED. Claimed ${fmt(G.claimed, "v3")}, measured ${fmt(G.controlled, "v3")}. G7: preregistered bar failed, direction ${fmt(g7.direction, "kn")}. G8: clauses a to c met, harness target missed.` };
    H.cx.forEach(c => { c.style.strokeDasharray = 1; c.style.strokeDashoffset = 1; });
    $("#btnReplay").addEventListener("click", replay);
    $("#btnPlay").addEventListener("click", () => {
      if (hero.playing) { hero.playing = false; $("#btnPlay").textContent = "Play"; }
      else { start(hero, hero.t >= hero.end ? 0 : hero.t); $("#btnPlay").textContent = hero.playing ? "Pause" : "Play"; }
    });
    H.scrub.addEventListener("input", () => { hero.playing = false; hero.t = +H.scrub.value; paintHero(hero.t); });
    $$(".scrub .mk button").forEach(b => b.addEventListener("click", () => { hero.playing = false; hero.t = +b.dataset.t + 1; paintHero(hero.t); }));
    wireFlow();
  }

  function wireFlow() {
    const go = el => { const t = $(el.dataset.to); if (t) { t.scrollIntoView({ behavior: RM ? "auto" : "smooth", block: "start" }); try { history.replaceState(null, "", el.dataset.to); } catch (e) { /* file:// */ } } };
    const ns = $$(".flow-h .fn");
    ns.forEach((g, i) => {
      g.addEventListener("click", () => go(g));
      g.addEventListener("keydown", e => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); e.stopPropagation(); go(g); }
        else if (e.key === "ArrowRight" || e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); const j = clamp(i + (e.key === "ArrowRight" ? 1 : -1), 0, ns.length - 1); ns.forEach((x, k) => x.tabIndex = k === j ? 0 : -1); ns[j].focus(); }
      });
    });
  }

  function renderReadout() {
    if (!D.readout || !D.readout.measured) { $("#readoutBody").innerHTML = `<p class="muted">No scored run files found.</p>`; return; }
    const R = V.readout(D), M = D.readout.measured;
    $("#readoutBody").innerHTML = `<div class="readgrid"><div class="gauge">${V.gauge(D)}
        <div class="glegend"><div class="n"><i></i><span>measured, mean of ${num(D, "readout.measured", "n")} repeats</span><b class="num" style="font-weight:400">${num(D, "readout.measured", "s3")}</b></div>
          <div class="h"><i></i><span>published (claim minus its own correction)</span><b class="num" style="font-weight:400">${num(D, "pub.inflation", "s2")}</b></div>
          <div class="d"><i></i><span>offline reference, Python port</span><b class="num" style="font-weight:400">${num(D, "pub.reference", "s3")}</b></div></div>
        <p class="xs muted" style="margin-top:12px">Gap tinted: measured against published. Dial runs 0 to 0.5 of inflation, no cropped axis. ${badge(M.badge)} <span class="faint">${esc(M.src)}</span></p></div>
      <div>${R.tiles}</div></div>${R.clauses}`;
  }

  function renderIntervals() { $("#intervalsBody").innerHTML = V.intervals(D); }
  function renderRings() { const R = V.rings(D); $("#layersBody").innerHTML = `<div class="layers">${R.svg}${R.list}</div>`; }

  /* ------------------------------------------------------------------ deliverable: reviewer note + recorded terminal */
  let REC = "rules";
  const recs = () => D.recorded || [];
  const recIdx = () => Math.max(0, recs().findIndex(r => r.tag === REC));
  function noteParts(r) {
    const claim = ((r.claim_md || "").split("\n").filter(l => l.startsWith(">")).map(l => l.replace(/^>\s?/, "")).join(" ") || "").trim();
    const step = (r.reviewer_note.match(/only ([\w, ]+?) changed/) || [])[1] || "";
    const cant = (r.could_not_test_md || "").split("\n").filter(l => l.startsWith("- ")).map(l => l.slice(2));
    return { claim, step, cant };
  }
  function renderDeliv() {
    const rs = recs();
    if (!rs.length) { $("#delivBody").innerHTML = `<p class="muted">No recorded run found in report/assets/recorded/.</p>`; return; }
    const i = recIdx(), r = rs[i], P = noteParts(r), b = `recorded.${i}.ba`;
    const diff = (r.diff || "").split("\n");
    const note = `<div class="note"><p class="xs muted" style="margin:0 0 12px">${badge("SYNTHETIC")} Example output on a case we built. <span class="faint">${esc(r.source_file)}</span></p>
      <div class="cap">What we could not test</div><ul style="margin:6px 0 20px;padding-left:18px;font-size:14px;line-height:22px">${P.cant.slice(0, 3).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
      <dl><dt>Claim</dt><dd>${esc(P.claim)}</dd>
        <dt>Flaw step</dt><dd>${esc(P.step || "see diff")}${r.rules_fired && r.rules_fired.length ? " (rule " + esc(r.rules_fired.join(", ")) + " fired)" : ""}</dd>
        <dt>Diff</dt><dd><pre tabindex="0">${esc(diff.slice(0, 14).join("\n"))}${diff.length > 14 ? "\n... " + (diff.length - 14) + " more lines in the .patch" : ""}</pre></dd>
        <dt>Before / after</dt><dd>claimed ${num(D, b + ".claimed", "pct1")} &rarr; controlled ${num(D, b + ".controlled", "pct1")} (${esc(r.summary.metric)}), drop ${num(D, b + ".inflation", "pp")} pp; n = ${num(D, b + ".n", "k")} rows scored per seed. Seed signs ${esc((r.summary.per_seed_sign || []).join(" "))}.</dd>
        <dt>Rerun</dt><dd><code class="mono xs">${esc(r.rerun_command)}</code></dd></dl>
      <div class="actions"><button class="pillbtn solid" id="btnCopyNote" type="button">Copy as reviewer note</button><button class="pillbtn" id="btnPatch" type="button">.patch</button><button class="pillbtn" id="btnBundle" type="button">Download bundle</button></div></div>`;
    $("#delivBody").innerHTML = `<div class="deliv">${note}${termHtml(r)}</div>`;
    $("#btnCopyNote").addEventListener("click", () => copy(r.reviewer_note, "Reviewer note copied"));
    $("#btnPatch").addEventListener("click", () => save(r.diff, "nulllab-" + r.case + ".patch", "text/x-diff"));
    $("#btnBundle").addEventListener("click", () => save(JSON.stringify({ record: r, note: r.reviewer_note, diff: r.diff }, null, 1), "nulllab-bundle-" + r.case + ".json", "application/json"));
    $$("#termSeg button").forEach(x => x.addEventListener("click", () => { REC = x.dataset.tag; renderDeliv(); startTerm(); }));
    $("#termCopy").addEventListener("click", () => copy(r.command, "Command copied"));
    $("#termSkip").addEventListener("click", () => { termP.playing = false; termP.t = termP.end; paintTerm(termP.end); });
  }
  function termHtml(r) {
    const lines = [{ c: "pr", t: "$ " + r.command }].concat(r.stdout.map(t => ({ c: "hl", t })), [{ c: "", t: "" }],
      r.report_head.map(t => ({ c: "", t: t.replace(/\*\*/g, "").replace(/`/g, "") })), [{ c: "", t: "" }],
      r.cost_lines.map(t => ({ c: "", t: t.replace(/\*\*/g, "") })), [{ c: "ok", t: "exit " + r.exit_code }]);
    TERM = { lines };
    const lab = { rules: "Rules only, $0.00", spark: "Spark case, recorded" };
    return `<div class="term"><div class="tb"><span class="badge">REPLAY</span><span class="seg" id="termSeg" role="group" aria-label="Recorded run">${recs().map(x => `<button type="button" data-tag="${esc(x.tag)}" aria-pressed="${x.tag === r.tag}">${esc(lab[x.tag] || x.tag)}</button>`).join("")}</span><span class="grow"></span>
        <button class="pillbtn" id="termCopy" type="button">Copy command</button><button class="pillbtn" id="termSkip" type="button">Skip</button></div>
      <div class="body" id="termBody" tabindex="0" role="log" aria-label="Recorded terminal output">${lines.map(l => `<span class="ln ${l.c}">${esc(l.t) || "&nbsp;"}</span>`).join("")}</div>
      <div class="ft">REPLAY of a real run recorded ${esc(r.recorded_utc.replace("T", " ").replace("Z", " UTC"))} (${esc(r.recorded_slt)} / ${esc(r.recorded_et)}). Source: <code>${esc(r.source_file)}</code>. ${esc(r.stdout_note)}. Model calls in this run: 0. Estimates are not billing.</div></div>`;
  }
  function copy(text, msg) {
    const done = () => toast(msg);
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
    else fallbackCopy(text, done);
  }
  function fallbackCopy(text, done) { const t = document.createElement("textarea"); t.value = text; t.style.position = "fixed"; t.style.opacity = "0"; document.body.appendChild(t); t.select(); try { document.execCommand("copy"); done(); } catch (e) { toast("Copy blocked by the browser"); } t.remove(); }
  function save(text, name, type) {
    try { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([text], { type })); a.download = name; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 400); toast("Saved " + name); } catch (e) { toast("Save failed: " + e.message); }
  }
  function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("on"); clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove("on"), 2200); }
  function startTerm() { paintTerm(0); start(termP, 0); }

  /* ------------------------------------------------------------------ footer + G9 slot */
  function renderFooter() {
    const L = D.ledger, G9 = D.g9;
    $("#footBody").innerHTML = `<div class="fgrid"><div><h3>Limits and provenance</h3>
        <p><button class="pillbtn" data-open="limits" type="button">Read the limits</button></p>
        <p><span class="badge">REAL-PINNED</span> real public data, checksum-pinned. <span class="badge">TEXTBOOK</span> a textbook-documented setting. <span class="badge">SYNTHETIC</span> a case we built.</p>
        <p>Every headline number shows its n and its file. Counts on cases we built or picked, not rates for the wild.</p></div>
      <div><h3>Estimated spend</h3><p>About <b class="num" data-p="ledger.total_usd" data-f="usd">$${L.total_usd.toFixed(2)}</b> in estimated Meta credits over <b class="num">${L.total_calls}</b> live calls, G4 to G8. Estimate at per-call figures, not billing. This page makes no model call.</p>
        <p class="xs">${L.phases.map(p => `${esc(p.name)} $${p.usd.toFixed(2)}`).join(" &middot; ")}</p></div>
      <div>${G9 ? `<div class="g9"><h3>G9 &middot; ${G9.complete ? "complete, 16 of 16 units (G9 + G9b)" : G9.status ? "incomplete run, recorded units only" : "scored, as the file states"}</h3>${G9.read_first ? `<p class="xs"><b>${esc(G9.read_first)}</b></p>` : ""}${G9.status ? `<p class="xs">${esc(G9.status)}</p>` : ""}<dl>${G9.rows.map(r => `<dt>${esc(r.key)}</dt><dd class="num">${esc(r.val)}</dd>`).join("")}</dl>${G9.guard_note ? `<p class="xs" style="margin-top:8px">${esc(G9.guard_note)} ${esc(G9.spend_note || "")}</p>` : ""}${G9.units && G9.units.length ? `<details><summary class="xs">Per unit, with guard version (${G9.units.length})</summary><dl>${G9.units.map(r => `<dt>${esc(r.unit)} &middot; ${esc(r.guard)}</dt><dd class="num">${esc(r.outcome)}</dd>`).join("")}</dl></details>` : ""}<p class="xs" style="margin-top:8px">${badge(G9.badge)} ${esc(G9.src)}. ${G9.complete ? "Clause results are the preregistered ones from the file." : "No pass or fail is added by this page."}</p></div>`
        : `<h3>Build</h3><p>NullLab, Meta Global AI Developer Hackathon. Recorded runs on muse-spark-1.3 and muse-spark-1.3-contributor.</p>`}
        <p class="xs">Test suite: ${esc(D.tests_doc.value)} (${esc(D.tests_doc.src)}). Data generated ${esc(D.generated_utc)}.</p></div></div>`;
    $$("[data-open]", $("#footBody")).forEach(b => b.addEventListener("click", () => openDrawer(b.dataset.open)));
  }

  /* ------------------------------------------------------------------ drawers */
  const sg = (x, d) => (x == null ? "n/a" : (x >= 0 ? "+" : "-") + Math.abs(Number(x)).toFixed(d));
  const DR = {
    steps: ["Step log and diff", () => {
      const t = D.trace; if (!t) return `<p class="muted">No trace found.</p>`;
      const edits = (t.act.edits || []).map(e => `<h4>${esc(e.label)}</h4><pre tabindex="0">${esc(e.code)}</pre>`).join("");
      return `<p class="xs muted">${badge("REAL-PINNED")} one executed G8 repeat. <span class="faint">${esc(t.source)}</span></p><h4>Log</h4><ol style="padding-left:20px">${t.lines.map(l => `<li><b>${esc(l.phase)}</b> ${esc(l.text)}${l.detail ? `<br><span class="xs muted">${esc(l.detail)}</span>` : ""}</li>`).join("")}</ol>${edits}`;
    }],
    factorial: ["2x2 factorial", () => {
      const f = D.factorial; if (!f) return `<p class="muted">No factorial run found.</p>`;
      const names = { orig: "original", fix_A: "fix A only", fix_B: "fix B only", fix_both: "fix both" };
      return `<p>${badge("SYNTHETIC")} A synthetic case with two planted flaws that interact. Fixing either alone barely helps; only fixing both removes the inflation. <span class="faint xs">${esc(f.src)}</span></p>
        <table><thead><tr><th>config</th><th>accuracy (mean of 3 seeds)</th></tr></thead><tbody>${Object.keys(f.acc).map(k => `<tr><td>${esc(names[k] || k)}</td><td>${num(D, "factorial.acc." + k, "pct1")} <span class="faint">n = ${num(D, "factorial.acc." + k, "n")}</span></td></tr>`).join("")}</tbody></table>
        <h4>Drop in points</h4><table><tbody>${Object.keys(f.components).map(k => `<tr><td>${esc(k)}</td><td>${num(D, "factorial.components." + k, "pp")} pp</td></tr>`).join("")}</tbody></table>`;
    }],
    score: ["Scoreboard", () => {
      const sb = D.scoreboard;
      return `<div class="tw"><table><thead><tr><th>evaluation</th><th>loop</th><th>reading only</th></tr></thead><tbody>${sb.rows.map(r => `<tr><td>${esc(r.eval)}<br><span class="faint">${r.badges.map(esc).join(", ")} &middot; ${esc(r.metric)}</span><br><span class="faint">${esc(r.note)}</span></td><td>${esc(r.loop)}</td><td>${esc(r.b3)}</td></tr>`).join("")}</tbody></table></div>
        <h4>Off-the-shelf checkers, 9 blind inputs</h4><table><thead><tr><th>tool</th><th>recall</th><th>false alarms</th></tr></thead><tbody>${sb.tools.map(t => `<tr><td>${esc(t.tool)}<br><span class="faint">${esc(t.rule)}</span></td><td>${esc(t.recall)}</td><td>${esc(t.fa)}</td></tr>`).join("")}</tbody></table>
        <p class="xs muted">${esc(sb.tools_src)}. Counts, not a population estimate.</p>`;
    }],
    wonder: ["Wonder swap", () => { const w = D.wonder; return `<p>${badge("SYNTHETIC")} Swapping the planner to muse-wonder-1.0: schema-valid plans <b>${num(D, "wonder.plans", "kn")}</b>, hard-case sign <b>${num(D, "wonder.hard_sign", "kn")}</b>, clean false alarms <b>${num(D, "wonder.clean_fa", "kn")}</b>.</p><p class="xs muted">${esc(w.note)} <span class="faint">${esc(w.plans.src)}</span></p>`; }],
    ci: ["CI and bundle commands", () => `<h4>CI check (rules only, $0, no key)</h4><pre tabindex="0">python -m agent.ci_check . --threshold 0.05 --summary $GITHUB_STEP_SUMMARY</pre><p class="xs muted">Exit 0: no case above the threshold. 1: at least one case INFLATED. 2: nothing audited or a measurement failed. A case where no rule fired is reported as NO_RULE_FIRED, not as a pass.</p>
      <h4>Reviewer bundle</h4><pre tabindex="0">python -m agent.bundle --help</pre><p class="xs muted">Run it for the options. The page's own bundle button saves the recorded record, diff and note as one JSON file.</p>`],
    sandbox: ["Sandbox limits", () => `<ul><li>A restricted subprocess: network cut, timeout, evaluator paths blocked. Not a locked container.</li><li>The guard checks that an edit stays inside its declared step and that a forecast gets a time split. It cannot check direction, or whether a fix is the right one.</li><li>Repeats at temperature 0.7 are weakly independent.</li></ul>`],
    flaw: ["The untouched second flaw", () => `<p>The real data file carries a second documented flaw: imputation that used the outcome. It is baked into the file and no method on this page corrects it. Measured numbers are for the flaw named in the claim only.</p>`],
    limits: ["Limits", () => {
      const g7 = D.g7, g8 = D.g8;
      return `<h4>${badge("SYNTHETIC")} Synthetic</h4><ul><li>The hard cases, the 2x2 factorial and the rules comparison are cases we generated with planted flaws. Counts, not rates. Repeats are weakly independent.</li></ul>
      <h4>${badge("REAL-PINNED")} Real, and its limits</h4><ul>
        <li>The headline case is real public data from a published 2016 ML study, with columns renamed, the domain reworded and features rescaled. Same rows, same numbers. The study's topic is not shown on this page.</li>
        <li>G7 (preregistered): bar FAILED, direction ${num(D, "g7.direction", "kn")}, ${num(D, "g7.inconclusive", "kn")} INCONCLUSIVE overall. G8 (a new labelled run, scored exactly as frozen): clauses (a) to (c) met, harness target not met (${num(D, "g8.inconclusive", "kn")}). Both stand. Neither is merged with or re-scored by the other.</li>
        <li>Measured ${num(D, "readout.measured", "s3")} against the published ${num(D, "pub.inflation", "s2")}; a Python port of the original pipeline measures ${num(D, "pub.reference", "s3")} on the same rows.</li>
        <li>The guard rejected a random-split plan in ${num(D, "guard", "k")} of ${num(D, "guard", "n")} executed repeats; the time split comes from the guard plus the model, not from the model alone.</li>
        <li>The fixed-rules baseline was never run on the disguised case. Rules matched or beat the loop on the undisguised case.</li>
        <li>The model's refusal to name the source in two probe calls shows it did not name it, not that it has no memory of it. The undisguised and textbook sources are recognised.</li>
        <li>One harness failure (read timeout) is in the denominator and listed; it was not re-rolled. n = 5 per arm, unpaired bootstrap intervals.</li></ul>
      <h4>UNVERIFIED</h4><ul><li>Whether the variables the planner wanted to drop really leak: the guard blocked that experiment.</li><li>Real per-token pricing: spend figures are per-call estimates.</li><li>A rerun of the whole loop from recorded replies was not repeated for this page.</li></ul>
      <h4>${badge("MOCK").replace('class="badge"', 'class="badge mock"')} Mock runs</h4><p class="xs muted">runs/*.json come from a scripted stand-in that exercises the plumbing. They are never model results and never in a headline.</p>`;
    }]
  };
  let lastFocus = null;
  function openDrawer(id) {
    const d = DR[id]; if (!d) return;
    lastFocus = document.activeElement;
    $("#drawerTitle").textContent = d[0]; $("#drawerBody").innerHTML = d[1]();
    $("#scrim").classList.add("on"); const el = $("#drawer"); el.removeAttribute("inert"); el.setAttribute("aria-hidden", "false"); el.classList.add("on"); $("#closeDrawer").focus();
  }
  function closeDrawer() {
    $("#scrim").classList.remove("on"); const el = $("#drawer"); el.classList.remove("on"); el.setAttribute("inert", ""); el.setAttribute("aria-hidden", "true");
    if (lastFocus && lastFocus.focus) lastFocus.focus();
  }

  /* ------------------------------------------------------------------ theme, keyboard, nav, data */
  function curTheme() { const t = document.documentElement.dataset.theme; if (t) return t; return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"; }
  function syncTheme() { const t = curTheme(), b = $("#btnTheme"); b.setAttribute("aria-label", t === "dark" ? "Switch to light theme" : "Switch to dark theme"); b.textContent = t === "dark" ? "Light" : "Dark"; }
  function toggleTheme() { const n = curTheme() === "dark" ? "light" : "dark"; document.documentElement.dataset.theme = n; store.set("nl-theme", n); syncTheme(); }
  function keys(e) {
    if (e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const tag = (e.target.tagName || "").toLowerCase();
    if (["input", "select", "textarea"].includes(tag)) return;
    if (e.key === "Escape") { if ($("#drawer").classList.contains("on")) closeDrawer(); return; }
    if ($("#help").open) return;
    if (e.key === " " && !["button", "summary", "a"].includes(tag) && !e.target.closest(".fn")) { e.preventDefault(); $("#btnPlay") && $("#btnPlay").click(); }
    else if (e.key === "?") { e.preventDefault(); $("#help").showModal ? $("#help").showModal() : $("#help").setAttribute("open", ""); }
    else if (e.key === "r" || e.key === "R") replay();
    else if (e.key === "s" || e.key === "S") skip();
    else if (e.key === "t" || e.key === "T") toggleTheme();
    else if (e.key === "l" || e.key === "L") openDrawer("limits");
  }
  function trap(e) {
    if (e.key !== "Tab" || !$("#drawer").classList.contains("on")) return;
    const f = $$("#drawer a, #drawer button, #drawer pre").filter(x => x.offsetParent !== null);
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
  function setStatus(html) { const s = $("#dataStatus"); if (s) s.textContent = html; }
  async function load() {
    const EMB = window.__NL_DATA || null;
    if (/^https?:$/.test(location.protocol)) {
      try {
        const ctl = "AbortController" in window ? new AbortController() : null, to = setTimeout(() => ctl && ctl.abort(), 2500);
        const r = await fetch("/api/demo", { cache: "no-store", signal: ctl ? ctl.signal : undefined }); clearTimeout(to);
        if (!r.ok) throw new Error("HTTP " + r.status);
        const d = await r.json(); setStatus("Read from the run files just now, " + d.generated_utc); return d;
      } catch (e) { if (EMB) { setStatus("API offline: run data embedded at build time, " + EMB.generated_utc); return EMB; } throw e; }
    }
    if (EMB) { setStatus("Opened as a file: run data embedded at build time, " + EMB.generated_utc); return EMB; }
    throw new Error("no embedded data");
  }
  /* number-vs-data check: every [data-p] equals the same path of a freshly built payload (needs the API) */
  window.NLcheck = async function () {
    const fresh = await (await fetch("/api/demo", { cache: "no-store" })).json(), bad = [];
    const els = $$("[data-p]");
    els.forEach(el => { if (el.dataset.f === "usd") return; const want = V.fmt(V.get(fresh, el.dataset.p), el.dataset.f); if (want !== el.textContent.trim()) bad.push({ p: el.dataset.p, shown: el.textContent, want }); });
    return { checked: els.length, mismatches: bad };
  };

  function once(el, fn) {
    if (!el) return;
    if (!("IntersectionObserver" in window)) { fn(); return; }
    const io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) { fn(); io.unobserve(e.target); } }), { threshold: .35 });
    io.observe(el);
  }

  function wire() {
    $("#btnTheme").addEventListener("click", toggleTheme);
    $$("[data-open]").forEach(b => b.addEventListener("click", () => openDrawer(b.dataset.open)));
    $("#closeDrawer").addEventListener("click", closeDrawer); $("#scrim").addEventListener("click", closeDrawer);
    $("#btnHelp").addEventListener("click", () => { const d = $("#help"); d.showModal ? d.showModal() : d.setAttribute("open", ""); });
    $("#closeHelp").addEventListener("click", () => { const d = $("#help"); d.close ? d.close() : d.removeAttribute("open"); });
    document.addEventListener("keydown", keys); document.addEventListener("keydown", trap);
  }

  async function init() {
    syncTheme(); wire();
    try { D = await load(); } catch (e) { setStatus("Could not load run data: " + e.message); $("#heroBody").innerHTML = `<p class="muted">No run data available. Run <code>python -m report.render</code> to embed it, or start the API with <code>uvicorn app.server:app</code>.</p>`; return; }
    renderHero(); renderReadout(); renderIntervals(); renderRings(); renderDeliv(); renderFooter(); navSpy();
    $("#delivIntro") && ($("#delivIntro").hidden = false);
    // initial states, then the page-load run: hero sequence now; needle and terminal when they scroll into view (once each)
    paintNeedle(RM ? needle.end : 0);
    if (RM) { paintHero(T.END); hero.t = T.END; H.verdict && H.verdict.classList.add("settled"); } else { paintHero(0); setTimeout(() => start(hero, 0), 250); }
    once($(".gauge"), () => start(needle, 0));
    if (RM) start(termP); else { paintTerm(0); once($("#termBody"), () => start(termP, 0)); }
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
