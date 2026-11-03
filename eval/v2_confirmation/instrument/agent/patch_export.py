"""Export the stored fix of a finished run as a unified .patch file, with the controlled score, seeds, n and provenance in the header.

    python -m agent.patch_export <case_dir> [--run FILE] [--case NAME] [--config fix_both|fix_A|fix_B] --out fix.patch

IMPORTANT (honest limit): the diff is taken between the ast.unparse-NORMALISED train.py and the normalised patched source, because the
sandbox executed the normalised form (comments and layout of the original are not preserved). The patch therefore applies to
`train.normalized.py`, which `normalized_base()` / `--base-out` write. It will not apply cleanly to a hand-formatted train.py.
The free-text header before the first `---` line is ignored by `patch` and `git apply`.
No model call, no network."""
import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from agent import audit, evidence  # noqa: E402


class PatchError(RuntimeError):
    pass


def normalized_base(case_dir: str | Path) -> str:
    """The text the patch applies to: ast.unparse(train.py) plus a final newline."""
    return audit._norm_src((Path(case_dir) / "train.py").read_text(encoding="utf-8")) + "\n"


def provenance_of(kind: str, rec: dict, override: str | None = None) -> str:
    """Where the patch came from (rule library or recorded model plan)."""
    if override:
        return override
    if kind == "rulefix":
        return "rules (no model): fixed rule library baselines/rulefix.py, rules applied " + (", ".join(rec["configs"]["fix_both"]["rules_applied"]) or "none")
    return "Spark: " + str((rec.get("final_plan") or {}).get("mode", "model-written plan"))


def build_patch(case_dir: str | Path, rec: dict, kind: str, cfg: str = "fix_both", provenance: str | None = None,
                run_name: str | None = None) -> str:
    """-> patch text (header + unified diff). Raises PatchError when the config changed nothing."""
    try:
        evidence.verify(case_dir, rec)
    except evidence.EvidenceError as e:
        raise PatchError(str(e)) from e
    if cfg not in (rec.get("sources") or {}):
        raise PatchError(f"record has no source for {cfg}")
    diff = audit.patch_diff(case_dir, rec, cfg)
    if not diff.strip():
        raise PatchError(f"{cfg} is identical to the claim's train.py: nothing to export (no fix was applied)")
    diff = re.sub(r"^--- .*$", "--- a/train.py", diff, count=1, flags=re.M)
    diff = re.sub(r"^\+\+\+ .*$", "+++ b/train.py", diff, count=1, flags=re.M)
    m = audit.measurement(rec)
    unit_pp = m["metric"] == "accuracy"
    k = 100.0 if unit_pp else 1.0
    u = "pp" if unit_pp else m["metric"]
    key = {"fix_both": "fix_both", "fix_A": "fix_A", "fix_B": "fix_B"}[cfg]
    rows = m["rows"]
    ctrl = [r["controlled"] if cfg == "fix_both" else rec["stats"][str(r["seed"])]["full"]["acc"][key] for r in rows]
    drops = [r["drop"] if cfg == "fix_both" else rec["stats"][str(r["seed"])]["full"]["drop"][key] for r in rows]
    cis = [r["ci"] if cfg == "fix_both" else rec["stats"][str(r["seed"])]["full"]["drop_ci"][key] for r in rows]
    base = normalized_base(case_dir)
    hdr = [
        "NullLab patch export",
        f"case:            {Path(case_dir).name}" + (f" (run {run_name})" if run_name else ""),
        f"fix:             {cfg}",
        f"provenance:      {provenance_of(kind, rec, provenance)}",
        f"metric:          {m['metric']}",
        f"claimed score:   {m['mean_claimed']:.4f} (mean over seeds)",
        f"controlled score: {sum(ctrl) / len(ctrl):.4f} (mean over seeds, this fix applied)",
        f"inflation:       {sum(drops) / len(drops) * k:+.3f} {u} (claimed minus controlled; verdict sign '{m['sign']}', per seed {m['per_seed_sign']})",
        "seeds:           " + ", ".join(str(r["seed"]) for r in rows),
        "n scored rows:   " + ", ".join(f"{r['seed']}: {r['n_controlled']}" for r in rows),
        "95% interval of the drop per seed (unpaired bootstrap over test rows): "
        + "; ".join(f"{r['seed']}: [{c[0] * k:+.3f}, {c[1] * k:+.3f}] {u}" for r, c in zip(rows, cis)),
        f"applies to:      train.py normalised with ast.unparse (sha256 {hashlib.sha256(base.encode()).hexdigest()[:16]}); "
        "use `python -m agent.patch_export ... --base-out train.normalized.py`",
        "limits:          measured on the case folder's code and data only; one fix, other leakage types not examined; "
        "the patch is a proposed control, not a proof the authors' original pipeline is wrong.",
        "",
    ]
    return "\n".join(hdr) + "\n" + diff + "\n"


