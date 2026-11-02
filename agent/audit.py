"""Reviewer report (EVAL-8 task 2): one self-contained page built ONLY from files that already exist. No API call, no network.

    python -m agent.audit <case_dir_or_run_dir> [--case NAME] [--repeat K] [--run FILE] --report out.html|out.md [--remeasure]

Input: a case dir (has train.py, excerpt.md; the run is looked up in runs_g*/ and runs_rulefix/) or a run dir (runs_g6/ ...,
then --case picks the case when the dir holds several). Supported run files: loop runs (rK.json with a "loop" section, g5/g6/g7)
and rule-baseline records (runs_rulefix/<case>.json).

The report states: the claim as written (with source), claimed vs controlled score (95% interval from an UNPAIRED bootstrap,
seeds, n), the exact patch diff, the fidelity-check result (stored and re-audited), the preregistration hash and timestamp, a rerun
command, what was not tested, a provenance badge (SYNTHETIC / REAL-PINNED / TEXTBOOK / MOCK), the finding mapped to a leakage type
(Kapoor & Narayanan, arXiv:2207.07048), a suggested reviewer note and a ~150-word plain-text block to copy.
Deterministic: the same files give the same bytes (no clock, no randomness). --remeasure is the only step that executes code
(the stored patches in the local sandbox, still no API) and it appends its comparison to the report."""
import argparse
import difflib
import hashlib
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True

TAXONOMY = {  # Kapoor & Narayanan, arXiv:2207.07048
    "L1.1": ("No test set", "an evaluation on rows the model was not fit on (a held-out test set)"),
    "L1.2": ("Pre-processing on training and test set", "fitting the preprocessing step inside each training fold only"),
    "L1.3": ("Feature selection jointly on training and test data", "repeating feature selection inside each training fold only"),
    "L1.4": ("Duplicates in data", "removing duplicate rows before the train/test split"),
    "L2": ("Illegitimate features", "a justification that every input is available at prediction time, or removal of the offending input"),
    "L3.1": ("Temporal leakage", "a time-ordered split that matches the intended forecasting use"),
    "L3.2": ("Non-independence between train and test samples", "a split that keeps related samples (the same patient, site, compound or well) on one side"),
    "L3.3": ("Sampling bias", "a description of how the sample was drawn and why it represents the target population"),
}
KEYWORDS = {
    "L1.1": ["train==test", "in-sample", "same rows", "idx, idx", "resubstitution", "apparent", "scored on the training", "no held-out",
             "no test set", "returns the same", "identical indices"],
    "L1.2": ["scaler", "standardscaler", "pca", "normaliz", "standardis", "standardiz", "impute", "imputation", "fit_transform", "preprocess",
             "pre-process", "mean imputation", "fillna"],
    "L1.3": ["selectkbest", "f_classif", "feature selection", "screen", "corrcoef", "select(", "selector", "most informative", "top-k"],
    "L1.4": ["duplicate", "drop_duplicates", "near-duplicate", "augment"],
    "L2": ["proxy", "post-outcome", "target mean", "target-conditioned", "label into features", "leaks the label", "illegitimate",
           "not available at prediction", "carrier_late_rate", "groupby(target)", "[target].transform"],
    "L3.1": ["temporal", "chronolog", "forecast", "time-ordered", "future", "sort_values", "shuffle=false", "look-ahead", "lookahead", "shift("],
    "L3.2": ["group", "patient", "ward", "site", "compound", "replicate", "well ", "wells", "non-independ", "identity across", "same subject"],
    "L3.3": ["sampling bias", "not representative", "convenience sample"],
}
KIND_HINT = {"feature": "L2"}  # a declared 'feature' fix = a column/input the claim should not use
TEMPORAL_WORDS = ("forecast", "future", "later year", "later period", "prospective", "temporal", "chronolog", "ahead", "upcoming")
RULE_TYPES = {"R1": "L1.1", "R3": "L3.2", "R4": "L3.1", "R5": "L1.4"}


def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def case_sign(stats_by_seed):
    """Same rule as g4.case_sign: per-seed sign of the 95% interval of the fix_both drop; case sign = category of >= 2 of 3 seeds."""
    cats = []
    for s in sorted(stats_by_seed):
        lo, hi = stats_by_seed[s]["full"]["drop_ci"]["fix_both"]
        cats.append("+" if lo > 0 else ("-" if hi < 0 else "0"))
    for k in ("+", "-", "0"):
        if cats.count(k) >= 2:
            return k, cats
    return "mixed", cats


# ---------------- locating the run ----------------
def _repeat_num(path):
    m = re.match(r"r(\d+)$", Path(path).stem)
    return int(m.group(1)) if m else None


def _candidates(case_name, search_dirs):
    out = []
    for d in search_dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for f in sorted(d.glob("r[0-9]*.json")):
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(j, dict) and isinstance(j.get("loop"), dict) and case_name in j["loop"]:
                out.append({"kind": "loop", "file": f, "dir": d, "repeat": _repeat_num(f), "rec": j["loop"][case_name], "run": j})
        f = d / f"{case_name}.json"
        if f.exists():
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(j, dict) and j.get("tool", "").startswith("rulefix"):
                out.append({"kind": "rulefix", "file": f, "dir": d, "repeat": None, "rec": j, "run": j})
    return out


