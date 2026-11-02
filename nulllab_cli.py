"""Thin entry point. No API call is made by either subcommand.

  python nulllab_cli.py audit <case_dir_or_run_dir> --report out.html|out.md [--case N] [--repeat K] [--run FILE] [--remeasure]
  python nulllab_cli.py rulefix detect|prereg|run|score [--out DIR] [--cases a,b]

The same audit is available as `python -m agent.audit ...`."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("audit", "rulefix"):
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "audit":
        from agent import audit
        return audit.main(rest)
    from eval import run_rulefix
    run_rulefix.main(rest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
