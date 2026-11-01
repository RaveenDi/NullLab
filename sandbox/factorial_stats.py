"""Host-side statistics for the 2x2 factorial (computed OUTSIDE the sandbox from raw y/p vectors).
UNPAIRED bootstrap: the four configs use different train/test partitions (row split vs group split) and different
test-set sizes, so each config's correctness vector is resampled independently in every replicate. Never call it paired.
drop_X = acc(orig) - acc(X);  interaction I = drop_both - (drop_A + drop_B)
                                            = (orig - fixBoth) - [(orig - fixA) + (orig - fixB)]."""
import numpy as np

CONFIGS = ("orig", "fix_A", "fix_B", "fix_both")


def _correct(d):
    return (np.asarray(d["y"]) == np.asarray(d["p"])).astype(float)


def _ci(x):
    lo, hi = np.percentile(x, [2.5, 97.5])
    return float(lo), float(hi)


def _score_metric(name):
    from sklearn.metrics import average_precision_score, roc_auc_score
    return {"pr_auc": average_precision_score, "roc_auc": roc_auc_score}[name]


def score_factorial_stats(seed_res, metric, n_boot=1000, seed=0, same_n=None):
    """G6: same estimand as factorial_stats, for a score metric (PR-AUC = average precision, or ROC-AUC) computed
    from (y_true, y_score). UNPAIRED bootstrap: each config's (y, score) rows are resampled independently; a replicate
    with a single class in some config is dropped (counted in 'boot_dropped')."""
    f = _score_metric(metric)
    rng = np.random.default_rng(seed)
    ys = {k: np.asarray(seed_res[k]["y"]) for k in CONFIGS}
    ps = {k: np.asarray(seed_res[k]["p"], dtype=float) for k in CONFIGS}
    if same_n:
        for k in CONFIGS:
            i = rng.choice(len(ys[k]), same_n, replace=False)
            ys[k], ps[k] = ys[k][i], ps[k][i]
    acc = {k: float(f(ys[k], ps[k])) for k in CONFIGS}
    boot = {k: [] for k in CONFIGS}
    dropped = 0
    for b in range(n_boot):
        rep = {}
        for k in CONFIGS:
            i = rng.integers(0, len(ys[k]), len(ys[k]))
            if ys[k][i].min() == ys[k][i].max():
                rep = None
                break
            rep[k] = f(ys[k][i], ps[k][i])
        if rep is None:
            dropped += 1
            continue
        for k in CONFIGS:
            boot[k].append(rep[k])
    boot = {k: np.asarray(v) for k, v in boot.items()}
    drops = {k: boot["orig"] - boot[k] for k in ("fix_A", "fix_B", "fix_both")}
    inter = drops["fix_both"] - (drops["fix_A"] + drops["fix_B"])
    out = {"metric": metric, "acc": acc, "n": {k: int(len(v)) for k, v in ys.items()}, "drop": {}, "drop_ci": {},
           "boot_dropped": dropped}
    for k in drops:
        out["drop"][k] = acc["orig"] - acc[k]
        out["drop_ci"][k] = _ci(drops[k])
    out["I"] = out["drop"]["fix_both"] - (out["drop"]["fix_A"] + out["drop"]["fix_B"])
    out["I_ci"] = _ci(inter)
    out["I_excludes_0"] = bool(out["I_ci"][0] > 0 or out["I_ci"][1] < 0)
    return out


def factorial_stats(seed_res, n_boot=1000, seed=0, same_n=None):
    """seed_res = {"orig": {"y","p"}, "fix_A": ..., "fix_B": ..., "fix_both": ...}.
    same_n: if given, each config's vector is first subsampled WITHOUT replacement to this size (sensitivity check)."""
    rng = np.random.default_rng(seed)
    c = {k: _correct(seed_res[k]) for k in CONFIGS}
    if same_n:
        c = {k: v[rng.choice(len(v), same_n, replace=False)] for k, v in c.items()}
    acc = {k: float(v.mean()) for k, v in c.items()}
    boot = {k: np.empty(n_boot) for k in CONFIGS}
    for b in range(n_boot):
        for k, v in c.items():
            boot[k][b] = v[rng.integers(0, len(v), len(v))].mean()
    drops = {k: boot["orig"] - boot[k] for k in ("fix_A", "fix_B", "fix_both")}
    inter = drops["fix_both"] - (drops["fix_A"] + drops["fix_B"])
    out = {"acc": acc, "n": {k: int(len(v)) for k, v in c.items()}, "drop": {}, "drop_ci": {}}
    for k in drops:
        out["drop"][k] = acc["orig"] - acc[k]
        out["drop_ci"][k] = _ci(drops[k])
    out["I"] = out["drop"]["fix_both"] - (out["drop"]["fix_A"] + out["drop"]["fix_B"])
    out["I_ci"] = _ci(inter)
    out["I_excludes_0"] = bool(out["I_ci"][0] > 0 or out["I_ci"][1] < 0)
    return out


def all_seeds(result, n_boot=1000):
    """Per-seed full-n stats plus the same-n subsample sensitivity check (min test n across configs)."""
    rows = {}
    metric = result.get("metric", "accuracy")
    for s, res in result["seeds"].items():
        n_min = min(len(res[k]["y"]) for k in CONFIGS)
        if metric == "accuracy":
            rows[s] = {"full": factorial_stats(res, n_boot, int(s)),
                       "same_n": factorial_stats(res, n_boot, int(s) + 7, same_n=n_min)}
        else:  # G6 score metric; ROC-AUC reported alongside PR-AUC
            rows[s] = {"full": score_factorial_stats(res, metric, n_boot, int(s)),
                       "roc_auc": score_factorial_stats(res, "roc_auc", n_boot, int(s)) if metric != "roc_auc" else None}
    return rows
