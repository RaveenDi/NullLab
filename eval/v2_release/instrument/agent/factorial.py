"""BRIEF-4 loop planner: muse-spark-1.3 reads ONLY the agent view (excerpt.md, train.py, data head), names the two
suspect evaluation steps A and B, writes the three factorial patches (fix_A, fix_B, fix_both) and commits its
predicted accuracy drop per config BEFORE anything runs. The sandbox then measures the drops and the interaction."""
import hashlib
import json
from pathlib import Path

from . import llm

SYSTEM = (
    "You are a scientific adversary planning a 2x2 factorial falsification experiment on a machine-learning claim. "
    "Read the claim excerpt, the training script and the data head. Identify the TWO evaluation steps (call them A and B) "
    "most likely to make the reported accuracy higher than the accuracy the claim's intended use would see. "
    "Write three self-contained Python modules, each defining controlled_eval(df, seed) -> (y_true, y_pred) "
    "(you may `import train` and reuse its functions and constants; df is train.load('data.csv')): "
    "fix_A corrects ONLY step A and keeps step B exactly as in the original; fix_B corrects ONLY step B and keeps step A; "
    "fix_both corrects both. Use only numpy, pandas and scikit-learn; no file or network access. "
    "Before anything runs, commit predictions: the accuracy drop versus the original, in percentage points "
    "(positive = accuracy falls), for each of the three configs, and rank the culprits of the inflation among "
    "'A' (A alone carries most of it), 'B' (B alone carries most of it), 'AxB' (only the combination: fixing either alone "
    "leaves most of the inflation). Return ONLY JSON: "
    '{"A": str, "A_code_line": <one line copied verbatim from train.py>, "B": str, "B_code_line": <one line copied verbatim>, '
    '"patches": {"fix_A": str, "fix_B": str, "fix_both": str}, '
    '"predicted_drop_pp": {"fix_A": number, "fix_B": number, "fix_both": number}, '
    '"culprit_ranking": ["A"|"B"|"AxB", ...], "reason": str}')


MAX_HEAD_LINE = 10000  # G6: very wide data (ESL case, 5001 columns) is clipped; every earlier case is < 8000 chars, so unchanged


def _clip(line):
    if len(line) <= MAX_HEAD_LINE:
        return line
    cells = line.split(",")
    keep, n = [], 0
    for c in cells[:-1]:
        if n + len(c) > 600:
            break
        keep.append(c)
        n += len(c) + 1
    return ",".join(keep) + f",... [{len(cells) - len(keep) - 1} more columns omitted] ...," + cells[-1]


def agent_view(case_dir):
    case_dir = Path(case_dir)
    excerpt = (case_dir / "excerpt.md").read_text(encoding="utf-8")
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    head = "\n".join(_clip(x) for x in (case_dir / "data.csv").read_text(encoding="utf-8").splitlines()[:6])
    return f"EXCERPT:\n{excerpt}\n\nTRAIN.PY:\n{code}\nDATA HEAD:\n{head}"


def plan(case_dir, mode="live"):
    if mode != "live":
        raise ValueError("the factorial planner has no mock: a stub cannot stand in for the model's predictions")
    raw = llm.live_complete(SYSTEM, agent_view(case_dir), est_usd=0.10, tag="factorial_planner")
    p = llm.parse_json(raw)
    p["mode"] = "LIVE muse-spark-1.3"
    p["prereg_sha256"] = hashlib.sha256(json.dumps({k: p.get(k) for k in ("patches", "predicted_drop_pp", "culprit_ranking")},
                                                   sort_keys=True).encode()).hexdigest()
    return p, raw