def apply_unified(base_text: str, patch_text: str) -> str:
    """Minimal unified-diff applier (hunks only; ignores the free-text header). Raises PatchError if a hunk does not match."""
    lines = patch_text.splitlines()
    i = next((j for j, ln in enumerate(lines) if ln.startswith("--- ")), None)
    if i is None:
        raise PatchError("no unified diff found")
    src = base_text.splitlines()
    out, pos = [], 0
    j = i + 2
    while j < len(lines):
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", lines[j])
        if not m:
            j += 1
            continue
        start = int(m.group(1)) - 1 if int(m.group(2) or 1) else int(m.group(1))
        out += src[pos:start]
        pos = start
        j += 1
        while j < len(lines) and not lines[j].startswith("@@"):
            ln = lines[j]
            if ln.startswith(" "):
                if pos >= len(src) or src[pos] != ln[1:]:
                    raise PatchError(f"context mismatch at base line {pos + 1}")
                out.append(src[pos])
                pos += 1
            elif ln.startswith("-"):
                if pos >= len(src) or src[pos] != ln[1:]:
                    raise PatchError(f"removal mismatch at base line {pos + 1}")
                pos += 1
            elif ln.startswith("+"):
                out.append(ln[1:])
            elif ln.startswith("\\"):
                pass
            elif ln == "":  # a blank context line whose trailing space was stripped by an editor
                if pos < len(src) and src[pos] == "":
                    out.append("")
                    pos += 1
            j += 1
    out += src[pos:]
    return "\n".join(out) + "\n"


def export_patch(case_dir: str | Path, out_path: str | Path, run: str | None = None, case: str | None = None,
                 cfg: str = "fix_both", provenance: str | None = None, rec: dict | None = None, kind: str | None = None) -> str:
    """Locate the stored run (or take rec/kind directly), write the patch, return its text."""
    case_dir = Path(case_dir)
    run_name = None
    if rec is None:
        case_dir, case_name, cand = audit.locate(case_dir, case=case, run=run)
        rec, kind, run_name = cand["rec"], cand["kind"], Path(cand["file"]).name
    text = build_patch(case_dir, rec, kind, cfg, provenance, run_name)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    return text


def main(argv: list[str] | None = None) -> int:
    """Command line: export the verified fix as a unified diff."""
    ap = argparse.ArgumentParser(prog="python -m agent.patch_export", description=__doc__.split("\n")[0])
    ap.add_argument("case_dir")
    ap.add_argument("--run", help="run file (rK.json or runs_rulefix/<case>.json)")
    ap.add_argument("--case")
    ap.add_argument("--config", default="fix_both", choices=["fix_both", "fix_A", "fix_B"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--base-out", help="also write the normalised base the patch applies to")
    a = ap.parse_args(argv)
    try:
        export_patch(a.case_dir, a.out, run=a.run, case=a.case, cfg=a.config)
    except PatchError as e:
        print(f"patch_export: {e}", file=sys.stderr)
        return 2
    if a.base_out:
        Path(a.base_out).write_text(normalized_base(a.case_dir), encoding="utf-8", newline="\n")
    print(f"patch written: {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
