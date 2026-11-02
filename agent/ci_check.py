"""CI entry: audit the evaluation code in a repository path and fail the build when the measured inflation is above a threshold.

    python -m agent.ci_check <path> [--threshold 0.05] [--summary $GITHUB_STEP_SUMMARY] [--fresh] [--spark --live]

A "case" is a folder with train.py (defining load, feats, claimed_eval) and data.csv, the NullLab case layout (see docs/PRODUCT-FEATURES.md).
<path> may be one case or a tree; every folder holding both files is audited.

Default mode is RULES ONLY: the fixed rule library plus the local sandbox. It costs $0, calls no model, needs no secret and no network.
Exit codes:  0 = no case exceeds the threshold   1 = at least one case is INFLATED beyond the threshold (95% interval above 0)
             2 = nothing audited / measurement failed / usage error.
A case where no rule fired is reported as NO_RULE_FIRED (not a pass): the rules cannot see look-ahead features, offsetting errors or
label-conditioned imputation. Spark mode (--spark --live) asks the model for those cases; it needs MODEL_API_KEY in the environment, the
repository's spend gate, and is optional and OFF in the shipped workflow.

Threshold units: percentage points for accuracy cases (--threshold 0.05 means 5 pp), absolute metric units for PR-AUC/ROC-AUC."""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from agent import hybrid  # noqa: E402

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".github", "site-packages"}
EXIT_OK, EXIT_INFLATED, EXIT_ERROR = 0, 1, 2


def discover_cases(path):
    p = Path(path)
    if (p / "train.py").exists() and (p / "data.csv").exists():
        return [p]
    found = []
    for d in sorted(p.rglob("train.py")):
        if any(part in SKIP_DIRS or part.startswith(".venv") for part in d.relative_to(p).parts[:-1]):
            continue
        if (d.parent / "data.csv").exists():
            found.append(d.parent)
    return found


def judge(res, threshold):
    """-> (status, message). status in PASS | FAIL | NO_RULE_FIRED | UNRESOLVED | ERROR. FAIL only if the 95% interval is above 0
    (sign '+') AND the mean inflation exceeds the threshold, in the metric's own units (pp for accuracy)."""
    s, v = res.get("summary"), res.get("verdict")
    if v in ("INFLATED", "DISPUTED") and s:
        over = s["inflation"] > threshold * (100.0 if s["unit"] == "pp" else 1.0)
        if v == "INFLATED" and over:
            return "FAIL", (f"{res['case']}: reported {s['metric']} is inflated by {s['inflation']:+} {s['unit']} "
                            f"(claimed {s['claimed']}, controlled {s['controlled']}; 95% interval above 0 in {s['per_seed_sign'].count('+')} of {len(s['per_seed_sign'])} seeds, per seed {''.join(s['per_seed_sign'])}), "
                            f"above the threshold of {threshold * (100.0 if s['unit'] == 'pp' else 1.0):g} {s['unit']}; found by {res['source']}")
        return "PASS", (f"{res['case']}: inflation {s['inflation']:+} {s['unit']} " + ("is within the threshold" if v == "INFLATED" else "was disputed by the referee"))
    if v == "NOT INFLATED":
        return "PASS", f"{res['case']}: no inflation measured ({s['inflation']:+} {s['unit']}, sign {s['sign']})" if s else f"{res['case']}: not inflated"
    if v == "NEEDS_MODEL":
        return "NO_RULE_FIRED", f"{res['case']}: no rule fired. NOT a clean bill of health: rules cannot detect look-ahead features, offsetting errors or label-conditioned imputation"
    if v == "UNRESOLVED":
        return "UNRESOLVED", f"{res['case']}: a rule fired but the measured drop is not clearly positive; a model is needed to resolve it"
    return "ERROR", f"{res['case']}: {v}: {res.get('route')}"


