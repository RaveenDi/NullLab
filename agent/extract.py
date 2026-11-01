"""Claim extraction. Reads ONLY the agent view (excerpt.md, train.py). Output claim.json with VERBATIM pointers.
mode="mock": regex stub (labelled MOCK, not a model result).  mode="live": muse-spark-1.3 via agent.llm."""
import re
from pathlib import Path

from . import llm

SYSTEM = ("You extract the central quantitative claim from a paper excerpt and the training script. Return ONLY JSON: "
          '{"claim": str, "metric": str, "value": number, "split_desc": str, '
          '"methods_line": <one line copied VERBATIM from excerpt>, "code_line": <one line copied VERBATIM from train.py>}')


def _lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


def grounded(claim: dict, excerpt: str, code: str) -> dict:
    """Pointer check: each pointer must appear verbatim in its source. Returns precision over the pointers."""
    ex = {l for l in _lines(excerpt)}
    co = {l for l in _lines(code)}
    flags = {"methods_line": claim.get("methods_line") in ex, "code_line": claim.get("code_line") in co}
    return {"flags": flags, "precision": sum(flags.values()) / len(flags)}


def _mock(excerpt, code):
    m = re.search(r"achieves (\d+(?:\.\d+)?)%\s+accuracy", excerpt)
    value = float(m.group(1)) / 100 if m else None
    claim_line = next((l for l in _lines(excerpt) if "achieves" in l), "")
    methods = next((l for l in _lines(excerpt) if re.search(r"divided|held out|split", l)), "")
    # code pointer: the first line that creates the train/test partition input from transformed data
    cands = [l for l in _lines(code) if re.search(r"augment\(df, seed\)|transform\(|split_idx\(", l) and not l.startswith("def ")]
    return {"claim": claim_line, "metric": "accuracy", "value": value, "split_desc": methods,
            "methods_line": methods, "code_line": cands[0] if cands else ""}


def extract_claim(case_dir, mode="mock"):
    case_dir = Path(case_dir)
    excerpt = (case_dir / "excerpt.md").read_text(encoding="utf-8")
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    if mode == "live":
        claim = llm.parse_json(llm.live_complete(SYSTEM, f"EXCERPT:\n{excerpt}\n\nTRAIN.PY:\n{code}"))
    else:
        claim = _mock(excerpt, code)
    g = grounded(claim, excerpt, code)
    claim["mode"] = "LIVE muse-spark-1.3" if mode == "live" else "MOCK (stub, not a model result)"
    claim["grounding"] = g
    return claim


def memorization_probe(case_dir, mode="mock"):
    """Asks the model to name the source repo of the excerpt; if it can, the hero must be replaced. Mock: UNVERIFIED."""
    if mode != "live":
        return {"status": "UNVERIFIED", "reason": "mock mode; requires a live call"}
    excerpt = (Path(case_dir) / "excerpt.md").read_text(encoding="utf-8")
    ans = llm.live_complete("Answer in one short line.", "If you recognise the dataset or repository this excerpt comes from, "
                            "name it; otherwise say UNKNOWN.\n\n" + excerpt, est_usd=0.01, max_tokens=800)
    return {"status": "pass" if "UNKNOWN" in ans.upper() else "FAIL_named_source", "answer": ans[:200]}
