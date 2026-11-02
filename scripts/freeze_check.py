"""Verify (or regenerate) the LF-normalised sha256 manifest of every preregistration-frozen file.

    python scripts/freeze_check.py verify    # default; exit 1 on any unacknowledged difference
    python scripts/freeze_check.py write     # (re)compute docs/FROZEN-HASHES.json from the working tree
    python scripts/freeze_check.py list      # print the frozen path list

Hashing: sha256 over file bytes with CRLF -> LF. Paths are repo-relative with forward slashes.
Prereg logs are append-only; they are pinned by their first ``pinned_lines`` lines, not the whole file.
A deliberate post-tag change is recorded in docs/FROZEN-CHANGELOG.json (see docs/FROZEN-FILES.md).
"""

from __future__ import annotations

import hashlib
import itertools
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# real/*/data.csv is gitignored (redistribution terms), so a fresh clone (CI) does not have the four frozen data files.
# With this flag a missing frozen data.csv is skipped instead of reported. Local runs stay strict.
ALLOW_MISSING_DATA = os.environ.get("FREEZE_ALLOW_MISSING_DATA") == "1"
MANIFEST = ROOT / "docs" / "FROZEN-HASHES.json"
CHANGELOG = ROOT / "docs" / "FROZEN-CHANGELOG.json"

CODE = [
    *(
        f"agent/{n}.py"
        for n in (
            "factorial_g9",
            "factorial_ehg",
            "factorial_g8",
            "factorial_g7",
            "factorial_g5",
            "factorial_g6",
            "factorial",
            "transport",
            "smoke",
            "cached_exec",
            "edit_dsl",
            "guard_g9",
            "contract_g9",
            "llm",
            "fidelity",
        )
    ),
    "g4.py",
    *(f"sandbox/{n}.py" for n in ("executor", "run", "run_factorial", "factorial_stats")),
    *(
        f"eval/{n}"
        for n in ("build_g8_cases.py", "build_g7.py", "run_rulefix.py", "regress.py", "g8_truth.json", "g7_truth.json")
    ),
    "baselines/rulefix.py",
]
VIEW_CASES = ("ehg_disguised", "ehg_disguised_clean", "civilwar_disguised", "civilwar_disguised_clean")
VIEWS = [f"real/{c}/{n}" for c in VIEW_CASES for n in ("train.py", "data.csv", "excerpt.md")]
DOCS = [
    "docs/EVAL-9-G8-PREREG.md",
    "docs/EVAL-9-G8-RESULT.md",
    "docs/EVAL-10-CASES.md",
    "docs/EVAL-11-EHG-PREREG.md",
    "docs/EVAL-12-G9-DSL.md",
    "docs/EVAL-12-G9-INSTRUMENT.md",
    "docs/EVAL-13-G9-PREREG.md",
]
TESTS = [
    f"tests/{n}.py"
    for n in ("test_g7", "test_g8", "test_g8_cases", "test_g9_runner", "test_ehg_runner", "test_guard_g9", "test_dsl")
]
LOGS = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.glob("runs_*/prereg_log.jsonl"))
# runs_g9 is a live run that keeps appending; only its freeze records (up to g9_prereg_doc) are pinned.
LIVE_LOG_KINDS = {"runs_g9/prereg_log.jsonl": "g9_prereg_doc"}

G8_FILES = (
    "agent/factorial_g8.py",
    "agent/factorial_g7.py",
    "agent/llm.py",
    "agent/fidelity.py",
    "agent/factorial_g5.py",
    "agent/factorial_g6.py",
    "eval/build_g7.py",
    "eval/g7_truth.json",
    "sandbox/factorial_stats.py",
    "sandbox/run_factorial.py",
    "sandbox/executor.py",
)


def frozen_paths() -> list[str]:
    return [*CODE, *VIEWS, *DOCS, *TESTS]


def lf_bytes(path: Path) -> bytes:
    return path.read_bytes().replace(b"\r\n", b"\n")


def lf_sha(path: Path) -> str:
    return hashlib.sha256(lf_bytes(path)).hexdigest()


def _log_lines(rel: str) -> list[bytes]:
    data = lf_bytes(ROOT / rel)
    return data.split(b"\n")[:-1] if data.endswith(b"\n") else data.split(b"\n") if data else []


def _pinned_count(rel: str) -> int:
    stop = LIVE_LOG_KINDS.get(rel)
    lines = _log_lines(rel)
    if not stop:
        return len(lines)
    for i, ln in enumerate(lines):
        if json.loads(ln).get("kind") == stop:
            return i + 1
    return len(lines)


def log_digest(rel: str, n: int) -> str:
    return hashlib.sha256(b"\n".join(_log_lines(rel)[:n]) + b"\n").hexdigest()


def compute() -> dict:
    files = {p: lf_sha(ROOT / p) for p in frozen_paths()}
    logs = {}
    for rel in LOGS:
        n = _pinned_count(rel)
        logs[rel] = {"pinned_lines": n, "sha256_of_pinned_lines": log_digest(rel, n)}
    return {
        "normalisation": "CRLF->LF before sha256; repo-relative forward-slash paths",
        "files": files,
        "prereg_logs": logs,
    }


def load_changelog() -> list[dict]:
    if not CHANGELOG.exists():
        return []
    return json.loads(CHANGELOG.read_text(encoding="utf-8")).get("changes", [])


def acknowledged(path: str, old: str, new: str) -> bool:
    return any(
        c["path"] == path and c["old_sha256"] == old and c["new_sha256"] == new and c.get("reason")
        for c in load_changelog()
    )


