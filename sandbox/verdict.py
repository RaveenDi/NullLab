"""Verdict logic. 3-seed agreement or INCONCLUSIVE."""
MIN_EFFECT = 0.03  # smallest accuracy drop we call practically meaningful


def seed_call(r):
    if r["ci_lo"] > 0 and r["delta"] >= MIN_EFFECT:
        return "FALSIFIED"           # claimed accuracy significantly above properly controlled accuracy
    if r["ci_lo"] <= 0 <= r["ci_hi"] or abs(r["delta"]) < MIN_EFFECT:
        return "SURVIVED"
    return "INCONCLUSIVE"            # e.g. controlled significantly better than claimed: unexpected


def verdict(seed_results: dict) -> dict:
    calls = {s: seed_call(r) for s, r in seed_results.items()}
    vals = set(calls.values())
    v = vals.pop() if len(vals) == 1 else "INCONCLUSIVE"
    return {"verdict": v, "per_seed": calls, "agree": len(set(calls.values())) == 1}