def locate(path, case=None, repeat=None, run=None, root=ROOT):
    """-> (case_dir, case_name, candidate). Raises SystemExit with a plain message when it cannot decide."""
    p = Path(path)
    if not p.is_absolute() and not p.exists():
        p = Path(root) / p
    if not p.exists():
        raise SystemExit(f"audit: {path} does not exist")
    if (p / "train.py").exists():                       # a case dir
        case_name = p.name
        dirs = sorted([d for d in Path(root).glob("runs_*") if d.is_dir()], reverse=True)
        case_dir = p
    else:                                               # a run dir
        names = set()
        for f in p.glob("r[0-9]*.json"):
            try:
                names |= set((json.loads(f.read_text(encoding="utf-8")).get("loop") or {}))
            except (OSError, ValueError):
                pass
        names |= {f.stem for f in p.glob("*.json") if f.stem not in ("score", "ref", "probe", "replay", "plan", "b3", "loop")
                  and f.read_text(encoding="utf-8")[:400].find('"tool": "rulefix') >= 0}
        if case is None:
            if len(names) == 1:
                case = next(iter(names))
            else:
                raise SystemExit(f"audit: {p} holds {len(names)} cases ({', '.join(sorted(names))}); pick one with --case")
        case_name, dirs = case, [p]
        case_dir = None
        for sub in ("factorial", "corpus", "real"):
            if (Path(root) / sub / case_name / "train.py").exists():
                case_dir = Path(root) / sub / case_name
        if case_dir is None:
            raise SystemExit(f"audit: no case directory named {case_name} under factorial/, corpus/ or real/")
    if run:
        dirs = [Path(run).parent]
    cands = _candidates(case_name, dirs)
    if run:
        cands = [c for c in cands if Path(c["file"]).resolve() == Path(run).resolve()]
    if repeat is not None:
        cands = [c for c in cands if c["repeat"] == repeat]
    cands = [c for c in cands if c["kind"] == "rulefix" or (c["rec"].get("status") == "ok")]
    if not cands:
        raise SystemExit(f"audit: no finished run of {case_name} found (searched {[str(d) for d in dirs]}); "
                         "a run needs status ok with stored sources")
    loops = [c for c in cands if c["kind"] == "loop"]
    pick = (loops or cands)[0]
    if case_dir is None or not (case_dir / "excerpt.md").exists():
        raise SystemExit(f"audit: {case_name} has no excerpt.md")
    return case_dir, case_name, pick


# ---------------- facts ----------------
def read_claim(case_dir):
    exc = (Path(case_dir) / "excerpt.md").read_text(encoding="utf-8")
    m = re.search(r"##\s*Results\s*\n(.*)", exc, re.S)
    results = (m.group(1) if m else exc).strip()
    methods = exc.split("## Results")[0].replace("## Methods (excerpt)", "").strip()
    nums = re.findall(r"\d+(?:\.\d+)?\s*%|\b0\.\d+\b", results)
    return {"results": results, "methods": methods, "number": nums[0].replace(" ", "") if nums else None,
            "source_file": f"{Path(case_dir).parent.name}/{Path(case_dir).name}/excerpt.md", "source_sha256": sha256_file(Path(case_dir) / "excerpt.md")}


def provenance(case_dir, case_name, cand, root=ROOT):
    """-> (badge, source citation or None, extras dict). Truth files are host-side metadata (never shown to an agent)."""
    extras = {}
    if "mock" in str(cand["dir"].name).lower() or "MOCK" in str((cand["rec"].get("final_plan") or {}).get("mode", "")).upper():
        return "MOCK", None, extras
    for tf in ("g6_truth.json", "g7_truth.json"):
        p = Path(root) / "eval" / tf
        if p.exists():
            try:
                t = json.loads(p.read_text(encoding="utf-8")).get(case_name)
            except ValueError:
                t = None
            if t:
                src = t.get("original_paper") or t.get("source")
                if t.get("reanalysis"):
                    src = f"{src}. Published correction: {t['reanalysis']}"
                extras = {"flaw": t.get("flaw"), "not_reproduced": t.get("related_reanalysis_not_reproduced"), "port": t.get("port_notes"),
                          "published": t.get("published_numbers")}
                return t.get("provenance", "SYNTHETIC"), src, extras
    if Path(case_dir).parent.name in ("factorial", "corpus"):
        return "SYNTHETIC", None, extras
    return "SYNTHETIC", None, extras


def probe_status(run_dir, case_name):
    p = Path(run_dir) / "probe.json"
    if not p.exists():
        return None
    try:
        j = json.loads(p.read_text(encoding="utf-8")).get(case_name)
    except ValueError:
        return None
    if not j:
        return None
    return {k: v.get("status") for k, v in j.items()}


def prereg_info(run_dir, case_name, repeat):
    """Earliest preregistration record of this case-repeat plus the scoring rule record, from prereg_log.jsonl / PREREG.sha256."""
    run_dir, out = Path(run_dir), {"records": [], "rule": None, "file": None}
    log = run_dir / "prereg_log.jsonl"
    if log.exists():
        rows = []
        for ln in log.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(ln))
            except ValueError:
                pass
        for r in rows:
            if r.get("case") == case_name and r.get("kind", "").startswith("loop_planner") and (repeat is None or str(r.get("repeat", "")).endswith(f"r{repeat}")):
                out["records"].append({"kind": r["kind"], "repeat": r.get("repeat"), "utc": r["utc"], "sha256": r["sha256"]})
        for r in rows:
            if r.get("kind", "").endswith("scoring_rule") or r.get("kind") == "rulefix_prereg":
                out["rule"] = {"kind": r["kind"], "utc": r["utc"], "sha256": r["sha256"]}
                break
        out["file"] = log.relative_to(ROOT).as_posix() if log.is_relative_to(ROOT) else log.as_posix()
    return out


def _norm_src(src):
    import ast
    return ast.unparse(ast.parse(src))


