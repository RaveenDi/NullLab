"""B3: single-prompt muse-spark-1.3 baseline. ONE live call, NO experiment execution.
The model reads the same blind agent view (excerpt, train.py, data head) and answers leak/no-leak directly.
The ablation question: does the plan->execute->verify loop beat this one-shot judgement
(accuracy on leaky cases and, especially, fewer false alarms on clean controls)?
mode="mock": NOT RUN (a stub cannot stand in for a model judgement)."""
from pathlib import Path

from agent import llm

SYSTEM = ("You are reviewing a machine-learning claim for evaluation flaws. Given the paper excerpt and the "
          "training script, decide whether the reported accuracy is inflated by a methodological flaw "
          "(data leakage, confounding, or distribution shift between the claimed evaluation and real use). "
          "Do NOT run any code; judge from reading only. Return ONLY JSON: "
          '{"leak": true/false, "confidence": <0-1>, "reason": <one sentence naming the mechanism or why the protocol looks sound>}.')


def b3_single_prompt(case_dir, mode="mock"):
    """Returns {"flagged": bool|None, ...}. flagged=None in mock mode (never a model result)."""
    case_dir = Path(case_dir)
    if mode != "live":
        return {"baseline": "B3 single-prompt muse-spark-1.3 (no execution)",
                "status": "NOT RUN (mock mode; single-prompt judgement needs --live)", "flagged": None}
    excerpt = (case_dir / "excerpt.md").read_text(encoding="utf-8")
    code = (case_dir / "train.py").read_text(encoding="utf-8")
    head = "\n".join((case_dir / "data.csv").read_text(encoding="utf-8").splitlines()[:4])
    ans = llm.parse_json(llm.live_complete(SYSTEM, f"EXCERPT:\n{excerpt}\n\nTRAIN.PY:\n{code}\nDATA HEAD:\n{head}",
                                           est_usd=0.03, max_tokens=2000))
    return {"baseline": "B3 single-prompt muse-spark-1.3 (no execution)", "status": "LIVE muse-spark-1.3",
            "flagged": bool(ans.get("leak")), "confidence": ans.get("confidence"), "reason": str(ans.get("reason", ""))[:300]}


FACTORIAL_SYSTEM = (
    "You are reviewing a machine-learning claim for evaluation flaws. Do NOT run any code; judge from reading only. "
    "Given the paper excerpt, the training script and the data head, name up to two flaws (A and B) that could make the "
    "reported accuracy higher than the claim's intended use would see. Predict the accuracy drop in percentage points "
    "(positive = accuracy falls) if ONLY A were fixed, if ONLY B were fixed, and if BOTH were fixed. Rank the culprits of the "
    "inflation among 'A' (A alone carries most of it), 'B' (B alone carries most of it), 'AxB' (only the combination: fixing "
    "either alone leaves most of the inflation). Return ONLY JSON: "
    '{"leak": true/false, "A": str, "B": str, "predicted_drop_pp": {"fix_A": number, "fix_B": number, "fix_both": number}, '
    '"culprit_ranking": ["A"|"B"|"AxB", ...], "confidence": <0-1>, "reason": <one sentence>}.')


def b3_factorial(case_dir):
    """B3 for BRIEF-4: ONE live call, no execution; commits culprit ranking + point drops (preregistered by the caller)."""
    from agent.factorial import agent_view
    raw = llm.live_complete(FACTORIAL_SYSTEM, agent_view(case_dir), est_usd=0.08, tag="b3_factorial")
    ans = llm.parse_json(raw)
    ans["status"] = "LIVE muse-spark-1.3 (single prompt, no execution)"
    return ans, raw
