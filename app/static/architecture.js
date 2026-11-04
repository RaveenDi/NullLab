"use strict";
(() => {
  const page = document.getElementById("architecture-content");
  if (!page) return;
  const $ = id => document.getElementById(id);
  const nodes = [...document.querySelectorAll(".arch-node[data-stage]")];
  const stages = {
    inputs: {tag:"YOUR RESEARCH",kicker:"THE STARTING POINT",title:"Define what the score should mean.",summary:"Start with your question, dataset and intended decision. Chat and notes can suggest a brief with source quotes; the author reviews and saves the declarations. A supplied pipeline is inspected, while a CSV-only path creates a labelled generated baseline.",input:"Research question, exact material bytes, grounded draft suggestions and the author's reviewed study declarations.",output:"A reviewed input version and concrete plan: target, metric, fixed seeds, population, timing, column roles and required split candidates.",boundary:"Suggestions remain drafts until author confirmation. Source/data checks and required-operation preflight run before dispatch; a changed brief or dataset needs a new version. Missing facts remain questions.",artifact:"Question + material versions + reviewed brief + static preflight"},
    baseline: {tag:"LOCAL CHECKS",kicker:"ESTABLISH THE STARTING POINT",title:"Execute the original protocol.",summary:"Read-only source, data and required split checks precede execution. Unsupported adapter shapes or missing group binding block the plan before a baseline or paid audit starts. A ready plan then executes the starting protocol on seeds 42, 43 and 44.",input:"Frozen data and source, declared metric, reviewed intended use and static applicability record.",output:"Original prediction vectors and baseline scores, tied to exact input identity.",boundary:"AST applicability is not runtime acceptance. Data sufficiency, row provenance and model-fidelity guards can still reject a control. Current group tracing requires numeric group metadata. Without a supplied reference, execution does not verify a published score.",artifact:"Static source/data checks → baseline_raw + per-seed scores + hashes"},
    independent: {tag:"MUSE WONDER · OPTIONAL",kicker:"REVIEW BEFORE THE PLAN",title:"Give the method an independent reading.",summary:"Wonder receives the original context and the same intervention contract as the planner. It reviews the methodology before seeing Spark's proposal.",input:"Source, claim, declarations, column names, aggregate diagnostics and the allowed edit contract.",output:"A structured capability assessment, concerns, questions and scope gaps.",boundary:"Supported means the instrument can investigate the concern. It does not mean the original pipeline is valid. This review is advisory and can fail or abstain.",artifact:"independent_review: assessment + concerns + reason"},
    planner: {tag:"MUSE SPARK",kicker:"PROPOSE AN INSPECTABLE INTERVENTION",title:"Choose a testable change.",summary:"Spark proposes a control using typed operations from a fixed vocabulary. It reasons about evaluation design while the compiler supplies the actual changed source.",input:"The supplied evaluation, intended-use context and allowed intervention contract.",output:"Structured JSON describing the suspected flaw, source evidence and typed operations.",boundary:"The planner does not supply arbitrary executable edits. No-flaw, missing-information and unsupported answers remain unmeasured assessments.",artifact:'{"op":"move_into_fold",\n "step":"claimed_eval",\n "call":"oversample"}',artifactLabel:"ILLUSTRATIVE SECOM OPERATION"},
    guard: {tag:"LOCAL CHECKS",kicker:"CHECK THE CHANGE BEFORE MEASURING",title:"A proposal must earn execution.",summary:"Static validation and a behavioral guard check that the operation applies to the original evaluation. A smoke execution traces which records are fitted, scored or seen upstream.",input:"The original source and the proposed typed intervention.",output:"An accepted control or explicit rejection with recorded problems.",boundary:"A control cannot silently replace the classifier or constant hyperparameters. A no-op, unsupported shape or missing model identity is refused.",artifact:"Contract check → runtime trace → accepted/rejected"},
    measurement: {tag:"LOCAL EXECUTION",kicker:"THE EXPERIMENT SUPPLIES THE NUMBERS",title:"Measure the controlled protocol.",summary:"The executor runs the original and accepted control. Host-side statistics validate the vectors and compute the metric, per-seed changes and conditional intervals.",input:"Frozen inputs, compiled controls, fixed seeds and the declared metric.",output:"Raw prediction vectors, original/control scores, differences and uncertainty.",boundary:"Changed baseline predictions stop attribution. Intervals condition on fixed predictions; they exclude training uncertainty. Group/time controls remain descriptive and inconclusive.",artifact:"Predictions → validated vectors → scores + intervals"},
    critique: {tag:"MUSE WONDER · OPTIONAL",kicker:"CHALLENGE THE INTERPRETATION",title:"Keep the objection beside the number.",summary:"After a measured control, Wonder reviews whether the plan and interpretation answer the intended question. A disagreement is preserved with the evidence.",input:"Original context, the independent review, the tested plan and measured summary.",output:"A structured accept/dispute decision and its recorded reason.",boundary:"Acceptance is an advisory assessment, not a new empirical finding. Deterministic uncertainty limits still apply even if a model accepts the interpretation.",artifact:"critic: decision + reason → retained with result"},
    evidence: {tag:"EVIDENCE",kicker:"MAKE THE INVESTIGATION INSPECTABLE",title:"Bind the claim to its artifacts.",summary:"The result retains exact input and control identity, environment, instrument sources, attempted calls and objections. Exports verify that these still match the recorded experiment.",input:"Original job records, immutable input snapshots, tested sources and result vectors.",output:"A measured reproducibility bundle or an explicitly unmeasured assessment ZIP.",boundary:"New data or declarations create a new version; they cannot inherit old measurements. Exports contain data and executable source, so review them before sharing.",artifact:"Inputs + control + predictions + provenance + review"}
  };
  let selected = 0;
  let manuallyPaused = false;
  const media = window.matchMedia("(prefers-reduced-motion: reduce)");

  function select(index, {focus=false, scroll=false}={}) {
    selected = Math.max(0, Math.min(nodes.length - 1, index));
    const key = nodes[selected].dataset.stage;
    const stage = stages[key];
    nodes.forEach((node, i) => {node.setAttribute("aria-pressed", String(i === selected));node.setAttribute("aria-expanded", String(i === selected));node.tabIndex = i === selected ? 0 : -1;});
    $("architectureDetailIndex").textContent = `${String(selected + 1).padStart(2,"0")} / 08`;
    for (const [id, field] of [["Tag","tag"],["Kicker","kicker"],["Title","title"],["Summary","summary"],["Input","input"],["Output","output"],["Boundary","boundary"]]) $("architectureDetail"+id).textContent = stage[field];
    $("architectureArtifactLabel").textContent = stage.artifactLabel || "INSPECTABLE ARTIFACT";
    $("architectureArtifact").textContent = stage.artifact;
    $("architecturePrevious").disabled = selected === 0;
    $("architectureNext").disabled = selected === nodes.length - 1;
    $("architectureDetail").dataset.kind = nodes[selected].classList.contains("arch-node-meta") ? "model" : "local";
    $("architectureAnnouncement").textContent = `Stage ${selected + 1} of 8. ${stage.title}`;
    nodes[selected].parentElement.append($("architectureDetail"));
    drawLinks();
    if (focus) nodes[selected].focus();
    if (scroll) nodes[selected].parentElement.scrollIntoView({behavior:media.matches?"auto":"smooth",block:"start"});
  }

  function motion() {
    const paused = manuallyPaused || media.matches;
    page.dataset.motion = paused ? "paused" : "playing";
    $("architectureMotion").setAttribute("aria-pressed", String(paused));
    $("architectureMotion").disabled = media.matches;
    $("architectureMotionLabel").textContent = media.matches ? "Reduced motion" : paused ? "Resume motion" : "Pause motion";
  }

  function drawLinks() {
    const map = $("architectureMap"), svg = $("architectureConnections"), bounds = map.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    svg.setAttribute("viewBox", `0 0 ${bounds.width} ${bounds.height}`);
    svg.replaceChildren();
    const rectangles = nodes.map(node => node.parentElement.getBoundingClientRect());
    rectangles.slice(0,-1).forEach((a,i) => {
      const b = rectangles[i+1];
      const x=a.left+a.width/2-bounds.left, y1=a.bottom-bounds.top+3, y2=b.top-bounds.top-4;
      const d=`M ${x} ${y1} L ${x} ${y2}`;
      for (const kind of ["base","signal"]) {
        const path=document.createElementNS("http://www.w3.org/2000/svg","path");
        path.setAttribute("d",d);path.setAttribute("class","arch-path-"+kind);
        if (kind==="signal") path.style.animationDelay=`${i*-.47}s`;
        svg.append(path);
      }
      const arrow=document.createElementNS("http://www.w3.org/2000/svg","path");
      arrow.setAttribute("d",`M ${x-4} ${y2-5} L ${x} ${y2} L ${x+4} ${y2-5}`);
      arrow.setAttribute("class","arch-path-arrow");svg.append(arrow);
    });
  }

  nodes.forEach((node,index) => {
    node.addEventListener("click",()=>select(index,{scroll:true}));
    node.addEventListener("keydown",event=>{
      const change={ArrowRight:1,ArrowLeft:-1,ArrowDown:1,ArrowUp:-1}[event.key];
      if (change!==undefined || event.key==="Home" || event.key==="End") {
        event.preventDefault();select(event.key==="Home"?0:event.key==="End"?nodes.length-1:selected+change,{focus:true,scroll:true});
      }
    });
  });
  $("architecturePrevious").addEventListener("click",()=>select(selected-1,{focus:true,scroll:true}));
  $("architectureNext").addEventListener("click",()=>select(selected+1,{focus:true,scroll:true}));
  $("architectureMotion").addEventListener("click",()=>{manuallyPaused=!manuallyPaused;motion();});
  media.addEventListener?.("change",motion);
  window.addEventListener("resize",drawLinks);
  if(window.ResizeObserver)new ResizeObserver(drawLinks).observe($("architectureMap"));
  document.fonts?.ready.then(drawLinks);
  select(0);motion();drawLinks();
})();