def patch_diff(case_dir, rec, cfg="fix_both"):
    """Unified diff of the executed patch against the claim's train.py (both through ast.unparse, so formatting noise is gone)."""
    src = rec["sources"][cfg]
    orig = _norm_src((Path(case_dir) / "train.py").read_text(encoding="utf-8"))
    new = _norm_src(src)
    tail = "def controlled_eval(df, seed):\n    return claimed_eval(df, seed)"
    new = new.replace(tail, "").rstrip("\n")
    hdr = ["import numpy as np", "import pandas as pd", "from sklearn.model_selection import GroupShuffleSplit, train_test_split"]
    nl = new.splitlines()
    if nl[:3] == hdr:  # the rule baseline prepends the imports its remedies need; they are not a step of the claim
        nl = nl[3:]
    d = list(difflib.unified_diff(orig.splitlines(), nl, "train.py (claim)", f"{cfg} (executed)", lineterm="", n=2))
    return "\n".join(d)


def reaudit(case_dir, rec, data_header):
    """Re-run the deterministic fidelity guard on the stored plan (loop runs only). Offline."""
    out = {"stored": rec.get("fidelity"), "recomputed": None, "sources_match": None, "justification": None, "problems": []}
    plan = rec.get("final_plan") or {}
    if not plan.get("edits"):
        out["problems"].append("no structured edits stored (legacy or rule-baseline record): static re-audit not applicable")
        return out
    sys.path.insert(0, str(ROOT))
    from agent import fidelity
    src = (Path(case_dir) / "train.py").read_text(encoding="utf-8")
    exc = (Path(case_dir) / "excerpt.md").read_text(encoding="utf-8")
    cfgs = fidelity.build_configs(src, plan["edits"])
    problems, rep = [], {}
    for cfg, info in cfgs.items():
        v = list(info["violations"])
        if not v:
            sv, r = fidelity.check_static(src, info["src"], info["kinds"], info["declared"])
            v += sv
            rep[cfg] = fidelity.verdict_line(info, r)
        problems += [f"{cfg}: {x}" for x in v]
    out["recomputed"] = rep
    out["sources_match"] = {c: (cfgs[c]["src"] == (rec.get("sources") or {}).get(c)) for c in cfgs}
    if data_header:
        out["justification"] = fidelity.check_justification(src, exc, data_header, plan)
        problems += [f"justification: {x}" for x in out["justification"]]
    out["problems"] = problems
    return out


def _kw_hits(text, kws):
    return sorted({w for w in kws if re.search(r"(?<![a-z0-9])" + re.escape(w), text)})


def classify(rec, kind, diff_text, meas):
    """Map the finding to Kapoor & Narayanan leakage types (deterministic, keyword-based; the report says so).
    One entry per factor (A, B): the type with most hits in that factor's description plus its declared kind; entries are ranked by the
    factor's measured mean drop, so the primary type belongs to the factor that carries more of the effect."""
    out = []
    if kind == "rulefix":
        for X, ids in (("A", ("R1", "R3", "R4", "R5")), ("B", ("R2",))):
            applied = [r for r in rec["configs"][f"fix_{X}"]["rules_applied"] if r in ids]
            for r in applied:
                if r == "R2":
                    ctor = (rec["fired"].get("R2") or {}).get("transformers") or []
                    t, why = ("L1.3" if any("Select" in c for c in ctor) else "L1.2"), f"rule R2 refit {', '.join(ctor)} on the training rows only"
                else:
                    t, why = RULE_TYPES[r], f"rule {r} fired and was applied"
                out.append({"factor": X, "type": t, "evidence": [why]})
    else:
        plan = rec.get("final_plan") or {}
        edits = plan.get("edits") or {}
        added = "\n".join(ln[1:] for ln in diff_text.splitlines() if ln.startswith("+") and not ln.startswith("+++")).lower()
        for X in ("A", "B"):
            text = str(plan.get(X, "")).lower()
            kind_x = (edits.get(X) or {}).get("kind")
            score, ev = {}, {}
            for t, kws in KEYWORDS.items():
                hits = _kw_hits(text, kws)
                if hits:
                    score[t] = len(hits)
                    ev[t] = [f"the planner's description of suspect step {X} mentions {', '.join(repr(h) for h in hits)}"]
            if kind_x in KIND_HINT:
                t = KIND_HINT[kind_x]
                score[t] = score.get(t, 0) + 1
                ev.setdefault(t, []).append(f"fix {X} is declared kind '{kind_x}'")
            if score:
                t = sorted(score, key=lambda k: (-score[k], list(TAXONOMY).index(k)))[0]
                out.append({"factor": X, "type": t, "evidence": ev[t]})
        if not out:  # no description: fall back on the patch text
            for t, kws in KEYWORDS.items():
                hits = _kw_hits(added, kws)
                if hits:
                    out.append({"factor": "both", "type": t, "evidence": [f"the patch adds code mentioning {', '.join(repr(h) for h in hits)}"]})
    drop = {"A": abs(meas["mean_A"]), "B": abs(meas["mean_B"]), "both": abs(meas["mean_drop"])}
    out.sort(key=lambda d: (-drop[d["factor"]], list(TAXONOMY).index(d["type"])))
    seen, res = set(), []
    for d in out:
        if d["type"] in seen:
            for r in res:
                if r["type"] == d["type"]:
                    r["evidence"] += d["evidence"]
            continue
        seen.add(d["type"])
        res.append({"type": d["type"], "label": TAXONOMY[d["type"]][0], "factor": d["factor"], "evidence": d["evidence"],
                    "suggestion": TAXONOMY[d["type"]][1]})
    return res


