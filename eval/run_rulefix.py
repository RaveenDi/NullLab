"""EVAL-8 driver: the NO-LLM rule-based leakage-fix baseline (baselines/rulefix.py) through the same sandbox, factorial layout
and verdict contract as the loop. NO live call is made here; nothing is spent.

Stages (.venv\\Scripts\\python eval/run_rulefix.py <stage> [--out DIR] [--cases a,b]):
  detect    print which rules fire per case (label-free; no measurement)
  prereg    write <out>/PREREG.md (+ .sha256 and prereg_log.jsonl) BEFORE any measurement; refuses to overwrite
  run       measure: 4 configs x seeds 42/43/44, n_boot=1000, UNPAIRED bootstrap (refuses unless PREREG.md matches the sources)
  score     <out>/score.json: rules vs the loop's runs in runs_g5 / runs_g6 (read-only) and the preregistered comparison
Default out dir: runs_rulefix/. Tests pass a temp --out."""
import argparse
import calendar
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from baselines import rulefix  # noqa: E402

SEEDS, N_BOOT = (42, 43, 44), 1000
CASES = {  # name -> (dir, group)
    "g4_freight_delay": ("factorial/g4_freight_delay", "hard"),
    "g4_pump_inspection": ("factorial/g4_pump_inspection", "hard"),
    "g4_crop_irrigation": ("factorial/g4_crop_irrigation", "hard"),
    "g4_assay_replicates": ("factorial/g4_assay_replicates", "hard"),
    "clean_control": ("corpus/clean_control", "clean"),
    "clean_group_correct": ("corpus/clean_group_correct", "clean"),
    "clean_wine_correct": ("corpus/clean_wine_correct", "clean"),
    "g4_visit_history_clean": ("factorial/g4_visit_history_clean", "clean"),
    "civilwar_apparent": ("real/civilwar_apparent", "real_leaky"),
    "esl_selection": ("real/esl_selection", "real_leaky"),
    "civilwar_temporal_clean": ("real/civilwar_temporal_clean", "real_clean"),
    "esl_selection_clean": ("real/esl_selection_clean", "real_clean"),
    "leak_group": ("corpus/leak_group", "supp"),
    "leak_prescale": ("corpus/leak_prescale", "supp"),
    "leak_proxy": ("corpus/leak_proxy", "supp"),
    "leak_temporal": ("corpus/leak_temporal", "supp"),
}
PUBLISHED = {"civilwar_apparent": {"metric": "pr_auc", "inflation": 0.36}, "esl_selection": {"metric": "accuracy", "inflation": 0.47}}

COMPARISON_RULE = """COMPARISON RULE (fixed before any measurement)
Unit: a case-repeat, as in EVAL-5. The loop has 3 live repeats per G4/G5 case (runs_g5/score.json), so 12 hard case-repeats
(4 hard cases) and 12 clean case-repeats (4 clean cases). The rule baseline is deterministic, so each case is measured ONCE and its
outcome is counted 3 times (x3) to put it on the loop's denominator. Per-case counts (out of 4 and out of 4) are reported next to
these, and the x3 replication is never presented as independent evidence.
Sign per seed: '+' if the 95% CI of drop_fix_both (orig - fix_both) is entirely > 0, '-' if entirely < 0, '0' if it spans 0;
case sign = the category shared by >= 2 of seeds 42/43/44, else 'mixed' (g4.case_sign). Verdict INFLATED iff sign '+'.
Truth for hard cases = runs_g5/score.json['truth'] (builder reference patches, unchanged). Clean truth = '0'.
Rules hard-correct = 3 x (number of hard cases whose rule sign == truth sign). Rules clean false alarms = 3 x (clean cases with sign '+').
Loop hard-correct and loop clean false alarms are read from runs_g5/score.json (acceptance clauses ii and i).
  d_hard = loop_hard_correct - rules_hard_correct;  d_fa = loop_false_alarms - rules_false_alarms.
PASS (the loop beats the rules) iff d_hard >= 3 AND d_fa <= 0.
RULES BEAT THE LOOP iff d_hard <= -3 AND d_fa >= 0.
Otherwise: TIE if |d_hard| <= 2 and d_fa == 0; else MIXED. A tie is reported as a tie, and MIXED with both numbers.
Reported alongside, NOT part of PASS: the 4 real/textbook cases (civilwar_apparent, civilwar_temporal_clean, esl_selection,
esl_selection_clean) against runs_g6 (3 repeats; the loop was CONTAMINATED there, see EVAL-6), and 4 supplementary corpus
leak cases (leak_group, leak_prescale, leak_proxy, leak_temporal) with no loop run to compare."""


