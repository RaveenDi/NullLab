"""Supported commands: audit CASE [--live --critic --out DIR], historical-report, rulefix.

Audit calls the v2 engine; network inference requires --live. Historical commands
exist only for old experiments. Use python -m agent.intake to prepare a CSV baseline.
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("audit", "historical-report", "rulefix", "prepare"):
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "audit":
        from agent import engine
        return engine.main(rest)
    if cmd == "prepare":
        raise SystemExit("Use python -m agent.intake CSV --target COLUMN --intended-use TEXT --out CASE_DIR")
    if cmd == "historical-report":
        from agent import audit
        return audit.main(rest)
    from eval import run_rulefix
    run_rulefix.main(rest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