# ---------------- measurement table ----------------
def measurement(rec):
    st = rec["stats"]
    metric = rec.get("metric") or (st[sorted(st)[0]]["full"].get("metric")) or "accuracy"
    rows = []
    for s in sorted(st):
        f = st[s]["full"]
        rows.append({"seed": s, "claimed": f["acc"]["orig"], "controlled": f["acc"]["fix_both"], "drop": f["drop"]["fix_both"],
                     "ci": f["drop_ci"]["fix_both"], "n_claimed": f["n"]["orig"], "n_controlled": f["n"]["fix_both"],
                     "A": f["drop"]["fix_A"], "A_ci": f["drop_ci"]["fix_A"], "B": f["drop"]["fix_B"], "B_ci": f["drop_ci"]["fix_B"],
                     "I": f["I"], "I_ci": f["I_ci"]})
    mean = lambda k: sum(r[k] for r in rows) / len(rows)  # noqa: E731
    sign, cats = case_sign(st)
    return {"metric": metric, "rows": rows, "mean_claimed": mean("claimed"), "mean_controlled": mean("controlled"), "mean_drop": mean("drop"),
            "mean_A": mean("A"), "mean_B": mean("B"), "mean_I": mean("I"), "sign": sign, "per_seed_sign": cats}


def _fmt(x, metric, signed=False):
    if metric == "accuracy":
        return f"{x * 100:+.1f} pp" if signed else f"{x * 100:.1f}%"
    return f"{x:+.3f}" if signed else f"{x:.3f}"


def _ci(ci, metric):
    return f"[{_fmt(ci[0], metric, True)}, {_fmt(ci[1], metric, True)}]".replace(" pp", "")


def reviewer_texts(F):
    """-> (suggested note paragraphs, ~150-word copy block). Plain, hedged, and honest about the sign of the finding."""
    m, sign, metric = F["meas"], F["meas"]["sign"], F["meas"]["metric"]
    unit = "accuracy" if metric == "accuracy" else {"pr_auc": "PR-AUC", "roc_auc": "ROC-AUC"}.get(metric, metric)
    top = F["types"][0] if F["types"] else None
    steps = ", ".join(F["steps_changed"]) or "the evaluation step"
    claimed = _fmt(m["mean_claimed"], metric)
    ctrl = _fmt(m["mean_controlled"], metric)
    drop = _fmt(m["mean_drop"], metric, True)
    seeds = "/".join(str(r["seed"]) for r in m["rows"])
    ncl = sorted({r["n_claimed"] for r in m["rows"]})
    nct = sorted({r["n_controlled"] for r in m["rows"]})
    nn = f"{'/'.join(map(str, ncl))} rows scored by the claim, {'/'.join(map(str, nct))} after the change"
    ci_txt = "; ".join(f"seed {r['seed']} {_ci(r['ci'], metric)}" for r in m["rows"])
    what = {"L1.1": "the model is scored on rows it was fit on", "L1.2": "preprocessing is fit on rows that are later scored",
            "L1.3": "feature selection sees the rows that are later scored", "L1.4": "duplicate rows can sit on both sides of the split",
            "L2": "an input that may not be available at prediction time is used", "L3.1": "the hold-out is not ordered in time",
            "L3.2": "related samples sit on both sides of the split", "L3.3": "the sample may not represent the target population"}
    reason = what.get(top["type"], "the evaluation protocol differs from the intended use") if top else "the evaluation protocol differs from the intended use"
    if sign == "+":
        para = [f"The headline result ({F['claim']['number'] or 'as reported'}) appears to depend on the evaluation protocol: {reason}.",
                f"In our reanalysis the code was run with only {steps} changed (fidelity guard: {F['fidelity_line']}). The same model then scored {ctrl} "
                f"against {claimed} under the claimed protocol (metric: {unit}), a drop of {drop} (mean of seeds {seeds}; 95% unpaired-bootstrap intervals for the drop: {ci_txt}; {nn}).",
                (f"This matches the leakage pattern '{top['label']}' ({top['type']}, Kapoor and Narayanan 2023). " if top else "")
                + f"We would ask the authors to report the score under {top['suggestion'] if top else 'a protocol matched to the intended use'}, "
                "or to explain why the current protocol is appropriate for the stated use.",
                "We did not re-run the authors' original pipeline and cannot rule out that other choices explain part of the gap."]
        npos = sum(1 for r in m["rows"] if r["ci"][0] > 0)
        short = (f"The reported result ({F['claim']['number'] or 'headline figure'}) may be inflated: {reason}. With only {steps} changed, "
                 f"the same model scores {ctrl} instead of {claimed} {unit} ({drop}, mean of seeds {seeds}). The 95% unpaired-bootstrap interval for the drop "
                 f"excludes zero on {npos} of {len(m['rows'])} seeds ({ci_txt}); {nn}. Separately, step A alone moves the score by "
                 f"{_fmt(m['mean_A'], metric, True)}, step B alone by {_fmt(m['mean_B'], metric, True)}, and their interaction by {_fmt(m['mean_I'], metric, True)}. "
                 f"Pattern: {top['label'] if top else 'protocol mismatch'}"
                 f"{' (' + top['type'] + ', Kapoor and Narayanan)' if top else ''}. "
                 f"Please report the score under {top['suggestion'] if top else 'a protocol matched to the intended use'}, or justify the current protocol. "
                 f"Caveat: we re-ran the evaluation code supplied, not the authors' full pipeline; {F['n_untested']} limits are listed in the audit report.")
    elif sign == "0":
        para = [f"We tried to check whether the headline result ({F['claim']['number'] or 'as reported'}) depends on the evaluation protocol.",
                f"With only {steps} changed ({F['fidelity_line']}) the same model scored {ctrl} against {claimed} under the claimed protocol (metric: {unit}) ({drop}); the 95% unpaired-bootstrap "
                f"interval for the drop spans zero on at least two of three seeds ({ci_txt}). We found no evidence of inflation from this change. "
                "That is not proof that none exists.",
                "We did not re-run the authors' original pipeline and tested only the changes listed in the audit report."]
        short = (f"No evidence of inflation found for the reported result ({F['claim']['number'] or 'headline figure'}). With only {steps} changed the same model "
                 f"scores {ctrl} against {claimed} {unit} under the claimed protocol ({drop}; seeds {seeds}); the 95% unpaired-bootstrap interval for the drop spans zero on at least two of three seeds. "
                 f"This is absence of evidence, not proof of absence: {nn}. We re-ran the evaluation code supplied, not the authors' full pipeline, and tested only "
                 f"the change described; {F['n_untested']} limits are listed in the audit report. No action requested on this point.")
    else:
        para = [f"With only {steps} changed the same model scored {ctrl} against {claimed} {unit} under the claimed protocol ({drop}), so this change does not support an inflation "
                f"reading (sign '{sign}', intervals: {ci_txt}).", "We did not re-run the authors' original pipeline."]
        short = (f"The change tested ({steps}) does not support an inflation reading of the reported result: the controlled score is {ctrl} against {claimed} {unit} under the claimed protocol "
                 f"({drop}; seeds {seeds}; sign '{sign}'; {nn}). We re-ran the evaluation code supplied, not the authors' full pipeline, and the check is limited to "
                 f"the change described; {F['n_untested']} limits are listed in the audit report. No action requested.")
    return para, short