def _sha_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _out(a):
    return Path(a.out) if a.out else ROOT / "runs_rulefix"


def _sel(a):
    names = a.cases.split(",") if a.cases else list(CASES)
    bad = [n for n in names if n not in CASES]
    if bad:
        raise SystemExit(f"unknown case(s) {bad}; known: {list(CASES)}")
    return [n for n in names if (ROOT / CASES[n][0] / "data.csv").exists()] if not a.cases else names


def _views(case_dir):
    return {n: _sha_file(case_dir / n) for n in ("train.py", "data.csv", "excerpt.md")}


def detect_stage(a):
    for n in _sel(a):
        d = rulefix.detect(ROOT / CASES[n][0])
        print(f"{n:26s} fired={ {r: v for r, v in d['fired'].items()} } not_applied={d['not_applied']}")


# ---------------- preregistration ----------------
def prereg_stage(a):
    out = _out(a)
    pm = out / "PREREG.md"
    if pm.exists():
        raise SystemExit(f"{pm} exists: a preregistration is never overwritten")
    out.mkdir(parents=True, exist_ok=True)
    now = time.gmtime()
    utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", now)
    t = calendar.timegm(now)
    slt = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t + 5.5 * 3600))
    et = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t - 5 * 3600))  # EST after the 2026-11-01 DST end
    names = _sel(a)
    dets = {n: rulefix.detect(ROOT / CASES[n][0]) for n in names}
    srcs = {"baselines/rulefix.py": _sha_file(ROOT / "baselines" / "rulefix.py"), "eval/run_rulefix.py": _sha_file(Path(__file__)),
            "runs_g5/score.json": _sha_file(ROOT / "runs_g5" / "score.json"), "runs_g6/score.json": _sha_file(ROOT / "runs_g6" / "score.json")}
    lines = [
        "# EVAL-8 PREREGISTRATION: rule-based leakage-fix baseline (no LLM, $0)", "",
        f"Written {utc} UTC = {slt} SLT / {et} ET, BEFORE any measurement of the rule baseline on any benchmark case. "
        "Rule development used synthetic scratch data in tests only; no benchmark case was executed under the rules before this file existed.", "",
        "## Rule set (frozen)", "", f"spec sha256: `{rulefix.spec_sha256()}`", "", "```json",
        json.dumps(rulefix.spec(), indent=1, sort_keys=True), "```", "",
        "Factorial layout: fix_A = fired rules of {R1, R3, R4, R5}; fix_B = fired rule R2; fix_both = all fired rules. "
        "Rules fire only if their detector fires (label-free), are applied blindly, with no model call. "
        "Precedence if several split rules fire: R4 > R3 > R1.", "",
        "## Frozen sources and read-only inputs (sha256)", ""]
    lines += [f"- `{k}`: `{v}`" for k, v in srcs.items()]
    lines += ["", "## Measurement", "", f"4 configs (orig, fix_A, fix_B, fix_both) x seeds {SEEDS}, n_boot = {N_BOOT}, UNPAIRED bootstrap, "
              "same sandbox (`sandbox/executor.run_factorial`) and statistics (`sandbox/factorial_stats.all_seeds`) as the loop. "
              "Metric = `train.METRIC` (PR-AUC for civilwar_*, accuracy otherwise).", "", "## " + COMPARISON_RULE.split("\n")[0], ""]
    lines += ["```text", COMPARISON_RULE, "```", ""]
    lines += ["## Which rules fire (label-free detection, recorded before measurement)", "",
              "| case | group | rules that fire | detected, not applied |", "|---|---|---|---|"]
    for n in names:
        lines.append(f"| {n} | {CASES[n][1]} | {', '.join(dets[n]['fired']) or 'none'} | {', '.join(dets[n]['not_applied']) or '-'} |")
    lines += ["", "## Frozen case files (sha256 of train.py / data.csv / excerpt.md)", ""]
    for n in names:
        v = _views(ROOT / CASES[n][0])
        lines.append(f"- {n}: " + ", ".join(f"{k} `{h[:16]}`" for k, h in v.items()))
    lines += ["", "## Honest caveats stated before running",
              "- The rules match code idioms of this benchmark; their author had read every train.py. The baseline is optimistic for rules.",
              "- Synthetic columns are hashed (c_xxxxxx), so R4 (time-name regex) can only fire on columns with real names (civil war).",
              "- No hard case has duplicate rows, so R5 is not expected to fire anywhere (checked: `df.duplicated().sum() == 0`).",
              "- 4 hard cases and 4 clean cases are counts, not rates. The x3 replication of a deterministic rule is not independent evidence.", ""]
    body = "\n".join(lines)
    pm.write_text(body, encoding="utf-8")
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    (out / "PREREG.sha256").write_text(h + "  PREREG.md\n", encoding="utf-8")
    with (out / "prereg_log.jsonl").open("a") as f:
        f.write(json.dumps({"kind": "rulefix_prereg", "utc": utc, "sha256": h, "spec_sha256": rulefix.spec_sha256(), "sources": srcs}) + "\n")
    print("PREREG written", pm, h)


