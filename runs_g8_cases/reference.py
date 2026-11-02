import importlib.util, json, sys, warnings
from pathlib import Path
import numpy as np
from sklearn.metrics import roc_auc_score
ROOT = Path(__file__).resolve().parent.parent
def run(case, seeds):
    spec = importlib.util.spec_from_file_location("t_" + case, ROOT/"real"/case/"train.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    df = m.load(str(ROOT/"real"/case/"data.csv"))
    return [float(roc_auc_score(*m.claimed_eval(df, s))) for s in seeds]
seeds = list(range(10)); out = {}
for c in ("ehg_apparent","ehg_clean","ehg_disguised","ehg_disguised_clean"): out[c] = run(c, seeds)
res = {"seeds": seeds, "roc_auc_by_case": out,
  "mean": {c: float(np.mean(v)) for c, v in out.items()},
  "inflation_named": [a-b for a,b in zip(out["ehg_apparent"], out["ehg_clean"])],
  "inflation_disguised": [a-b for a,b in zip(out["ehg_disguised"], out["ehg_disguised_clean"])]}
res["inflation_named_mean"] = float(np.mean(res["inflation_named"])); res["inflation_disguised_mean"] = float(np.mean(res["inflation_disguised"]))
res["disguise_identical_to_named"] = bool(np.allclose(out["ehg_apparent"], out["ehg_disguised"]) and np.allclose(out["ehg_clean"], out["ehg_disguised_clean"]))
Path(ROOT/"runs_g8_cases"/"reference.json").write_text(json.dumps(res, indent=1)); print(json.dumps(res, indent=1))