def untested(F):
    L = []
    ex = F["extras"]
    if F["kind"] == "rulefix":
        L.append("This record comes from a fixed rule library with no model: it applies standard remedies to code idioms it recognises and cannot reason about the claim.")
    L.append("We re-ran the evaluation code in the case folder, not the authors' original pipeline, raw data or software versions."
             + (f" Port notes: {ex['port']}" if ex.get("port") else ""))
    L.append("Only two evaluation steps (factors A and B) were varied per run. Other leakage types were not examined, and the model, metric and features are held fixed by construction.")
    L.append("Intervals come from an unpaired bootstrap over test rows for 3 seeds (42/43/44). They do not cover variation across training sets, "
             "model initialisations or a fresh draw of the data.")
    exc = (F["claim"]["methods"] + " " + F["claim"]["results"]).lower()
    if any(w in exc for w in TEMPORAL_WORDS) and F["kind"] == "loop" and "L3.1" not in [t["type"] for t in F["types"]]:
        L.append("The excerpt states a forecasting use, but the control used here is not a time-ordered hold-out; a temporal control may give a different size of inflation.")
    if ex.get("not_reproduced"):
        L.append(f"Not tested: {ex['not_reproduced']}")
    if F["probe"]:
        bad = [k for k, v in F["probe"].items() if v and str(v).startswith("FAIL")]
        if bad:
            L.append("Contamination: the model that proposed the fix recognised the source of this case in the memorisation probe "
                     f"({', '.join(bad)}), so its choice of what to fix may be recalled rather than discovered. The measured numbers come from the sandbox, not from the model.")
    if F["provenance"] == "SYNTHETIC":
        L.append("The case is synthetic (built by NullLab). A real study can differ in ways that matter.")
    if F["provenance"] == "MOCK":
        L.append("MOCK: produced by a stub, not by a live model. Do not cite as evidence.")
    if F["meas"]["rows"] and any(r["n_controlled"] < 100 for r in F["meas"]["rows"]):
        L.append(f"Small scored sample ({min(r['n_controlled'] for r in F['meas']['rows'])} rows after the change): intervals are wide.")
    return L


def build_finding(path, case=None, repeat=None, run=None, root=ROOT, remeasure=None):
    case_dir, case_name, cand = locate(path, case, repeat, run, root)
    rec, kind = cand["rec"], cand["kind"]
    claim = read_claim(case_dir)
    badge, source, extras = provenance(case_dir, case_name, cand, root)
    meas = measurement(rec)
    diff = patch_diff(case_dir, rec, "fix_both")
    header = None
    dp = Path(case_dir) / "data.csv"
    if dp.exists():
        with dp.open(encoding="utf-8") as fh:
            header = fh.readline().strip().split(",")
    audit = reaudit(case_dir, rec, header) if kind == "loop" else {"stored": None, "recomputed": None, "sources_match": None, "justification": None,
                                                                   "problems": ["rule-baseline record: no model-written plan to audit"]}
    if kind == "loop":
        mm = re.search(r"step\(s\) (.*?) changed", (rec.get("fidelity") or {}).get("fix_both", ""))
        steps = mm.group(1).split(", ") if mm else []
        fid_line = (rec.get("fidelity") or {}).get("fix_both", "fidelity line not stored")
    else:
        steps = list(rec["configs"]["fix_both"]["steps"])
        fid_line = f"rules applied {', '.join(rec['configs']['fix_both']['rules_applied']) or 'none'}; steps changed {', '.join(steps) or 'none'}"
    rel = lambda p: str(Path(p).resolve().relative_to(Path(root).resolve())).replace("\\", "/") if Path(p).resolve().is_relative_to(Path(root).resolve()) else str(p)  # noqa: E731
    types = classify(rec, kind, diff, meas)
    pre = prereg_info(cand["dir"], case_name, cand["repeat"])
    if kind == "rulefix":
        pf = Path(cand["dir"]) / "PREREG.sha256"
        pre["file"] = rel(pf) if pf.exists() else None
        pre["prereg_md_sha256"] = pf.read_text().split()[0] if pf.exists() else None
    A = (rec.get("final_plan") or {}).get("A")
    B = (rec.get("final_plan") or {}).get("B")
    rerun = f"python -m agent.audit {rel(case_dir)} --run {rel(cand['file'])} --case {case_name}" + (f" --repeat {cand['repeat']}" if cand["repeat"] else "") + " --remeasure --report out.html"
    F = {"case": case_name, "case_dir": rel(case_dir), "kind": kind, "run_file": rel(cand["file"]), "repeat": cand["repeat"], "claim": claim,
         "provenance": badge, "source": source, "extras": extras, "meas": meas, "diff": diff, "steps_changed": steps,
         "fidelity_line": fid_line, "audit": audit, "types": types, "prereg": pre, "rerun": rerun, "A": A, "B": B,
         "probe": probe_status(cand["dir"], case_name), "retries": rec.get("retries"), "sources_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in rec["sources"].items()},
         "per_config_diffs": {c: patch_diff(case_dir, rec, c) for c in ("fix_A", "fix_B") if c in rec["sources"]}, "remeasure": remeasure}
    F["untested"] = untested(F)
    F["n_untested"] = len(F["untested"])
    F["note_paragraphs"], F["note_short"] = reviewer_texts(F)
    return F