def check_path(path, threshold=0.05, measure=None, fresh=True, spark=False, live=False, detector=None, spark_runner=None):
    """Audit every case under path. Returns {"exit_code", "rows", "messages", "markdown"}. `measure`/`detector`/`spark_runner` are test hooks."""
    cases = discover_cases(path)
    rows, msgs = [], []
    if not cases:
        msg = f"ERROR: no case found under {path} (a case folder holds train.py and data.csv). See docs/PRODUCT-FEATURES.md."
        return {"exit_code": EXIT_ERROR, "rows": [], "messages": [msg], "markdown": render_summary([], threshold, [msg], spark)}
    for c in cases:
        try:
            res = hybrid.run_hybrid(c, live=spark and live, measure=measure, detector=detector, fresh=fresh, allow_recorded=False,
                                    spark_runner=spark_runner if spark else None)
            if not spark and res["verdict"] in ("UNRESOLVED", "NEEDS_MODEL"):
                pass  # rules-only: the model branch was refused offline; reported as such
        except Exception as e:  # noqa: BLE001
            res = {"case": c.name, "verdict": "ERROR", "source": "-", "route": repr(e)[:300], "summary": None, "ledger": {"calls": 0, "est_usd": 0.0}}
        status, msg = judge(res, threshold)
        rows.append({"case": c.name, "path": str(c), "status": status, "verdict": res["verdict"], "source": res["source"], "summary": res.get("summary"),
                     "calls": res["ledger"]["calls"], "est_usd": res["ledger"]["est_usd"], "rules": res.get("rules_fired", []), "message": msg})
        msgs.append(msg)
    code = EXIT_INFLATED if any(r["status"] == "FAIL" for r in rows) else (EXIT_ERROR if any(r["status"] == "ERROR" for r in rows) else EXIT_OK)
    return {"exit_code": code, "rows": rows, "messages": msgs, "markdown": render_summary(rows, threshold, msgs, spark)}


def render_summary(rows, threshold, msgs, spark=False):
    """GitHub job-summary markdown."""
    total_calls = sum(r["calls"] for r in rows)
    total_usd = sum(r["est_usd"] for r in rows)
    L = ["## NullLab audit", "", f"Mode: **{'rules + Spark (optional)' if spark else 'rules only (no model, $0, no secrets)'}**. "
         f"Threshold: {threshold:g} (percentage points for accuracy as a fraction, e.g. 0.05 = 5 pp; absolute units for PR-AUC). "
         f"Model calls: {total_calls}; estimated spend ${total_usd:.2f}.", ""]
    if not rows:
        return "\n".join(L + [msgs[0] if msgs else "Nothing audited.", ""])
    icon = {"PASS": "PASS", "FAIL": "FAIL", "NO_RULE_FIRED": "NOT CHECKED", "UNRESOLVED": "UNRESOLVED", "ERROR": "ERROR"}
    L += ["| case | result | claimed | controlled | inflation | produced by |", "|---|---|---|---|---|---|"]
    for r in rows:
        s = r["summary"]
        L.append(f"| `{r['case']}` | **{icon[r['status']]}** | {s['claimed'] if s else '-'} | {s['controlled'] if s else '-'} | "
                 f"{(format(s['inflation'], '+') + ' ' + s['unit']) if s else '-'} | {r['source']} |")
    L += [""] + [f"- {m}" for m in msgs] + [""]
    if any(r["status"] in ("NO_RULE_FIRED", "UNRESOLVED") for r in rows):
        L += ["> **Limit:** a case marked NOT CHECKED or UNRESOLVED was not cleared. The free rule library recognises a fixed list of patterns "
              "(evaluating on training rows, scaler/selector fit on all rows, repeated groups across the split, unordered time split, duplicate rows). "
              "Look-ahead features, offsetting errors and label-conditioned imputation need the optional Spark mode.", ""]
    L += ["Rows scored are those in the case folder's own code and data; this is not a re-run of your full pipeline.", ""]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m agent.ci_check", description=__doc__.split("\n")[0])
    ap.add_argument("path", nargs="?", default=".")
    ap.add_argument("--threshold", type=float, default=0.05, help="max tolerated inflation (fraction: 0.05 = 5 pp accuracy)")
    ap.add_argument("--summary", help="append the markdown summary to this file (use $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--fresh", action="store_true", default=True, help=argparse.SUPPRESS)
    ap.add_argument("--spark", action="store_true", help="ALSO ask the model for cases the rules cannot judge (needs --live and MODEL_API_KEY)")
    ap.add_argument("--live", action="store_true", help="allow real model calls with --spark")
    a = ap.parse_args(argv)
    if a.spark and not (a.live and os.environ.get("MODEL_API_KEY")):
        print("ci_check: --spark needs --live and MODEL_API_KEY in the environment; refusing (rules-only is the default and needs neither).", file=sys.stderr)
        return EXIT_ERROR
    out = check_path(a.path, a.threshold, spark=a.spark, live=a.live)
    for m in out["messages"]:
        print(("::error::" if "inflated by" in m and os.environ.get("GITHUB_ACTIONS") else "") + m)
    if a.summary:
        with open(a.summary, "a", encoding="utf-8") as f:
            f.write(out["markdown"] + "\n")
    else:
        print(out["markdown"])
    if out["exit_code"] == EXIT_INFLATED:
        print(f"ci_check: FAILED, inflation above the {a.threshold:g} threshold with the 95% interval above 0", file=sys.stderr)
    return out["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