def _check_prereg(out):
    pm = out / "PREREG.md"
    if not pm.exists():
        raise SystemExit("no PREREG.md: run the prereg stage first")
    txt = pm.read_text(encoding="utf-8")
    for rel in ("baselines/rulefix.py", "eval/run_rulefix.py"):
        if _sha_file(ROOT / rel) not in txt:
            raise SystemExit(f"{rel} changed after preregistration: refusing to measure")
    if rulefix.spec_sha256() not in txt:
        raise SystemExit("rule spec changed after preregistration: refusing to measure")


# ---------------- measurement ----------------
def run_case(case_dir, seeds=SEEDS, n_boot=N_BOOT, timeout=3000):
    """Measure one case. Returns the record that is saved as <out>/<case>.json."""
    from sandbox import executor, factorial_stats
    case_dir = Path(case_dir)
    b = rulefix.build_configs(case_dir)
    patches = {k: b["configs"][k]["src"] for k in ("fix_A", "fix_B", "fix_both")}
    t0 = time.time()
    ex = executor.run_factorial(case_dir, patches, seeds=seeds, timeout=timeout)
    rec = {"case": case_dir.name, "tool": "rulefix (no LLM)", "seeds": list(seeds), "n_boot": n_boot, "bootstrap": "unpaired",
           "fired": b["det"]["fired"], "not_applied": b["det"]["not_applied"], "split_fn": b["det"]["split_fn"],
           "configs": {k: {"rules_applied": v["rules_applied"], "steps": v["steps"], "notes": v["notes"],
                           "src_sha256": hashlib.sha256(v["src"].encode()).hexdigest()} for k, v in b["configs"].items()},
           "sources": patches, "status": ex["status"], "elapsed_s": round(time.time() - t0, 1)}
    if ex["status"] != "ok":
        rec["stderr"] = ex.get("stderr", "")[-1500:]
        return rec
    rec["stats"] = factorial_stats.all_seeds(ex["result"], n_boot=n_boot)
    rec["metric"] = ex["result"].get("metric", "accuracy")
    return rec


def run_stage(a):
    out = _out(a)
    _check_prereg(out)
    for n in _sel(a):
        p = out / f"{n}.json"
        if p.exists() and not a.force:
            print(n, "exists, skipped")
            continue
        rec = run_case(ROOT / CASES[n][0])
        p.write_text(json.dumps(rec, indent=1), encoding="utf-8")
        import g4
        s = g4.case_sign(rec["stats"]) if rec["status"] == "ok" else ("ERROR", None)
        both = g4.components(rec["stats"])["both"] if rec["status"] == "ok" else None
        print(f"{n:26s} {rec['status']} fired={list(rec['fired'])} sign={s} both={both} {rec['elapsed_s']}s", flush=True)


# ---------------- scoring ----------------
def _row(rec):
    import g4
    if rec["status"] != "ok":
        return {"status": rec["status"], "sign": "ERROR"}
    st = rec["stats"]
    sign, cats = g4.case_sign(st)
    comp = g4.components(st)
    full = {s: st[s]["full"] for s in sorted(st)}
    scale = 100.0 if rec.get("metric", "accuracy") == "accuracy" else 1.0
    unit = "pp" if scale == 100.0 else "PR-AUC"
    return {"status": "ok", "sign": sign, "per_seed": cats, "verdict": "INFLATED" if sign == "+" else "NOT INFLATED", "unit": unit,
            "inflation": round(comp["both"] * scale, 3), "A": round(comp["A"] * scale, 3), "B": round(comp["B"] * scale, 3),
            "I": round(comp["AxB"] * scale, 3),
            "ci_per_seed": {s: [round(x * scale, 3) for x in full[s]["drop_ci"]["fix_both"]] for s in full},
            "n_orig": {s: full[s]["n"]["orig"] for s in full}, "n_fix_both": {s: full[s]["n"]["fix_both"] for s in full},
            "acc_orig": {s: round(full[s]["acc"]["orig"], 4) for s in full}, "acc_fix_both": {s: round(full[s]["acc"]["fix_both"], 4) for s in full},
            "fired": list(rec["fired"]), "not_applied": rec["not_applied"],
            "rules_applied_both": rec["configs"]["fix_both"]["rules_applied"], "steps_changed": rec["configs"]["fix_both"]["steps"]}


