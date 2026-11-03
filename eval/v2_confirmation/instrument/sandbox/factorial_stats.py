"""Host-side statistics for the 2x2 factorial (computed OUTSIDE the sandbox from raw y/p vectors).
UNPAIRED bootstrap: the four configs use different train/test partitions (row split vs group split) and different
test-set sizes, so each config's correctness vector is resampled independently in every replicate. Never call it paired.
drop_X = acc(orig) - acc(X);  interaction I = drop_both - (drop_A + drop_B)
                                            = (orig - fixBoth) - [(orig - fixA) + (orig - fixB)]."""
import numpy as np

CONFIGS = ("orig", "fix_A", "fix_B", "fix_both")


def validate_vectors(d, metric="accuracy"):
    """Validate worker output before NumPy can broadcast or metrics coerce it."""
    if metric not in ("accuracy", "pr_auc", "roc_auc"):
        raise ValueError(f"unsupported metric: {metric}")
    if not isinstance(d, dict) or not {"y", "p"} <= set(d):
        raise ValueError("prediction record requires y and p")
    try:
        y, p = np.asarray(d["y"], dtype=float), np.asarray(d["p"], dtype=float)
    except (TypeError, ValueError) as e:
        raise ValueError("labels and predictions must be numeric vectors") from e
    if y.ndim != 1 or p.ndim != 1 or not len(y) or y.shape != p.shape:
        raise ValueError("labels and predictions must be nonempty equal-length one-dimensional vectors")
    if not np.isfinite(y).all() or not np.isfinite(p).all():
        raise ValueError("labels and predictions must be finite")
    if not np.equal(y, np.floor(y)).all():
        raise ValueError("classification labels must be integer class identifiers")
    if metric == "accuracy" and not np.equal(p, np.floor(p)).all():
        raise ValueError("accuracy requires class predictions, not continuous scores")
    if metric != "accuracy" and set(np.unique(y)) != {0.0, 1.0}:
        raise ValueError("AUC requires both binary classes encoded as 0 and 1")
    if "row_ids" in d:
        ids = d["row_ids"]
        if not isinstance(ids, list) or len(ids) != len(y) or any(not isinstance(v, (str, int)) for v in ids):
            raise ValueError("row_ids must identify every prediction")
        if len(set(ids)) != len(ids):
            raise ValueError("evaluation row_ids must be unique")
    return y, p


def validate_seed(seed_res, metric="accuracy", n_boot=1000, same_n=None):
    if not isinstance(seed_res, dict) or set(seed_res) != set(CONFIGS):
        raise ValueError("worker result must contain exactly orig, fix_A, fix_B and fix_both")
    if isinstance(n_boot, bool) or not isinstance(n_boot, int) or n_boot < 1:
        raise ValueError("n_boot must be a positive integer")
    pairs = {k: validate_vectors(seed_res[k], metric) for k in CONFIGS}
    if same_n is not None and (isinstance(same_n, bool) or not isinstance(same_n, int)
                               or same_n < 1 or same_n > min(len(v[0]) for v in pairs.values())):
        raise ValueError("same_n must be a positive integer no larger than any evaluation set")
    return pairs


def _correct(d):
    y, p = validate_vectors(d)
    return (y == p).astype(float)


def _ci(x):
    if len(x) == 0 or not np.isfinite(x).all():
        raise ValueError("no finite bootstrap estimates; measurement is inconclusive")
    lo, hi = np.percentile(x, [2.5, 97.5])
    return float(lo), float(hi)


def _score_metric(name):
    from sklearn.metrics import average_precision_score, roc_auc_score
    return {"pr_auc": average_precision_score, "roc_auc": roc_auc_score}[name]


def score_factorial_stats(seed_res, metric, n_boot=1000, seed=0, same_n=None):
    """G6: same estimand as factorial_stats, for a score metric (PR-AUC = average precision, or ROC-AUC) computed
    from (y_true, y_score). UNPAIRED bootstrap: each config's (y, score) rows are resampled independently; a replicate
    with a single class in some config is dropped (counted in 'boot_dropped')."""
    pairs = validate_seed(seed_res, metric, n_boot, same_n)
    f = _score_metric(metric)
    rng = np.random.default_rng(seed)
    ys = {k: pairs[k][0] for k in CONFIGS}
    ps = {k: pairs[k][1] for k in CONFIGS}
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
    validate_seed(seed_res, "accuracy", n_boot, same_n)
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


def all_seeds(result, n_boot=1000, expected_seeds=None):
    """Per-seed full-n stats plus the same-n subsample sensitivity check (min test n across configs)."""
    if not isinstance(result, dict) or not isinstance(result.get("seeds"), dict) or not result["seeds"]:
        raise ValueError("worker result needs nonempty seed results")
    if any(not isinstance(s, str) or not s.isdigit() for s in result["seeds"]):
        raise ValueError("seed keys must be nonnegative integer strings")
    if len({int(s) for s in result["seeds"]}) != len(result["seeds"]):
        raise ValueError("duplicate seed identity")
    if expected_seeds is not None and set(result["seeds"]) != {str(s) for s in expected_seeds}:
        raise ValueError("worker seed set differs from requested seeds")
    rows = {}
    metric = result.get("metric", "accuracy")
    for s, res in result["seeds"].items():
        validate_seed(res, metric, n_boot)
        n_min = min(len(res[k]["y"]) for k in CONFIGS)
        if metric == "accuracy":
            rows[s] = {"full": factorial_stats(res, n_boot, int(s)),
                       "same_n": factorial_stats(res, n_boot, int(s) + 7, same_n=n_min)}
        else:  # G6 score metric; ROC-AUC reported alongside PR-AUC
            rows[s] = {"full": score_factorial_stats(res, metric, n_boot, int(s)),
                       "roc_auc": score_factorial_stats(res, "roc_auc", n_boot, int(s)) if metric != "roc_auc" else None}
    return rows
