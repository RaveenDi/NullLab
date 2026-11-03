"""One-zip reproducibility bundle for a finished audit run.

    python -m agent.bundle <case_dir> --out bundle.zip [--run FILE] [--case NAME] [--no-data]

Contents: README.md (honest limits), MANIFEST.md5 (md5sum -c compatible), case/ (train.py, data.csv, excerpt.md), patches/ (fix_A/fix_B/
fix_both sources, fix_both.patch, train.normalized.py), prereg/ (input hashes, the preregistration records and hash found next to the
run), traces/ (run record without sources, plan and event log, the raw planner reply when one is stored), expected.json,
report.md, rerun.py (standalone: needs only python, pandas, numpy, scikit-learn).

No secrets: every text file is scanned for API-key-looking strings and for the value of MODEL_API_KEY in the environment; hits are
replaced by [REDACTED] and counted in the README; if anything key-looking is still found after redaction, the build is refused.
The zip is deterministic (fixed timestamps, sorted entries), so the same inputs give the same bytes. No model call, no network."""
import argparse
import hashlib
import io
import json
import os
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from agent import audit, patch_export, evidence  # noqa: E402

SECRET_PATTERNS = [
    re.compile(r"MODEL_API_KEY\s*[=:]\s*\S+"),
    re.compile(r"MODEL_API_KEY"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"(?i)\b(?:api[_\-]?key|secret|access[_\-]?token|auth[_\-]?token|password)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-./+]{16,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]
ZIP_DATE = (2026, 1, 1, 0, 0, 0)


class BundleError(RuntimeError):
    pass


def _env_secrets():
    v = os.environ.get("MODEL_API_KEY", "")
    return [v] if len(v) >= 8 else []


def scan_secrets(text: str) -> list[str]:
    """-> list of matched fragments (first 12 chars of each, never the full match) for the key-looking patterns / env key value."""
    hits = []
    for p in SECRET_PATTERNS:
        hits += [m.group(0)[:12] + "..." for m in p.finditer(text)]
    hits += ["<MODEL_API_KEY value>" for v in _env_secrets() if v in text]
    return hits


def redact(text: str) -> tuple[str, int]:
    """Replace key-looking strings and env secret values; returns (clean text, number of redactions)."""
    n = 0
    for v in _env_secrets():
        n += text.count(v)
        text = text.replace(v, "[REDACTED]")
    for p in SECRET_PATTERNS:
        text, k = p.subn("[REDACTED]", text)
        n += k
    return text, n


RERUN = '''"""Rerun this bundle's measurement with nothing but python, pandas, numpy and scikit-learn.

    python rerun.py            # recompute claimed vs controlled point estimates for the seeds in expected.json
Compares them with expected.json (what the audit stored). Exit 0 = match within 1e-9, 1 = differ, 2 = could not run.
It does NOT recompute the bootstrap intervals (use `python -m agent.audit ... --remeasure` in the NullLab repo for that) and runs
the code in case/ and patches/ on YOUR machine: read them first. Library versions that differ from the recorded ones can change scores."""
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def score(metric, y, p):
    import numpy as np
    y, p = np.asarray(y), np.asarray(p)
    if metric == "accuracy":
        return float((y == p).mean())
    from sklearn.metrics import average_precision_score, roc_auc_score
    return float({"pr_auc": average_precision_score, "roc_auc": roc_auc_score}[metric](y, p))


def main():
    exp = json.loads((HERE / "expected.json").read_text(encoding="utf-8"))
    os.chdir(HERE / "case")
    sys.path.insert(0, str(HERE / "case"))
    try:
        train = load("train_claim", HERE / "case" / "train.py")
        fix = load("fix_both", HERE / "patches" / "fix_both.py")
        df = train.load("data.csv")
    except Exception as e:  # noqa: BLE001
        print("could not load the case:", repr(e))
        return 2
    metric, bad = exp["metric"], 0
    for s in exp["seeds"]:
        y, p = train.claimed_eval(df, int(s))
        a = score(metric, y, p)
        y, p = fix.controlled_eval(df, int(s))
        b = score(metric, y, p)
        ea, eb = exp["claimed"][s], exp["controlled"][s]
        ok = abs(a - ea) < 1e-9 and abs(b - eb) < 1e-9
        bad += not ok
        print(f"seed {s}: claimed {a:.6f} (stored {ea:.6f})  controlled {b:.6f} (stored {eb:.6f})  {'MATCH' if ok else 'DIFFERS'}")
    print("RESULT:", "all seeds match the stored audit" if not bad else f"{bad} seed(s) differ (library versions? see README)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
'''

README = """# NullLab reproducibility bundle: {case}

Built by `agent/bundle.py` from `{run_file}`. Provenance of the finding: **{provenance}** ({badge}).
Verdict recorded: sign `{sign}`, claimed {claimed}, controlled {controlled} ({metric}); seeds {seeds}.

## Files
- `report.md`: the full audit report for this run (claim, numbers, exact patch, fidelity check, preregistration, what was not tested).
- `case/`: the claim's `train.py`, `data.csv`, `excerpt.md` exactly as audited (sha256 in `prereg/INPUT_HASHES.json`).
- `patches/`: the executed sources (`fix_A.py`, `fix_B.py`, `fix_both.py`), `fix_both.patch` (unified diff with a provenance header) and
  `train.normalized.py` (the base the patch applies to, `ast.unparse` form).
- `prereg/`: input hashes, and the preregistration records / hash that sat next to the run (if any).
- `traces/`: the run record without sources, the plan and event log, and the raw planner reply when stored.
- `expected.json`, `rerun.py`: recompute the point estimates yourself. `python rerun.py` (python, pandas, numpy, scikit-learn needed).
- `MANIFEST.md5`: md5 of every other file (`md5sum -c MANIFEST.md5` from this folder).

## Honest limits
- This reproduces the audit's POINT ESTIMATES on the case folder's code and data. It does not recompute the bootstrap intervals
  (that needs the NullLab repo: `python -m agent.audit ... --remeasure`) and it is not a re-run of the authors' original pipeline.
- Scores depend on library versions; a mismatch may be version drift, not a different finding.
- `rerun.py` executes the code in `case/` and `patches/` on your machine. Read it first.
- The md5 manifest detects accidental change, not tampering: an adversary can rewrite files and the manifest together.
  The preregistration hash is the integrity anchor only to the extent you trust where it was first recorded.
- Model: {model_note}
- Secrets: the bundle was scanned for API-key-looking strings; {redactions} redaction(s) were made. Absence of a match is not proof of absence.
- Data included: {data_note}
"""


def _traces(cand, case_name):
    out = {}
    rec = dict(cand["rec"])
    rec.pop("sources", None)
    out["traces/run_record.json"] = json.dumps(rec, indent=1, sort_keys=True)
    if cand["kind"] == "loop":
        run = cand["run"]
        pl = (run.get("plan") or {}).get(case_name) or {}
        out["traces/plan.json"] = json.dumps(rec.get("final_plan"), indent=1, sort_keys=True)
        out["traces/event_log.json"] = json.dumps(rec.get("log"), indent=1, sort_keys=True)
        if pl.get("raw"):
            out["traces/planner_raw_reply.txt"] = pl["raw"]
    return out


def build_bundle(case_dir: str | Path, out_zip: str | Path, run: str | None = None, case: str | None = None,
                 include_data: bool = True, extra_report: str | None = None, root: str | Path = ROOT) -> dict:
    """Build the zip. Returns {"path", "files", "redactions", "manifest"}."""
    case_dir, case_name, cand = audit.locate(case_dir, case=case, run=run, root=root)
    rec, kind = cand["rec"], cand["kind"]
    try:
        evidence.verify(case_dir, rec)
    except evidence.EvidenceError as e:
        raise BundleError(str(e)) from e
    if not all(k in (rec.get("sources") or {}) for k in ("fix_A", "fix_B", "fix_both")):
        raise BundleError("the run record has no stored patch sources: nothing to bundle")
    F = audit.build_finding(case_dir, case=case_name, run=cand["file"], root=root)
    m = F["meas"]
    files = {}
    for name in ("train.py", "excerpt.md") + (("data.csv",) if include_data else ()):
        files[f"case/{name}"] = (Path(case_dir) / name).read_bytes()
    for c in ("fix_A", "fix_B", "fix_both"):
        files[f"patches/{c}.py"] = rec["sources"][c].encode("utf-8")
    files["patches/train.normalized.py"] = patch_export.normalized_base(case_dir).encode("utf-8")
    try:
        files["patches/fix_both.patch"] = patch_export.build_patch(case_dir, rec, kind, "fix_both", run_name=Path(cand["file"]).name).encode("utf-8")
    except patch_export.PatchError as e:
        files["patches/fix_both.patch"] = f"no patch: {e}\n".encode()
    hashes = {n: v for n, v in rec["evidence"]["inputs"].items() if v is not None}
    files["prereg/INPUT_HASHES.json"] = json.dumps({"sha256": hashes, "patch_sources_sha256": F["sources_sha256"],
                                                    "evidence": rec["evidence"],
                                                    "note": "audit-time input hashes verified before export; compare exported byte hashes separately"}, indent=1, sort_keys=True).encode()
    files["prereg/prereg_records.json"] = json.dumps(F["prereg"], indent=1, sort_keys=True).encode()
    for fn in ("PREREG.sha256", "PREREG.md"):
        p = Path(cand["dir"]) / fn
        if p.exists():
            files[f"prereg/{fn}"] = p.read_bytes()
    for k, v in _traces(cand, case_name).items():
        files[k] = v.encode("utf-8")
    seeds = [str(r["seed"]) for r in m["rows"]]
    files["expected.json"] = json.dumps({"metric": m["metric"], "seeds": seeds, "claimed": {str(r["seed"]): r["claimed"] for r in m["rows"]},
                                         "controlled": {str(r["seed"]): r["controlled"] for r in m["rows"]}}, indent=1, sort_keys=True).encode()
    files["rerun.py"] = RERUN.encode("utf-8")
    report = audit.render_md(F) + (("\n\n---\n\n" + extra_report) if extra_report else "")
    files["report.md"] = report.encode("utf-8")
    mode = str((rec.get("final_plan") or {}).get("mode", ""))
    model_note = ("none: produced by the fixed rule library, no model call." if kind == "rulefix"
                  else f"{mode or 'a model-written plan'}; the measured numbers come from the sandbox, not from the model.")
    # redact text files, then rescan EVERYTHING (binary-safe) and refuse on any remaining hit
    n_red = 0
    for k in list(files):
        try:
            txt = files[k].decode("utf-8")
        except UnicodeDecodeError:
            continue
        new, n = redact(txt)
        if n:
            files[k] = new.encode("utf-8")
            n_red += n
    # Redaction may change code/data. Keep the original audit identity distinct
    # from the bytes actually exported; never promise exact rerun after edits.
    exported = {k: hashlib.sha256(v).hexdigest() for k, v in files.items() if k.startswith(("case/", "patches/"))}
    files["prereg/EXPORTED_HASHES.json"] = json.dumps({"sha256": exported, "redactions": n_red,
        "note": "hashes of exported bytes; redacted artifacts may not reproduce the audited result"}, indent=1, sort_keys=True).encode()
    readme = README.format(case=case_name, run_file=F["run_file"], provenance=F["source"] or "case built by NullLab, no external source",
                           badge=F["provenance"], sign=m["sign"], claimed=round(m["mean_claimed"], 4), controlled=round(m["mean_controlled"], 4),
                           metric=m["metric"], seeds=", ".join(seeds), model_note=model_note, redactions=n_red,
                           data_note="data.csv as audited" if include_data else "NOT included (--no-data): rerun.py cannot run until you add case/data.csv")
    files["README.md"] = readme.encode("utf-8")
    for k, v in files.items():
        try:
            left = scan_secrets(v.decode("utf-8"))
        except UnicodeDecodeError:
            left = scan_secrets(v.decode("latin-1"))
        if left and k != "README.md":
            raise BundleError(f"refusing to build: key-looking string still present in {k}: {left[:3]}")
    manifest = "".join(f"{hashlib.md5(files[k]).hexdigest()}  {k}\n" for k in sorted(files))
    files["MANIFEST.md5"] = manifest.encode("utf-8")
    out = Path(out_zip)
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for k in sorted(files):
            zi = zipfile.ZipInfo(k, ZIP_DATE)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, files[k])
    out.write_bytes(buf.getvalue())
    return {"path": str(out), "files": sorted(files), "redactions": n_red, "manifest": manifest}


def main(argv: list[str] | None = None) -> int:
    """Command line: write a reproducibility bundle zip for a case."""
    ap = argparse.ArgumentParser(prog="python -m agent.bundle", description=__doc__.split("\n")[0])
    ap.add_argument("case_dir")
    ap.add_argument("--out", required=True)
    ap.add_argument("--run")
    ap.add_argument("--case")
    ap.add_argument("--no-data", action="store_true", help="leave data.csv out (licence or size)")
    a = ap.parse_args(argv)
    try:
        r = build_bundle(a.case_dir, a.out, run=a.run, case=a.case, include_data=not a.no_data)
    except (BundleError, SystemExit) as e:
        print(f"bundle: {e}", file=sys.stderr)
        return 2
    print(f"bundle written: {r['path']} ({len(r['files']) + 0} files, {r['redactions']} redactions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