# ---------------- remeasure (executes the stored patches in the local sandbox; no API) ----------------
def remeasure(path, case=None, repeat=None, run=None, root=ROOT, n_boot=1000):
    sys.path.insert(0, str(ROOT))
    from sandbox import executor, factorial_stats
    case_dir, case_name, cand = locate(path, case, repeat, run, root)
    rec = cand["rec"]
    ex = executor.run_factorial(case_dir, {k: rec["sources"][k] for k in ("fix_A", "fix_B", "fix_both")}, seeds=(42, 43, 44), timeout=3000)
    if ex["status"] != "ok":
        return {"status": ex["status"], "stderr": ex.get("stderr", "")[-600:]}
    st = factorial_stats.all_seeds(ex["result"], n_boot=n_boot)
    old = rec["stats"]
    diffs = [abs(st[s]["full"]["drop"]["fix_both"] - old[s]["full"]["drop"]["fix_both"]) for s in sorted(old) if s in st]
    return {"status": "ok", "max_abs_delta_drop": max(diffs) if diffs else None,
            "new_sign": case_sign(st)[0], "stored_sign": case_sign(old)[0],
            "new_drops": {s: st[s]["full"]["drop"]["fix_both"] for s in sorted(st)}, "stored_drops": {s: old[s]["full"]["drop"]["fix_both"] for s in sorted(old)}}


# ---------------- rendering ----------------
CSS = """:root{--bg:#F2EFEA;--panel:#FFFFFF;--panel-2:#F7F5F1;--ink:#111111;--ink-2:#3A3631;--muted:#6B655E;--faint:#A8A096;--line:#E3DED6;--line-2:#D2CBC0;
--accent:#E8501F;--accent-ink:#B23A0E;--accent-soft:#FCE9E1;--r-sm:10px;--r-md:16px;--f-sans:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;
--f-mono:ui-monospace,"SF Mono","Cascadia Mono",Consolas,Menlo,monospace;color-scheme:light}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 var(--f-sans)}
main{max-width:920px;margin:0 auto;padding:32px 16px 64px}p,li,blockquote,summary{overflow-wrap:anywhere}
h1{font-size:clamp(24px,4vw,34px);line-height:1.15;margin:0 0 8px}h2{font-size:18px;margin:0 0 10px;letter-spacing:.01em}
.sub{color:var(--muted);margin:0 0 20px}.card{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-md);padding:18px 20px;margin:0 0 14px}
.badge{display:inline-block;border:1px solid var(--line-2);border-radius:999px;padding:2px 10px;font:600 12px var(--f-mono);letter-spacing:.04em;background:var(--panel-2)}
.badge.hot{background:var(--accent-soft);border-color:var(--accent);color:var(--accent-ink)}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}th{color:var(--muted);font-weight:600}
td.n,th.n{text-align:right;font-variant-numeric:tabular-nums}code,pre,.mono{font-family:var(--f-mono);font-size:13px;overflow-wrap:anywhere}.scroll{overflow-x:auto;max-width:100%}
pre{background:var(--panel-2);border:1px solid var(--line);border-radius:var(--r-sm);padding:10px 12px;overflow:auto;white-space:pre-wrap;word-break:break-word;margin:8px 0}
pre.diff .add{color:#1a6b2b}pre.diff .del{color:#a3260d}.k{color:var(--muted)}
blockquote{margin:8px 0;padding:8px 14px;border-left:3px solid var(--accent);background:var(--panel-2)}
button{font:600 13px var(--f-sans);background:var(--accent);color:#fff;border:0;border-radius:999px;padding:8px 16px;cursor:pointer}button:hover{background:var(--accent-ink)}
details{margin:6px 0}summary{cursor:pointer;color:var(--ink-2)}ul{margin:6px 0;padding-left:20px}.warn{color:var(--accent-ink);font-weight:600}
@media (max-width:560px){main{padding:20px 16px 48px}.card{padding:14px}th,td{padding:5px 4px}}"""


def _diff_html(d):
    out = []
    for ln in d.splitlines():
        cls = "add" if ln.startswith("+") and not ln.startswith("+++") else ("del" if ln.startswith("-") and not ln.startswith("---") else "")
        out.append(f'<span class="{cls}">{html.escape(ln)}</span>' if cls else html.escape(ln))
    return "\n".join(out)


def _meas_rows(F):
    m = F["meas"]
    rows = []
    for r in m["rows"]:
        rows.append((r["seed"], _fmt(r["claimed"], m["metric"]), _fmt(r["controlled"], m["metric"]), _fmt(r["drop"], m["metric"], True),
                     _ci(r["ci"], m["metric"]), r["n_claimed"], r["n_controlled"]))
    return rows


