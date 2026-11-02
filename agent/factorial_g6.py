"""G6 loop planner: the G5 planner (agent/factorial_g5.py, unchanged) plus ONE added paragraph describing the G6
justification rules of the guard (agent/fidelity.check_justification). Design change made before any G6 live call
(docs/EVAL-6.md section 3), not tuning on results. The metric of a case is whatever train.py's METRIC says
(accuracy when absent); predicted drops are in points of that metric x100."""
from . import factorial_g5, llm

SYSTEM = factorial_g5.SYSTEM + (
    " G6 guard rules (also enforced): a 'feature' fix that names a data column must cite, in A_code_line / B_code_line "
    "(or an optional \"evidence\" field inside that edit), a line copied verbatim from train.py or the excerpt that "
    "mentions that column and shows why it should not be an input; a 'split' fix may hold rows out by order or time "
    "(sorting, shuffle=False, positional slices, comparisons on a time column) only if the excerpt states a temporal "
    "intended use. If train.py sets METRIC, the drops are in points (x100) of that metric instead of accuracy.")


def plan(case_dir, repeat_id):
    raw = llm.live_complete(SYSTEM, factorial_g5.user_msg(case_dir, repeat_id), est_usd=0.10, tag="g6_planner")
    p = llm.parse_json(raw)
    p["mode"] = "LIVE muse-spark-1.3"
    p["prereg_sha256"] = factorial_g5.prereg_hash(p)
    return p, raw


def retry(case_dir, repeat_id, prev, problems):
    import json
    msg = (factorial_g5.user_msg(case_dir, repeat_id) + "\n\nYOUR PREVIOUS JSON:\n" +
           json.dumps({k: prev.get(k) for k in ("A", "A_code_line", "B", "B_code_line", "edits", "predicted_drop_pp",
                                                "culprit_ranking", "reason")}) +
           "\n\nIt was REJECTED:\n- " + "\n- ".join(problems) +
           "\nReturn the corrected complete JSON with the same schema. Change only what the rejection requires.")
    raw = llm.live_complete(SYSTEM, msg, est_usd=0.10, tag="g6_planner_retry")
    p = llm.parse_json(raw)
    p["mode"] = "LIVE muse-spark-1.3 (retry)"
    p["prereg_sha256"] = factorial_g5.prereg_hash(p)
    return p, raw