def score_stage(a):
    out = _out(a)
    g5 = json.loads((ROOT / "runs_g5" / "score.json").read_text())
    g6 = json.loads((ROOT / "runs_g6" / "score.json").read_text())
    truth = g5["truth"]
    rows = {}
    for n, (_, grp) in CASES.items():
        p = out / f"{n}.json"
        if not p.exists():
            continue
        r = _row(json.loads(p.read_text(encoding="utf-8")))
        r["group"] = grp
        if grp in ("hard", "clean"):
            t = truth[n]["sign"]
            r["truth_sign"], r["truth_both_pp"] = t, truth[n].get("components_pp", {}).get("both")
            r["correct"] = r["sign"] == t
            r["false_alarm"] = grp == "clean" and r["sign"] == "+"
            reps = g5["cases"][n]
            r["loop"] = {k: {"sign": v["loop"]["sign"], "both_pp": v["loop"].get("components_pp", {}).get("both"),
                             "correct": v["loop"]["correct"], "false_alarm": v["loop"]["false_alarm"]} for k, v in reps.items()}
        elif grp in ("real_leaky", "real_clean"):
            reps = g6["cases"][n]
            r["loop"] = {k: {"sign": v["loop"]["sign"], "inflation": v["loop"].get("inflation_mean"),
                             "reproduces": v["loop"].get("reproduces"), "false_alarm": v["loop"].get("false_alarm")} for k, v in reps.items()}
            if grp == "real_leaky":
                pub = PUBLISHED[n]["inflation"]
                r["published_inflation"] = pub
                scale = 100.0 if r["unit"] == "pp" else 1.0
                r["magnitude_ok"] = r["status"] == "ok" and abs(r["inflation"] / scale - pub) <= 0.15
                r["correct"] = r["sign"] == "+"
                r["reproduces"] = r["correct"] and r["magnitude_ok"]
            else:
                r["truth_sign"], r["correct"], r["false_alarm"] = "0", r["sign"] == "0", r["sign"] == "+"
        else:
            r["note"] = "supplementary: no loop run, no preregistered truth beyond 'leaky by construction'"
        rows[n] = r
    hard = [n for n in rows if rows[n]["group"] == "hard"]
    clean = [n for n in rows if rows[n]["group"] == "clean"]
    summary = {}
    if len(hard) == 4 and len(clean) == 4:
        rules_hard = 3 * sum(rows[n]["correct"] for n in hard)
        rules_fa = 3 * sum(rows[n]["false_alarm"] for n in clean)
        loop_hard = int(g5["acceptance"]["ii_hard_sign_correct"].split("/")[0])
        loop_fa = int(g5["acceptance"]["i_clean_false_alarms"].split("/")[0])
        d_hard, d_fa = loop_hard - rules_hard, loop_fa - rules_fa
        if d_hard >= 3 and d_fa <= 0:
            res = "PASS: the loop beats the rules"
        elif d_hard <= -3 and d_fa >= 0:
            res = "FAIL: the rules beat the loop"
        elif abs(d_hard) <= 2 and d_fa == 0:
            res = "TIE"
        else:
            res = "MIXED"
        summary = {"rules_hard_sign_correct_cases": f"{sum(rows[n]['correct'] for n in hard)}/4",
                   "rules_hard_correct_x3": f"{rules_hard}/12", "loop_hard_correct": f"{loop_hard}/12",
                   "rules_clean_false_alarm_cases": f"{sum(rows[n]['false_alarm'] for n in clean)}/4",
                   "rules_false_alarms_x3": f"{rules_fa}/12", "loop_false_alarms": f"{loop_fa}/12",
                   "d_hard": d_hard, "d_fa": d_fa, "result": res}
    obj = {"rules_spec_sha256": rulefix.spec_sha256(), "prereg_sha256_file": (out / "PREREG.sha256").read_text().split()[0]
           if (out / "PREREG.sha256").exists() else None, "summary": summary, "cases": rows}
    (out / "score.json").write_text(json.dumps(obj, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    for n, r in rows.items():
        print(f"{n:26s} {r['group']:10s} fired={r.get('fired')} sign={r['sign']} {r.get('per_seed')} infl={r.get('inflation')}{r.get('unit', '')} "
              f"truth={r.get('truth_sign')} correct={r.get('correct')} FA={r.get('false_alarm')}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["detect", "prereg", "run", "score"])
    ap.add_argument("--out")
    ap.add_argument("--cases")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    {"detect": detect_stage, "prereg": prereg_stage, "run": run_stage, "score": score_stage}[a.stage](a)


if __name__ == "__main__":
    main()
