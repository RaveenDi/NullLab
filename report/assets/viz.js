/* NullLab viz: pure functions (data in, markup out). No DOM access, no globals except NLV. Every number is rendered through
   num(D, path, fmt), which tags the element with data-p / data-f so a script can re-check it against spa_data.build(). */
(function (root) {
  "use strict";
  const esc = s => String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const get = (o, p) => String(p).split(".").reduce((a, k) => (a == null ? a : a[k]), o);
  const sgn = (x, d) => (x >= 0 ? "+" : "-") + Math.abs(x).toFixed(d);
  /* formats: kn = k/n, k = count or value as is, v3 / v2 = value with 3 / 2 decimals, s3 / s2 = signed value, n = n alone */
  function fmt(item, f) {
    if (item == null || item.k == null) return "n/a";
    switch (f) {
      case "kn": return item.k + "/" + item.n;
      case "n": return String(item.n);
      case "v3": return Number(item.k).toFixed(3);
      case "v2": return Number(item.k).toFixed(2);
      case "s3": return sgn(item.k, 3);
      case "s2": return sgn(item.k, 2);
      case "pp": return sgn(item.k, 1);
      case "pct1": return (item.k * 100).toFixed(1) + "%";
      default: return String(item.k);
    }
  }
  const num = (D, path, f, cls) => `<span class="num ${cls || ""}" data-p="${esc(path)}" data-f="${esc(f)}">${esc(fmt(get(D, path), f))}</span>`;
  const badge = b => `<span class="badge">${esc(b)}</span>`;
  const IC = {
    x: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/></svg>',
    check: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3.2L13 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" fill="none"/></svg>',
    q: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5.6 5.8a2.5 2.5 0 1 1 3.6 2.2c-.8.4-1.2.9-1.2 1.8" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" fill="none"/><circle cx="8" cy="13" r="1.1" fill="currentColor"/></svg>',
    broken: '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2.2a5.8 5.8 0 1 0 5.8 5.8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" fill="none"/><path d="M11 2.6l1.2 1.2M13.2 5l-1.2-1.2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>',
    square: '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="2.5" y="2.5" width="11" height="11" rx="1.5" stroke="currentColor" stroke-width="1.6" fill="none"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>'
  };
  const vd = (v, label) => `<span class="vd ${v}">${v === "FALSIFIED" ? IC.x : v === "SURVIVED" ? IC.check : v === "INCONCLUSIVE" ? IC.q : IC.square}${esc(label || v)}</span>`;

  const rad = d => d * Math.PI / 180;
  const pol = (cx, cy, r, deg) => [cx + r * Math.sin(rad(deg)), cy - r * Math.cos(rad(deg))];
  const f1 = x => (Math.round(x * 100) / 100);

  /* ---------------------------------------------------------------- flow (hero) */
  const NODES = [
    { id: "claim", label: "Claim", note: "a published score", x: 80, y: 238, to: "#top" },
    { id: "guard", label: "Guard", note: "plain code, not the model", x: 290, y: 176, to: "#deliverable" },
    { id: "rerun", label: "Re-run", note: "4 configs x 3 seeds, no network", x: 500, y: 250, to: "#intervals" },
    { id: "measure", label: "Measure", note: "bootstrap interval per seed", x: 700, y: 176, to: "#readout" },
    { id: "verdict", label: "Verdict", note: "a word and an icon", x: 870, y: 250, to: "#layers" }
  ];
  const nodeW = n => n.label.length * 9.4 + 44;
  function flow(D) {
    const g = D.guard;
    const paths = NODES.slice(0, -1).map((a, i) => {
      const b = NODES[i + 1], x1 = a.x + nodeW(a) / 2, x2 = b.x - nodeW(b) / 2, dx = (x2 - x1) / 2;
      return `<path class="cx" data-i="${i}" pathLength="1" d="M${f1(x1)} ${a.y}C${f1(x1 + dx)} ${a.y} ${f1(x2 - dx)} ${b.y} ${f1(x2)} ${b.y}"/>`;
    }).join("");
    const nodes = NODES.map((n, i) => {
      const w = nodeW(n);
      return `<g class="fn" data-i="${i}" data-to="${n.to}" role="link" tabindex="${i ? -1 : 0}" aria-label="${esc(n.label)}: ${esc(n.note)}. Jump to its section.">
        <rect class="pill" x="${f1(n.x - w / 2)}" y="${n.y - 15}" width="${f1(w)}" height="30" rx="15"/>
        <circle class="dot" cx="${f1(n.x - w / 2)}" cy="${n.y}" r="3"/><circle class="dot" cx="${f1(n.x + w / 2)}" cy="${n.y}" r="3"/>
        <text class="lab" x="${n.x}" y="${n.y + 5}" text-anchor="middle" style="font-size:15px">${esc(n.label)}</text>
        <text class="note" x="${n.x}" y="${n.y + 36}" text-anchor="middle" style="font-size:14px">${esc(n.note)}</text></g>`;
    }).join("");
    const gx = NODES[1].x, gy = NODES[1].y;
    const branch = g ? `<g class="branchbox"><path class="cx branch" d="M${gx} ${gy - 15}V${gy - 58}"/>
      <rect class="pill" x="${gx - 168}" y="${gy - 104}" width="336" height="46" rx="23"/>
      <text x="${gx}" y="${gy - 84}" text-anchor="middle" style="font-size:14px">random split rejected &#8594; time split</text>
      <text x="${gx}" y="${gy - 67}" text-anchor="middle" style="font-size:13px"><tspan class="k num" data-p="guard" data-f="k">${esc(fmt(g, "k"))}</tspan> of <tspan class="k num" data-p="guard" data-f="n">${esc(fmt(g, "n"))}</tspan> initial plans, runs_g8</text></g>` : "";
    const horiz = `<svg class="flow-h" viewBox="0 0 960 330" role="group" aria-label="Pipeline: Claim, Guard, Re-run, Measure, Verdict">${paths}${branch}${nodes}</svg>`;
    const vert = `<ol class="flow-v" aria-label="Pipeline, vertical">${NODES.map((n, i) => `<li><a href="${n.to}" data-to="${n.to}">${esc(n.label)}</a><p>${esc(n.note)}</p>${i === 1 && g ? `<span class="br">random split rejected &#8594; time split, <b class="num" data-p="guard" data-f="k">${esc(fmt(g, "k"))}</b> of <b class="num" data-p="guard" data-f="n">${esc(fmt(g, "n"))}</b> initial plans</span>` : ""}</li>`).join("")}</ol>`;
    return horiz + vert;
  }

  /* ---------------------------------------------------------------- gauge (readout) */
  const GMAX = 0.5, A0 = -120, A1 = 120;
  const ang = v => A0 + (A1 - A0) * Math.max(0, Math.min(GMAX, v)) / GMAX;
  function arc(cx, cy, r, a0, a1) {
    const [x0, y0] = pol(cx, cy, r, a0), [x1, y1] = pol(cx, cy, r, a1);
    return `M${f1(x0)} ${f1(y0)}A${r} ${r} 0 ${a1 - a0 > 180 ? 1 : 0} 1 ${f1(x1)} ${f1(y1)}`;
  }
  function gauge(D) {
    const cx = 200, cy = 190, r = 140;
    const meas = D.readout.measured.k, pub = D.pub.inflation.k, ref = D.pub.reference.k;
    let labs = "";
    for (let i = 0; i <= 5; i++) { const v = i / 10, [x, y] = pol(cx, cy, r + 26, ang(v)); labs += `<text class="g-lab" x="${f1(x)}" y="${f1(y + 4)}" text-anchor="middle">${v.toFixed(1)}</text>`; }
    const [px, py] = pol(cx, cy, r + 10, ang(pub));
    const [r0x, r0y] = pol(cx, cy, r - 24, ang(ref)), [r1x, r1y] = pol(cx, cy, r + 14, ang(ref));
    const lo = Math.min(meas, pub), hi = Math.max(meas, pub);
    const [a1x, a1y] = pol(cx, cy, r - 30, ang(lo)), [a2x, a2y] = pol(cx, cy, r - 30, ang(hi)), [b1x, b1y] = pol(cx, cy, r - 14, ang(hi)), [b2x, b2y] = pol(cx, cy, r - 14, ang(lo));
    const gap = `M${f1(a1x)} ${f1(a1y)}A${r - 30} ${r - 30} 0 0 1 ${f1(a2x)} ${f1(a2y)}L${f1(b1x)} ${f1(b1y)}A${r - 14} ${r - 14} 0 0 0 ${f1(b2x)} ${f1(b2y)}Z`;
    const start = ang(pub);
    return `<svg viewBox="0 0 400 300" role="img" aria-label="Dial from 0 to 0.5 of inflation. Measured needle ${fmt(D.readout.measured, "s3")}, published ${fmt(D.pub.inflation, "s2")}, offline reference ${fmt(D.pub.reference, "s3")}.">
      <path class="g-arc" d="${arc(cx, cy, r, A0, A1)}"/>
      <path class="g-min" pathLength="250" stroke-dasharray="1 9" d="${arc(cx, cy, r, A0, A1)}"/>
      <path class="g-maj" pathLength="250" stroke-dasharray="1.4 48.6" d="${arc(cx, cy, r, A0, A1)}"/>
      <path class="g-maj" d="M${f1(pol(cx, cy, r - 6, A1)[0])} ${f1(pol(cx, cy, r - 6, A1)[1])}L${f1(pol(cx, cy, r + 6, A1)[0])} ${f1(pol(cx, cy, r + 6, A1)[1])}" style="stroke-width:1.4"/>
      ${labs}<path class="g-gap" d="${gap}"/>
      <line class="g-ref" x1="${f1(r0x)}" y1="${f1(r0y)}" x2="${f1(r1x)}" y2="${f1(r1y)}"/>
      <circle class="g-pub" cx="${f1(px)}" cy="${f1(py)}" r="5"/>
      <g transform="translate(${cx} ${cy})"><g id="needle" data-a="${ang(meas).toFixed(2)}" data-s="${start.toFixed(2)}" transform="rotate(${ang(meas).toFixed(2)})"><line class="g-needle" x1="0" y1="0" x2="0" y2="${-(r - 18)}"/></g><circle class="g-hub" r="6"/></g>
      <g class="g-seed" id="seeds">${[42, 43, 44].map((s, i) => `<circle cx="${170 + i * 30}" cy="252" r="4.5"/><text x="${170 + i * 30}" y="276" text-anchor="middle">${s}</text>`).join("")}</g></svg>`;
  }

  /* ---------------------------------------------------------------- readout tiles + clauses */
  function readout(D) {
    const R = D.readout;
    if (!R || !R.measured) return `<p class="muted">No scored run files found.</p>`;
    const rep = R.repeats.map((_, i) => num(D, `readout.repeats.${i}`, "s3")).join("");
    const tile = (cap, body, meta) => `<div class="tile"><div class="cap">${cap}</div>${body}<div class="meta">${meta}</div></div>`;
    const t1 = tile("Leaky repeats, measured inflation", `<div class="tn small">${rep}</div>`,
      `<span>n = ${num(D, "readout.measured", "n")} executed of ${num(D, "g8.direction", "n")} repeats</span>${badge(R.measured.badge)}<span class="faint">${esc(R.measured.src)}</span>`);
    const t2 = tile("Clean twin, false alarms", `<div class="tn">${num(D, "readout.clean_fa", "kn")}</div>`,
      `<span>n = ${num(D, "readout.clean_fa", "n")} repeats</span>${badge(R.clean_fa.badge)}<span class="faint">${esc(R.clean_fa.src)}</span>`);
    const t3 = tile("Harness INCONCLUSIVE", `<div class="tn">${num(D, "readout.harness.got", "kn")}</div>`,
      `<span>target ${num(D, "readout.harness.target", "k")}, not met</span>${badge(R.harness.got.badge)}<span class="faint">${esc(R.harness.got.src)}</span>`);
    const rows = R.clauses.map((c, i) => `<div class="cl"><span class="faint">(${c.id})</span><span class="nm">${esc(c.label)}</span>
      <span>${c.rule === "ge" ? "at least " : "at most "}${num(D, `readout.clauses.${i}.needed`, "kn")}</span><span>${num(D, `readout.clauses.${i}.got`, "kn")}</span>
      <span class="st ${c.met ? "" : "no"}">${c.met ? IC.check + "<span>MET</span>" : IC.x + "<span>NOT MET</span>"}</span></div>`).join("");
    const hm = `<div class="cl"><span class="faint">(t)</span><span class="nm">harness target (not a pass clause)</span><span>at most ${num(D, "readout.harness.target", "k")}</span><span>${num(D, "readout.harness.got", "kn")}</span><span class="st no">${IC.broken}<span>NOT MET</span></span></div>`;
    return { tiles: `<div class="tiles">${t1}${t2}${t3}</div>`, clauses: `<div class="clauses" role="table" aria-label="Preregistered clauses, needed versus got"><div class="cl head" role="row"><span></span><span>Preregistered clause</span><span>Needed</span><span>Got</span><span class="st">Status</span></div>${rows}${hm}</div>` };
  }

  /* ---------------------------------------------------------------- intervals (tick scale rows, HTML so labels stay legible at 390 px) */
  function intervals(D) {
    const G = D.g8; if (!G) return "";
    const all = [].concat(G.leaky, G.clean).flatMap(r => (r.seeds || []).flatMap(s => [s.lo, s.hi]));
    const lo = Math.floor(Math.min(-0.1, ...all) * 10) / 10, hi = Math.ceil(Math.max(0.5, ...all, D.pub.inflation.k) * 10) / 10;
    const p = v => ((v - lo) / (hi - lo) * 100).toFixed(2);
    let ticks = "";
    for (let v = Math.round(lo * 20) / 20; v <= hi + 1e-9; v = Math.round((v + 0.05) * 100) / 100) {
      const major = Math.abs(Math.round(v * 10) - v * 10) < 1e-6;
      ticks += `<i class="${major ? "m" : ""}" style="left:${p(v)}%"></i>${major ? `<b style="left:${p(v)}%">${v === 0 ? "0" : sgn(v, 1)}</b>` : ""}`;
    }
    const group = (title, rowsKey, spanNote) => {
      const rows = G[rowsKey].map((r, i) => {
        const lb = `<div class="lb"><span>R${r.r.slice(1)}</span>${r.failed ? "" : num(D, `g8.${rowsKey}.${i}.m`, "s3")}</div>`;
        if (r.failed) return `<div class="ivrow fail">${lb}<div class="ivtrack">${IC.broken}<span>empty slot: read timeout ~500 s, counted as not met, not re-rolled</span></div></div>`;
        const br = r.seeds.map((s, j) => `<div class="bk" style="left:${p(s.lo)}%;width:${(p(s.hi) - p(s.lo)).toFixed(2)}%;top:${4 + j * 10}px" title="seed ${esc(s.seed)}"></div>`).join("");
        return `<div class="ivrow">${lb}<div class="ivtrack">${br}<div class="dotm" style="left:${p(r.mean)}%;top:14px"></div></div></div>`;
      }).join("");
      return `<div class="ivgroup"><h3>${title}</h3><div class="ivscale" aria-hidden="true">${ticks}</div>
        <div class="ivrows"><div class="zero" style="left:calc(var(--lw,128px) + (100% - var(--lw,128px)) * ${p(0) / 100})"></div><div class="pubm" style="left:calc(var(--lw,128px) + (100% - var(--lw,128px)) * ${p(D.pub.inflation.k) / 100})"></div>${rows}</div>
        <p class="ivnote">${spanNote}</p></div>`;
    };
    return `<div class="ivwrap">
      ${group(`Leaky pipeline, ${num(D, "g8.direction", "n")} repeats ${badge("REAL-PINNED")}`, "leaky", `Three thin brackets per repeat: 95% intervals of the drop for seeds 42, 43, 44; dot = repeat mean. Solid rule = 0. Dashed rule = published ${fmt(D.pub.inflation, "s2")}. n = ${esc((G.n_scored || []).map(n => n.toLocaleString("en-US")).join(" to "))} held-out rows per seed.`)}
      ${group(`Clean twin, ${num(D, "g8.false_alarms", "n")} repeats ${badge("REAL-PINNED")}`, "clean", `Same scale as above. Every interval spans 0: no evidence of inflation, not proof of absence.`)}</div>`;
  }

  /* ---------------------------------------------------------------- rings: layers of evidence */
  function rings(D) {
    const Rg = D.rings; if (!Rg) return { svg: "", list: "" };
    const c = Rg.core, m = Rg.mid, o = Rg.outer, gh = Rg.ghost;
    const at = (r, deg) => { const [x, y] = pol(50, 50, r, deg); return `left:${x.toFixed(1)}%;top:${y.toFixed(1)}%`; };
    const ghostArc = arc(50, 50, 49.2, 20, 150);
    const lab = (r, deg, html, cls) => `<div class="rl ${cls || ""}" style="${at(r, deg)}">${html}</div>`;
    const blk = (k, who, cap, ic) => `<div class="coreblk ${k}" style="top:50%;transform:translate(-50%,-50%);left:${k === "g7" ? 38 : 62}%;width:22%">${num(D, `rings.core.${k}.direction`, "kn")}<span class="cap">${who}<br>${cap}</span></div>`;
    const svg = `<div class="rings" role="group" aria-label="Layers of evidence, as concentric rings">
      <svg viewBox="0 0 100 100" aria-hidden="true"><path class="rg ghost" d="${ghostArc}"/><circle class="rg" cx="50" cy="50" r="45"/><circle class="rg dot" cx="50" cy="50" r="35"/><circle class="rg core" cx="50" cy="50" r="24"/></svg>
      ${lab(24, 0, "CORE", "h")}${lab(35, 0, "MIDDLE &middot; the model recognises these", "h")}${lab(45, 0, "OUTER &middot; synthetic hard cases", "h")}
      <div class="coreline" style="left:50%;right:auto;top:38%;height:24%;border-top:0;border-left:1px solid var(--line)"></div>
      ${blk("g7", "G7", "bar FAILED")}${blk("g8", "G8", "clauses met")}
      ${lab(35, -62, `<b>${num(D, "rings.mid.textbook", "kn")}</b> textbook<br>size within tolerance`)}
      ${lab(35, 128, `undisguised real case<br><b>${num(D, "rings.mid.undisguised_dir", "kn")}</b> direction &middot; <b>${num(D, "rings.mid.undisguised_size", "kn")}</b> size`)}
      ${lab(45, 222, `loop <b>${num(D, "rings.outer.loop_sign", "kn")}</b> sign<br><b>${num(D, "rings.outer.loop_fa", "kn")}</b> false alarms`)}
      ${lab(45, 138, `rules <b>${num(D, "rings.outer.rules_sign", "kn")}</b> sign<br><b>${num(D, "rings.outer.rules_fa", "kn")}</b> false alarms`)}
      ${lab(49.2, 96, `<span style="display:block;white-space:normal;width:150px;text-align:left">reading only: <b>${num(D, "rings.ghost.reading_dir", "kn")}</b> right, <b>${num(D, "rings.ghost.reading_fa", "kn")}</b> false alarms on the clean twin</span>`)}</div>`;
    const li = (path, txt, f, b) => `<li>${num(D, path, f || "kn")}<span>${txt}</span>${badge(b)}</li>`;
    const gl = '<svg class="ringglyph" viewBox="0 0 56 56" aria-hidden="true"><circle cx="28" cy="28" r="26" fill="none" stroke="var(--line)"/><circle cx="28" cy="28" r="17" fill="none" stroke="var(--ink2)" stroke-dasharray="1 4" stroke-linecap="round"/><circle cx="28" cy="28" r="8" fill="none" stroke="var(--ink)" stroke-width="1.5"/></svg>';
    const gblock = (k, ttl, line, ic, v) => `<div><div class="cap">${ttl}</div><p style="margin:6px 0 8px;font-size:14px;line-height:22px">${line}</p>${vd(v, ic)}<p class="xs muted" style="margin:8px 0 0">direction ${num(D, `rings.core.${k}.direction`, "kn")} &middot; clean false alarms ${num(D, `rings.core.${k}.false_alarms`, "kn")} &middot; harness failures ${num(D, `rings.core.${k}.inconclusive`, "kn")}</p></div>`;
    const list = `<div class="layerlist">
      <div class="layer">${gl}<h3>Core &middot; the disguised real case ${badge("REAL-PINNED")}</h3><div class="both">
        ${gblock("g7", "G7", "Preregistered bar FAILED (direction " + fmt(c.g7.direction, "kn") + ").", "BAR FAILED", "NOTMET")}
        ${gblock("g8", "G8, new labelled run", "Clauses (a) to (c) met, harness target missed.", "CLAUSES MET", "SURVIVED")}</div>
        <p class="xs muted" style="margin:10px 0 0">Two separate runs, two separate scores, never merged. ${esc(c.g7.src)}, ${esc(c.g8.src)}</p></div>
      <div class="layer"><h3>Middle &middot; sources the model recognises</h3><ul>
        ${li("rings.mid.textbook", "textbook case, size within tolerance", "kn", "TEXTBOOK")}
        ${li("rings.mid.undisguised_dir", "undisguised real case, direction", "kn", "REAL-PINNED")}
        ${li("rings.mid.undisguised_size", "undisguised real case, size within tolerance", "kn", "REAL-PINNED")}</ul>
        <p class="xs muted" style="margin:8px 0 0">Dotted edge: the model recognises these. They cannot separate running from remembering.</p></div>
      <div class="layer"><h3>Outer &middot; synthetic hard cases</h3><ul>
        ${li("rings.outer.loop_sign", "loop, hard-case sign right", "kn", "SYNTHETIC")}${li("rings.outer.loop_fa", "loop, false alarms on clean cases", "kn", "SYNTHETIC")}
        ${li("rings.outer.rules_sign", "fixed rules, no model, sign right", "kn", "SYNTHETIC")}${li("rings.outer.rules_fa", "fixed rules, false alarms", "kn", "SYNTHETIC")}</ul></div>
      <div class="layer"><h3>Ghost arc &middot; reading only</h3><ul>
        ${li("rings.ghost.reading_dir", "right on the leaky case (one prompt, no execution)", "kn", "REAL-PINNED")}
        ${li("rings.ghost.reading_fa", "false alarms on the clean twin", "kn", "REAL-PINNED")}</ul></div></div>`;
    return { svg, list };
  }

  root.NLV = { esc, get, fmt, num, badge, IC, vd, flow, gauge, readout, intervals, rings, ang, NODES };
})(typeof window !== "undefined" ? window : globalThis);
