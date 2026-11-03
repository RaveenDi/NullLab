"""Real subprocess checks of transformer provenance, without model API calls."""

from pathlib import Path

import numpy as np
import pandas as pd

from agent import contract_g9, guard_g9

SOURCE = '''
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.linear_model import LogisticRegression
TARGET = "target"
def load(path="data.csv"):
    return pd.read_csv(path)
def feats(df):
    return [c for c in df.columns if c != TARGET]
def evaluate(X, y, seed):
    ys, ps = [], []
    for tr, te in StratifiedKFold(n_splits=3, shuffle=True, random_state=seed).split(X, y):
        model = LogisticRegression(solver="liblinear", random_state=seed)
        model.fit(X[tr], y[tr])
        ys.append(y[te])
        ps.append(model.predict(X[te]))
    return np.concatenate(ys), np.concatenate(ps)
def claimed_eval(df, seed):
    X = df[feats(df)].to_numpy(dtype=float)
    y = df[TARGET].to_numpy().astype(int)
    V = StandardScaler().fit_transform(X)
    return evaluate(V, y, seed)
'''


def prepare(path: Path, source=SOURCE):
    rng = np.random.default_rng(713)
    frame = pd.DataFrame(rng.normal(size=(60, 3)), columns=["a", "b", "c"])
    frame["target"] = [0, 1] * 30
    frame.to_csv(path / "data.csv", index=False)
    (path / "train.py").write_text(source)
    (path / "excerpt.md").write_text("Independent records from the same population; retrospective screening.")


def test_scaler_control_keeps_trace_and_model_identity(tmp_path):
    prepare(tmp_path)
    plan = {"verdict": "flaw", "reason": "Fit preprocessing only inside each fold", "factors": [{"id": "A", "flaw": "Whole-data scaler", "evidence_line": "V = StandardScaler().fit_transform(X)", "ops": [{"op": "move_into_fold", "step": "claimed_eval", "call": "StandardScaler"}]}], "predicted_drop_pp": {"fix_all": 0}, "culprit_ranking": ["A"]}
    result = contract_g9.check_plan(plan, tmp_path, runtime=True)
    assert result["ok"], result["problems"]
    facts = result["runtime"]["configs"]["fix_all"]["facts"]
    assert facts["StandardScaler_overlap"]["before"] > 0
    assert facts["StandardScaler_overlap"]["after"] == 0
    assert "LogisticRegression" in facts["model"]


def test_unverified_transformer_cannot_inherit_row_identity(tmp_path):
    child = '''
class ReorderingScaler(StandardScaler):
    def fit_transform(self, X, y=None, **kwargs):
        return super().fit_transform(X, y, **kwargs)[::-1]
'''
    source = SOURCE.replace('TARGET = "target"', child + '\nTARGET = "target"').replace("V = StandardScaler()", "V = ReorderingScaler()")
    prepare(tmp_path, source)
    trace = guard_g9.trace_run(source, tmp_path)
    check = guard_g9.behaviour_check(trace, trace, [], source)
    assert check["decision"] != "ACCEPT"
    assert any("fidelity cannot be verified" in p for p in check["problems"])