def _acknowledged_old_forms(path: str, got: str):
    """(LF hash, CRLF hash) of the pre-change content when the changelog records the transition to the current content, else None.
    Needed for the G8 combined digest, which was computed over the old bytes (see check_logs)."""
    for c in load_changelog():
        if c["path"] == path and c["new_sha256"] == got and c.get("reason") and c.get("old_sha256_crlf"):
            return c["old_sha256"], c["old_sha256_crlf"]
    return None


def _data_skippable(rel: str) -> bool:
    return ALLOW_MISSING_DATA and rel.startswith("real/") and rel.endswith("/data.csv") and not (ROOT / rel).exists()


def check_manifest() -> list[str]:
    """Manifest vs working tree. Returns a list of problems (empty = clean)."""
    m = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bad = []
    for p, want in m["files"].items():
        f = ROOT / p
        if not f.exists():
            if not _data_skippable(p):
                bad.append(f"missing frozen file: {p}")
        elif (got := lf_sha(f)) != want and not acknowledged(p, want, got):
            bad.append(
                f"changed frozen file: {p} (manifest {want[:12]}, tree {got[:12]}); record it in docs/FROZEN-CHANGELOG.json"
            )
    for rel, rec in m["prereg_logs"].items():
        if not (ROOT / rel).exists():
            bad.append(f"missing prereg log: {rel}")
        elif (
            len(_log_lines(rel)) < rec["pinned_lines"]
            or log_digest(rel, rec["pinned_lines"]) != rec["sha256_of_pinned_lines"]
        ):
            bad.append(f"prereg log changed (not append-only): {rel}")
    for p in frozen_paths():
        if p not in m["files"]:
            bad.append(f"frozen path not in manifest: {p}")
    return bad


def _records(rel: str) -> list[dict]:
    return [json.loads(ln) for ln in _log_lines(rel)]


def check_logs() -> list[str]:
    """Hashes recorded inside the prereg logs vs the working tree (honours the changelog)."""
    bad = []

    def cmp(path: str, logged: str, where: str):
        if not (ROOT / path).exists():
            if not _data_skippable(path):
                bad.append(f"{where}: {path} is missing")
            return
        got = lf_sha(ROOT / path)
        if got != logged and not acknowledged(path, logged, got):
            bad.append(f"{where}: {path} logged {logged[:12]}, tree {got[:12]}")

    for rel in ("runs_ehg/prereg_log.jsonl", "runs_g9/prereg_log.jsonl"):
        recs = _records(rel)
        # a re-freeze appends a new record; the LAST source_hashes record binds, earlier ones are history
        src = [r for r in recs if r["kind"].endswith("_source_hashes")]
        for p, h in src[-1]["payload"].items() if src else ():
            cmp(p, h, f"{rel}:{src[-1]['kind']}")
        for r in recs:
            k = r["kind"]
            if k.endswith("_agent_view_frozen"):
                hit = [
                    c
                    for c in VIEW_CASES
                    if all(
                        _data_skippable(f"real/{c}/{n}")
                        or ((ROOT / "real" / c / n).exists() and lf_sha(ROOT / "real" / c / n) == h)
                        for n, h in r["payload"]["files_lf"].items()
                    )
                ]
                if not hit:
                    bad.append(f"{rel}:{k}: no case folder matches the logged file hashes")
        docs = [r for r in recs if r["kind"].endswith("_prereg_doc")]
        if docs:  # the doc may have been edited before the final freeze: the LAST record binds
            cmp(docs[-1]["payload"]["path"], docs[-1]["payload"]["sha256_lf"], f"{rel}:{docs[-1]['kind']}")
    # G8 logged one combined digest: sha256(json(sorted {path: sha256})) over the G8 file list. It was computed on the
    # Windows working tree (CRLF bytes), so accept the LF form and the CRLF form of the same text.
    g8 = [r for r in _records("runs_g8/prereg_log.jsonl") if r["kind"] == "g8_source_hashes"]
    if g8:
        # each file may have been on disk as LF or CRLF when the digest was taken: try every combination (2^11)
        forms = {
            p: _acknowledged_old_forms(p, lf_sha(ROOT / p))  # a file changed after the G8 run: the digest covers its old bytes
            or (
                hashlib.sha256(lf_bytes(ROOT / p)).hexdigest(),
                hashlib.sha256(lf_bytes(ROOT / p).replace(b"\n", b"\r\n")).hexdigest(),
            )
            for p in G8_FILES
        }
        names = sorted(G8_FILES)
        found = False
        for combo in itertools.product((0, 1), repeat=len(names)):
            per_file = {n: forms[n][c] for n, c in zip(names, combo, strict=True)}
            if hashlib.sha256(json.dumps(per_file, sort_keys=True).encode()).hexdigest() == g8[-1]["sha256"]:
                found = True
                break
        if not found:
            bad.append("runs_g8 g8_source_hashes digest does not match the working tree")
    return bad


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "verify"
    if cmd == "list":
        print("\n".join([*frozen_paths(), *LOGS]))
        return 0
    if cmd == "write":
        MANIFEST.write_text(json.dumps(compute(), indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {MANIFEST.relative_to(ROOT)}: {len(frozen_paths())} files, {len(LOGS)} logs")
        return 0
    global ALLOW_MISSING_DATA
    if "--allow-missing-data" in argv:
        ALLOW_MISSING_DATA = True
    problems = check_manifest() + check_logs()
    for p in problems:
        print("FROZEN VIOLATION:", p)
    print("freeze check:", "FAILED" if problems else f"ok ({len(frozen_paths())} files, {len(LOGS)} logs)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