def render_html(F):
    e, m = html.escape, F["meas"]
    metric_name = {"accuracy": "accuracy", "pr_auc": "PR-AUC", "roc_auc": "ROC-AUC"}.get(m["metric"], m["metric"])
    sign_txt = {"+": "controlled score is lower: consistent with inflation", "0": "interval spans 0: no evidence of inflation",
                "-": "controlled score is higher: not an inflation", "mixed": "seeds disagree"}[m["sign"]]
    rows = "".join(f"<tr><td class='mono'>{s}</td><td class='n'>{c}</td><td class='n'>{k}</td><td class='n'>{d}</td><td class='n mono'>{ci}</td><td class='n'>{n1}</td><td class='n'>{n2}</td></tr>"
                   for s, c, k, d, ci, n1, n2 in _meas_rows(F))
    mean_row = (f"<tr><td><b>mean</b></td><td class='n'><b>{_fmt(m['mean_claimed'], m['metric'])}</b></td><td class='n'><b>{_fmt(m['mean_controlled'], m['metric'])}</b></td>"
                f"<td class='n'><b>{_fmt(m['mean_drop'], m['metric'], True)}</b></td><td></td><td></td><td></td></tr>")
    pre = F["prereg"]
    pre_html = "".join(f"<li><span class='mono'>{e(r['kind'])}</span> {e(str(r['repeat']))}: <span class='mono'>{e(r['utc'])}</span> sha256 <span class='mono'>{e(r['sha256'])}</span></li>" for r in pre["records"])
    if pre.get("rule"):
        pre_html += f"<li>{e(pre['rule']['kind'])}: <span class='mono'>{e(pre['rule']['utc'])}</span> sha256 <span class='mono'>{e(pre['rule']['sha256'])}</span></li>"
    if pre.get("prereg_md_sha256"):
        pre_html += f"<li>PREREG.md sha256 <span class='mono'>{e(pre['prereg_md_sha256'])}</span></li>"
    if not pre_html:
        pre_html = "<li class='warn'>No preregistration record found next to this run file.</li>"
    au = F["audit"]
    if F["kind"] == "loop":
        sm = au["sources_match"] or {}
        fid = (f"<p>Stored by the loop: <span class='mono'>{e(F['fidelity_line'])}</span></p>"
               f"<p>Re-audited offline now: {'<b>ACCEPT</b>' if not au['problems'] and au['recomputed'] else '<b class=\"warn\">PROBLEMS</b>'}"
               f" (static guard; stored sources identical to the rebuilt ones: {', '.join(f'{k} {v}' for k, v in sm.items()) or 'n/a'}"
               f"{'; justification rules checked' if au['justification'] is not None else '; justification rules skipped (no data header)'}).</p>")
        if au["problems"]:
            fid += "<ul>" + "".join(f"<li class='mono'>{e(p)}</li>" for p in au["problems"]) + "</ul>"
    else:
        fid = f"<p>Rule baseline (no model). <span class='mono'>{e(F['fidelity_line'])}</span></p><p class='k'>{e(au['problems'][0])}</p>"
    types = "".join(f"<li><b>{e(t['type'])} {e(t['label'])}</b>{' (primary)' if i == 0 else ''} <span class='k'>via factor {e(t['factor'])}</span><br><span class='k'>{e('; '.join(t['evidence']))}</span></li>" for i, t in enumerate(F["types"]))
    if not types:
        types = "<li>No taxonomy type matched the patch (unclassified).</li>"
    extra = "".join(f"<details><summary>{e(c)} diff</summary><pre class='diff'>{_diff_html(d) or 'no change'}</pre></details>" for c, d in F["per_config_diffs"].items())
    rem = ""
    if F["remeasure"]:
        r = F["remeasure"]
        rem = (f"<div class='card'><h2>Re-measurement (stored patches re-executed in the local sandbox, no API)</h2><p>Status {e(str(r['status']))}; "
               f"max |difference in mean drop| versus stored: <span class='mono'>{e(str(r.get('max_abs_delta_drop')))}</span>; "
               f"sign stored {e(str(r.get('stored_sign')))}, re-measured {e(str(r.get('new_sign')))}.</p></div>")
    paras = "".join(f"<p>{e(p)}</p>" for p in F["note_paragraphs"])
    src = F["source"] or "Synthetic case built by NullLab; no external source."
    badge_cls = "badge hot" if F["provenance"] in ("MOCK",) else "badge"
    A = f"<p><b>Suspect step A:</b> {e(F['A'])}<br><b>Suspect step B:</b> {e(F['B'])}</p>" if F["A"] else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>NullLab audit {e(F['case'])}</title><style>{CSS}</style></head><body><main>
