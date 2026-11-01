"""Claim extraction. Reads ONLY the agent view (excerpt.md, train.py). Output claim.json with VERBATIM pointers.
mode="mock": regex stub (labelled MOCK, not a model result).  mode="live": muse-spark-1.3 via agent.llm."""
import re
from pathlib import Path

from . import llm

SYSTEM = ("You extract the central quantitative claim from a paper excerpt and the training script. Return ONLY JSON: "
          '{"claim": str, "metric": str, "value": number, "split_desc": str, '
          '"methods_line": <one line copied from the excerpt>, "methods_line_no": <1-based line number of that line in the excerpt>, '
          '"code_line": <one line copied from train.py>, "code_line_no": <1-based line number of that line in train.py>}. '
          "Copy each line character-for-character (do not rephrase) and give the exact line number where it appears.")

RETRY_SYSTEM = ("You returned a citation whose text or line number does not match the source file. "
                "Return ONLY corrected JSON with the same keys: claim, metric, value, split_desc, "
                "methods_line, methods_line_no, code_line, code_line_no.")


def _lines(text):
    return [l.strip() for l in text.splitlines() if l.strip()]


def _norm(s):
    """Collapse all whitespace runs to single spaces so indentation/double-space drift still matches."""
    return re.sub(r"\s+", " ", s.strip())


def _check_pointer(pointer, line_no, text):
    """True iff the pointer matches the source under normalised whitespace. A reported 1-based
    line number is binding: it must hold the matching line, otherwise the pointer fails (honest
    grounding for the dual-cites gate). Pointers without a number fall back to an any-line match."""
    if not pointer:
        return False, None
    raw = text.splitlines()
    if isinstance(line_no, int):
        if 1 <= line_no <= len(raw) and _norm(raw[line_no - 1]) == _norm(pointer):
            return True, line_no
        return False, None
    norm_lines = [_norm(l) for l in raw if l.strip()]
    if _norm(pointer) in norm_lines:
        return True, norm_lines.index(_norm(pointer)) + 1
    return False, None


def grounded(claim: dict, excerpt: str, code: str) -> dict:
    """Pointer check: each pointer must match its source under normalised whitespace, ideally at the
    reported 1-based line number. Returns precision over the two pointers plus resolved line numbers."""
    ok_m, no_m = _check_pointer(claim.get("methods_line"), claim.get("methods_line_no"), excerpt)
    ok_c, no_c = _check_pointer(claim.get("code_line"), claim.get("code_line_no"), code)
    flags = {"methods_line": ok_m, "code_line": ok_c}
    return {"flags": flags, "precision": sum(flags.values()) / len(flags),
            "line_numbers": {"methods_line_no": no_m, "code_line_no": no_c}}


def _mock(excerpt, code):
    m = re.search(r"achieves (\d+(?:\.\d+)?)%\s+accuracy", excerpt)
    value = float(m.group(1)) / 100 if m else None
    raw_ex = excerpt.splitlines()
    raw_co = code.splitlines()
    claim_line = next((l for l in _lines(excerpt) if "achieves" in l), "")
    methods = next((l for l in _lines(excerpt) if re.search(r"divided|held out|split", l)), "")
    # code pointer: the first line that creates the train/test partition input from transformed data
    cands = [l for l in _lines(code) if re.search(r"augment\(df, seed\)|transform\(|split_idx\(", l) and not l.startswith("def ")]
    code_line = cands[0] if cands else ""
    return {"claim": claim_line, "metric": "accuracy", "value": value, "split_desc": methods,
            "methods_line": methods, "methods_line_no": next((i + 1 for i, l in enumerate(raw_ex) if l.strip() == methods), None),
            "code_line": code_line, "code_line_no": next((i + 1 for i, l in enumerate(raw_co) if l.strip() == code_line), None)}


def _live_with_retry(excerpt, code):
    """Live extraction with one correction retry when a pointer fails the normalised-whitespace check."""
    claim = llm.parse_json(llm.live_complete(SYSTEM, f"EXCERPT:\n{excerpt}\n\nTRAIN.PY:\n{code}"))
    if grounded(claim, excerpt, code)["precision"] < 1.0:
        hint = (f"Your citations did not verify: {grounded(claim, excerpt, code)['flags']}. "
                f"EXCERPT:\n{excerpt}\n\nTRAIN.PY:\n{code}")
        claim = llm.parse_json(llm.live_complete(RETRY_SYSTEM, hint, est_usd=0.02, max_tokens=4000))
    return claim


def extract_claim(case_dir, mode="mock"):
    case_dir = Path(case_dir)
    excerpt = (case_dir / "excerpt.md").read_text(encoding="utf-8")
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    if mode == "live":
        claim = _live_with_retry(excerpt, code)
    else:
        claim = _mock(excerpt, code)
    g = grounded(claim, excerpt, code)
    claim["mode"] = "LIVE muse-spark-1.3" if mode == "live" else "MOCK (stub, not a model result)"
    claim["grounding"] = g
    # back-fill verified line numbers so the report can cite them
    for k in ("methods_line_no", "code_line_no"):
        claim.setdefault(k, g["line_numbers"][k])
    return claim


def memorization_probe(case_dir, mode="mock"):
    """Asks the model to name the source repo of the excerpt; if it can, the hero must be replaced. Mock: UNVERIFIED."""
    if mode != "live":
        return {"status": "UNVERIFIED", "reason": "mock mode; requires a live call"}
    excerpt = (Path(case_dir) / "excerpt.md").read_text(encoding="utf-8")
    ans = llm.live_complete("Answer in one short line.", "If you recognise the dataset or repository this excerpt comes from, "
                            "name it; otherwise say UNKNOWN.\n\n" + excerpt, est_usd=0.01, max_tokens=800)
    return {"status": "pass" if "UNKNOWN" in ans.upper() else "FAIL_named_source", "answer": ans[:200]}