<h1>Audit: {e(F['case'])}</h1>
<p class="sub"><span class="{badge_cls}">{e(F['provenance'])}</span> <span class="badge">{e(F['kind'].upper())} RUN</span>
<span class="badge">sign {e(m['sign'])}</span> built from <span class="mono">{e(F['run_file'])}</span> without any API call.</p>
<div class="card"><h2>1. Claim as stated</h2><blockquote>{e(F['claim']['results'])}</blockquote>
<p class="k">Methods as stated: {e(F['claim']['methods'])}</p>
<p>Source of the claim text: <span class="mono">{e(F['claim']['source_file'])}</span> (sha256 <span class="mono">{e(F['claim']['source_sha256'][:16])}</span>). Provenance of the case: {e(src)}</p></div>
<div class="card"><h2>2. Claimed vs controlled {e(metric_name)}</h2>
<p>Drop = claimed minus controlled (positive means the claim looks inflated). Interval: 95%, UNPAIRED bootstrap over test rows (n_boot=1000 in the g5/g6 drivers; not stored in the run file). {e(sign_txt)}.</p>
<div class="scroll"><table><tr><th>seed</th><th class="n">claimed</th><th class="n">controlled</th><th class="n">drop</th><th class="n">95% interval of drop</th><th class="n">n claimed</th><th class="n">n controlled</th></tr>{rows}{mean_row}</table></div>
<p class="k">Factors (mean drop): A alone {e(_fmt(m['mean_A'], m['metric'], True))}, B alone {e(_fmt(m['mean_B'], m['metric'], True))}, interaction {e(_fmt(m['mean_I'], m['metric'], True))}. Counts, not rates: 3 seeds, one dataset.</p>{A}</div>
<div class="card"><h2>3. Exact patch: only {e(', '.join(F['steps_changed']) or 'no step')} changed</h2>
<pre class="diff">{_diff_html(F['diff']) or 'no difference from the claim code'}</pre>{extra}</div>
<div class="card"><h2>4. Fidelity check</h2>{fid}</div>
<div class="card"><h2>5. Preregistration</h2><ul>{pre_html}</ul><p class="k">Source: {e(str(pre.get('file')))}. The plan was hashed and logged before any execution.</p></div>
<div class="card"><h2>6. Rerun (offline, no API)</h2><pre>{e(F['rerun'])}</pre></div>{rem}
<div class="card"><h2>7. What we could not test</h2><ul>{''.join(f'<li>{e(x)}</li>' for x in F['untested'])}</ul></div>
<div class="card"><h2>8. Leakage type (Kapoor and Narayanan, arXiv:2207.07048)</h2><ul>{types}</ul>
<p class="k">Mapped by keyword rules from the patch and the planner's description of the suspect step; check it by hand.</p></div>
<div class="card"><h2>9. Suggested note to the authors</h2><blockquote>{paras}</blockquote></div>
<div class="card"><h2>10. Copy as reviewer note</h2><pre id="note">{e(F['note_short'])}</pre>
<button type="button" onclick="var t=document.getElementById('note').innerText;if(navigator.clipboard){{navigator.clipboard.writeText(t)}}else{{var r=document.createRange();r.selectNodeContents(document.getElementById('note'));var s=getSelection();s.removeAllRanges();s.addRange(r);document.execCommand('copy')}}">Copy</button></div>
</main></body></html>
"""


def render_md(F):
    m = F["meas"]
    L = [f"# Audit: {F['case']}", "", f"**Provenance: {F['provenance']}** | {F['kind']} run | sign {m['sign']} | built from `{F['run_file']}` without any API call", "",
         "## 1. Claim as stated", "", "> " + F["claim"]["results"].replace("\n", "\n> "), "", f"Methods as stated: {F['claim']['methods']}", "",
         f"Source of the claim text: `{F['claim']['source_file']}` (sha256 `{F['claim']['source_sha256'][:16]}`). Provenance: {F['source'] or 'Synthetic case built by NullLab; no external source.'}", "",
         f"## 2. Claimed vs controlled ({m['metric']})", "", "Drop = claimed minus controlled. Interval: 95%, unpaired bootstrap over test rows.", "",
         "| seed | claimed | controlled | drop | 95% interval of drop | n claimed | n controlled |", "|---|---|---|---|---|---|---|"]
    L += [f"| {a} | {b} | {c} | {d} | {e_} | {f} | {g} |" for a, b, c, d, e_, f, g in _meas_rows(F)]
    L += [f"| mean | {_fmt(m['mean_claimed'], m['metric'])} | {_fmt(m['mean_controlled'], m['metric'])} | {_fmt(m['mean_drop'], m['metric'], True)} | | | |", "",
          f"Factors (mean drop): A alone {_fmt(m['mean_A'], m['metric'], True)}, B alone {_fmt(m['mean_B'], m['metric'], True)}, interaction {_fmt(m['mean_I'], m['metric'], True)}.", "",
          f"## 3. Exact patch: only {', '.join(F['steps_changed']) or 'no step'} changed", "", "```diff", F["diff"], "```", "", "## 4. Fidelity check", "",
          f"Stored: `{F['fidelity_line']}`", ""]
    if F["kind"] == "rulefix":
        L += [f"Re-audit: not applicable ({F['audit']['problems'][0]})"]
    else:
        L += [f"Re-audit problem: {p}" for p in F["audit"]["problems"]] or ["Re-audit: ACCEPT"]
    L += ["", "## 5. Preregistration", ""]
    L += [f"- {r['kind']} {r['repeat']}: {r['utc']} sha256 `{r['sha256']}`" for r in F["prereg"]["records"]]
    if F["prereg"].get("rule"):
        L.append(f"- {F['prereg']['rule']['kind']}: {F['prereg']['rule']['utc']} sha256 `{F['prereg']['rule']['sha256']}`")
    if F["prereg"].get("prereg_md_sha256"):
        L.append(f"- PREREG.md sha256 `{F['prereg']['prereg_md_sha256']}`")
    L += ["", "## 6. Rerun (offline, no API)", "", "```", F["rerun"], "```", "", "## 7. What we could not test", ""]
    L += [f"- {x}" for x in F["untested"]]
    L += ["", "## 8. Leakage type (Kapoor and Narayanan, arXiv:2207.07048)", ""]
    L += [f"- **{t['type']} {t['label']}**: {'; '.join(t['evidence'])}" for t in F["types"]] or ["- unclassified"]
    L += ["", "## 9. Suggested note to the authors", ""] + [f"> {p}\n>" for p in F["note_paragraphs"]]
    L += ["", "## 10. Copy as reviewer note", "", "```text", F["note_short"], "```", ""]
    return "\n".join(L)


def write_report(F, out):
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    text = render_md(F) if out.suffix.lower() == ".md" else render_html(F)
    out.write_text(text, encoding="utf-8", newline="\n")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m agent.audit", description=__doc__.split("\n")[0])
    ap.add_argument("path", help="case dir or run dir")
    ap.add_argument("--case")
    ap.add_argument("--repeat", type=int)
    ap.add_argument("--run", help="a specific run file (rK.json or runs_rulefix/<case>.json)")
    ap.add_argument("--report", required=True, help="output .html or .md")
    ap.add_argument("--remeasure", action="store_true", help="re-execute the stored patches in the local sandbox (no API) and add the comparison")
    a = ap.parse_args(argv)
    rm = remeasure(a.path, a.case, a.repeat, a.run) if a.remeasure else None
    F = build_finding(a.path, a.case, a.repeat, a.run, remeasure=rm)
    out = write_report(F, a.report)
    print(f"audit report written: {out} ({F['provenance']}, sign {F['meas']['sign']}, {len(F['note_short'].split())}-word note)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
