"""Evaluator-only: builds the 4 G4 compositional cases + 1 clean factorial variant (all SYNTHETIC) and their reference
2x2 patches. Agent view -> factorial/<case>/{train.py, data.csv, excerpt.md}. Evaluator -> eval/factorial_truth_g4.json
(flaw definitions + reference patches + design intent; never enters the sandbox or a prompt).

Each case has two plausible flaws A and B (Kapoor & Narayanan taxonomy, https://arxiv.org/abs/2207.07048) and is
designed so that STATIC READING is tempted to the wrong answer:
  g4_freight_delay     CANCELLATION   A = carrier target rate on all rows (L2/L1.2, inflates);
                                      B = test-only zero-fill of a key reading while Methods say median (deflates; readings go missing
                                      more often on late shipments)
  g4_pump_inspection   WRONG-CULPRIT  A = SelectKBest on all rows (textbook L1.3, salient, ~harmless here);
                                      B = "previous load" lag written as shift(-1) = NEXT inspection (L2 look-ahead)
  g4_crop_irrigation   BENIGN-SUSP.   A = scaler+PCA fit on all rows (L1.2 look); B = grid search on all rows (L1.1
                                      look); n large, unsupervised step + tiny grid -> both ~0
  g4_assay_replicates  SYNERGY-2      A = failed reads imputed with per-class means over all rows (L1.2 with labels);
                                      B = duplicate wells of one compound split at random (L1.4 duplicates)
  g4_visit_history_clean  CLEAN variant of the spike case: group split + out-of-fold patient rate.
Run: python eval/build_factorial_g4.py [--validate]"""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hash_cols import hname  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "factorial"

HEAD = "import numpy as np\nimport pandas as pd\n"


# ============================== (a) CANCELLATION ==============================
def freight():
    T, C, D = hname("late_delivery"), hname("carrier_id"), hname("dwell_hours")
    X = [hname(f"op_{i}") for i in range(5)]
    rng = np.random.default_rng(11)
    rows = []
    for c in range(520):
        u = rng.normal(0, 1.3)
        for _ in range(rng.integers(3, 9)):
            z = rng.normal(0, 1, 6)
            logit = -0.3 + u + 1.6 * z[0] + 0.7 * z[1] - 0.6 * z[2] + 0.3 * z[3]
            dwell = round(float(max(1.0, 20 + 6 * z[0])), 1)
            yv = int(rng.random() < 1 / (1 + np.exp(-logit)))
            if rng.random() < (0.5 if yv else 0.12):  # dwell sensors drop out more often at congested hubs
                dwell = np.nan
            ops = [round(float(v), 3) for v in (12 + 3 * z[1], 4 + 1.5 * z[2], 50 + 10 * z[3], 7 + 2 * z[4], 1 + 0.5 * z[5])]
            rows.append([dwell, *ops, c, yv])
    df = pd.DataFrame(rows, columns=[D] + X + [C, T]).sample(frac=1, random_state=11).reset_index(drop=True)
    train = HEAD + f'''from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

TARGET = "{T}"
CARRIER = "{C}"
RATE = "carrier_late_rate"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_carrier_rate(df):
    # each carrier's historical late-delivery rate
    df = df.copy()
    df[RATE] = df.groupby(CARRIER)[TARGET].transform("mean")
    return df


def feats(df):
    return [c for c in df.columns if c not in (TARGET, CARRIER)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=3, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def impute(Xtr, Xte):
    med = Xtr.median()
    return Xtr.fillna(med), Xte.fillna(0)  # held-out rows: a missing dwell reading counts as no dwell


def claimed_eval(df, seed):
    data = add_carrier_rate(df)
    tr, te = split_idx(data, seed)
    f = feats(data)
    Xtr, Xte = impute(data.iloc[tr][f], data.iloc[te][f])
    y = data[TARGET].to_numpy()
    return y[te], fit_predict(Xtr.to_numpy(), y[tr], Xte.to_numpy(), seed)
'''
    excerpt = """## Methods (excerpt)
We predict whether a freight shipment arrives late from six operational measurements plus each carrier's historical late-delivery rate.
Dwell time is missing for about a third of shipments; missing readings are imputed with the training median.
Shipments were randomly divided into 75% training and 25% test with a fixed random seed.
## Results
Our model achieves {acc}% accuracy on held-out shipments and is intended to flag late shipments from our existing carriers in live dispatch.
"""
    oof = '''from sklearn.model_selection import KFold


def _oof_rate(trd, ted, seed):
    T, C, R = train.TARGET, train.CARRIER, train.RATE
    prior = trd[T].mean()
    trd[R] = prior
    for a, b in KFold(5, shuffle=True, random_state=seed).split(trd):
        m = trd.iloc[a].groupby(C)[T].mean()
        trd.loc[trd.index[b], R] = trd.iloc[b][C].map(m).fillna(prior).to_numpy()
    ted[R] = ted[C].map(trd.groupby(C)[T].mean()).fillna(prior)
    return trd, ted


def _run(df, seed, fix_rate, fix_impute):
    if fix_rate:
        tr, te = train.split_idx(df, seed)
        trd, ted = _oof_rate(df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy(), seed)
    else:
        data = train.add_carrier_rate(df)
        tr, te = train.split_idx(data, seed)
        trd, ted = data.iloc[tr].reset_index(drop=True), data.iloc[te].reset_index(drop=True)
    f = train.feats(trd)
    Xtr, Xte = trd[f], ted[f]
    if fix_impute:
        med = Xtr.median()
        Xtr, Xte = Xtr.fillna(med), Xte.fillna(med)
    else:
        Xtr, Xte = train.impute(Xtr, Xte)
    return ted[train.TARGET].to_numpy(), train.fit_predict(Xtr.to_numpy(), trd[train.TARGET].to_numpy(), Xte.to_numpy(), seed)
'''
    ref = {k: "import numpy as np\nimport train\n" + oof + f"\n\ndef controlled_eval(df, seed):\n    return _run(df, seed, {a}, {b})\n"
           for k, (a, b) in {"fix_A": (True, False), "fix_B": (False, True), "fix_both": (True, True)}.items()}
    return dict(case="g4_freight_delay", kind="CANCELLATION", df=df, train=train, excerpt=excerpt, ref=ref,
                flaw_A={"kind": "L2/L1.2 target-derived carrier rate computed on all rows (incl. test + self) before the split; INFLATES",
                        "code_substr": 'df[RATE] = df.groupby(CARRIER)[TARGET].transform("mean")'},
                flaw_B={"kind": "test-only zero-fill of missing dwell readings, Methods say training-median imputation; DEFLATES",
                        "code_substr": "return Xtr.fillna(med), Xte.fillna(0)"},
                temptation="reading sees a textbook target leak and predicts the claim is inflated (fix-both drop > 0); "
                           "the deflating zero-fill outweighs it, so the honest accuracy is HIGHER than claimed")


# ============================== (b) WRONG-CULPRIT ==============================
def pump():
    T, U, O, L = hname("fault_next"), hname("pump_id"), hname("inspection_no"), hname("load")
    S = [hname(f"sensor_{i}") for i in range(9)]
    rng = np.random.default_rng(12)
    rows = []
    for p in range(120):
        base = rng.normal(0, 0.6)
        n = 27
        load = np.empty(n)
        load[0] = base + rng.normal()
        for t in range(1, n):
            load[t] = base + 0.55 * (load[t - 1] - base) + rng.normal(0, 0.85)
        for t in range(n - 1):
            vib = 0.5 * load[t] + rng.normal(0, 1)
            temp = 0.35 * load[t] + rng.normal(0, 1)
            pres = 0.3 * base + rng.normal(0, 1)
            flow = -0.3 * load[t] + rng.normal(0, 1)
            noise = rng.normal(0, 1, 5)
            y = int(load[t + 1] + rng.normal(0, 0.45) > 0.55)
            rows.append([p, t, round(load[t], 3), *[round(float(v), 3) for v in (vib, temp, pres, flow, *noise)], y])
    df = pd.DataFrame(rows, columns=[U, O, L] + S[:9] + [T])
    train = HEAD + f'''from sklearn.model_selection import train_test_split
from sklearn.feature_selection import SelectKBest, f_classif
from sklearn.ensemble import RandomForestClassifier

TARGET = "{T}"
PUMP = "{U}"
ORDER = "{O}"
LOAD = "{L}"
K = 6


def load(path="data.csv"):
    return pd.read_csv(path)


def add_lag(df):
    # previous inspection's load for the same pump
    df = df.sort_values([PUMP, ORDER]).copy()
    df["prev_load"] = df.groupby(PUMP)[LOAD].shift(-1)
    return df.dropna(subset=["prev_load"]).reset_index(drop=True)


def feats(df):
    return [c for c in df.columns if c not in (TARGET, PUMP, ORDER)]


def select(df, cols):
    # keep the K most informative sensors (ANOVA F-test)
    sel = SelectKBest(f_classif, k=K).fit(df[cols], df[TARGET])
    return [c for c, keep in zip(cols, sel.get_support()) if keep]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    data = add_lag(df)
    cols = select(data, feats(data))
    tr, te = split_idx(data, seed)
    X, y = data[cols].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
'''
    excerpt = """## Methods (excerpt)
We predict whether a pump faults at its next inspection from ten sensor readings plus the pump's load at the previous inspection.
The six most informative sensors were selected with an ANOVA F-test; inspections were randomly divided into 75% training and 25% test with a fixed random seed.
## Results
Our model achieves {acc}% accuracy on held-out inspections and is intended to schedule maintenance across the existing fleet.
"""
    body = '''

def _lag(df, fix_lag):
    if not fix_lag:
        return train.add_lag(df)
    d = df.sort_values([train.PUMP, train.ORDER]).copy()
    d["prev_load"] = d.groupby(train.PUMP)[train.LOAD].shift(1)
    return d.dropna(subset=["prev_load"]).reset_index(drop=True)


def _run(df, seed, fix_sel, fix_lag):
    data = _lag(df, fix_lag)
    tr, te = train.split_idx(data, seed)
    f = train.feats(data)
    cols = train.select(data.iloc[tr], f) if fix_sel else train.select(data, f)
    X, y = data[cols].to_numpy(), data[train.TARGET].to_numpy()
    return y[te], train.fit_predict(X[tr], y[tr], X[te], seed)
'''
    ref = {k: "import numpy as np\nimport train\n" + body + f"\n\ndef controlled_eval(df, seed):\n    return _run(df, seed, {a}, {b})\n"
           for k, (a, b) in {"fix_A": (True, False), "fix_B": (False, True), "fix_both": (True, True)}.items()}
    return dict(case="g4_pump_inspection", kind="WRONG-CULPRIT", df=df, train=train, excerpt=excerpt, ref=ref,
                flaw_A={"kind": "L1.3 feature selection (SelectKBest) fit on all rows before the split; salient textbook flaw, "
                                "but the informative sensors are strong so the selection is stable (~harmless)",
                        "code_substr": "cols = select(data, feats(data))"},
                flaw_B={"kind": "L2 look-ahead: 'previous' load is shift(-1) = the NEXT inspection's load, which drives the label",
                        "code_substr": 'df["prev_load"] = df.groupby(PUMP)[LOAD].shift(-1)'},
                temptation="reading ranks the textbook feature-selection leak first; the one-character lag direction drives the inflation")


# ============================== (c) BENIGN-SUSPICIOUS ==============================
def crop():
    T = hname("needs_irrigation")
    S = [hname(f"field_{i}") for i in range(10)]
    rng = np.random.default_rng(13)
    n = 3200
    Z = rng.normal(0, 1, (n, 10))
    Z[:, 5] = 0.7 * Z[:, 0] + 0.7 * Z[:, 5]
    Z[:, 6] = 0.6 * Z[:, 1] + 0.8 * Z[:, 6]
    logit = 1.2 * Z[:, 0] - 1.0 * Z[:, 1] + 0.8 * Z[:, 2] * Z[:, 3] + 0.6 * np.sin(2 * Z[:, 4])
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    scale = np.array([18, 6, 2.5, 40, 0.8, 12, 3, 150, 9, 1.2])
    loc = np.array([35, 22, 6.5, 300, 4, 60, 15, 900, 50, 7])
    df = pd.DataFrame(np.round(loc + scale * Z, 3), columns=S)
    df[T] = y
    train = HEAD + f'''from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier

TARGET = "{T}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c != TARGET]


def prepare(df):
    # standardise and decorrelate the sensor block
    Z = StandardScaler().fit_transform(df[feats(df)])
    return PCA(n_components=8, random_state=0).fit_transform(Z), df[TARGET].to_numpy()


def tune(X, y):
    grid = GridSearchCV(RandomForestClassifier(n_estimators=100, random_state=0, n_jobs=1),
                        {{"max_depth": [8, None], "min_samples_leaf": [1, 5]}}, cv=3, refit=False)
    return grid.fit(X, y).best_params_


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    X, y = prepare(df)
    params = tune(X, y)
    tr, te = split_idx(df, seed)
    m = RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=1, **params)
    return y[te], m.fit(X[tr], y[tr]).predict(X[te])
'''
    excerpt = """## Methods (excerpt)
We predict whether a field plot needs irrigation within 48 hours from ten soil and weather sensor readings.
Readings are standardised and projected onto eight principal components; random-forest hyperparameters were chosen by 3-fold grid search.
Plots were randomly divided into 75% training and 25% test with a fixed random seed.
## Results
Our model achieves {acc}% accuracy on held-out plots and is intended for irrigation scheduling on the same farms.
"""
    body = '''from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.ensemble import RandomForestClassifier


def _run(df, seed, fix_prep, fix_tune):
    tr, te = train.split_idx(df, seed)
    y = df[train.TARGET].to_numpy()
    if fix_prep:
        f = train.feats(df)
        sc = StandardScaler().fit(df.iloc[tr][f])
        pca = PCA(n_components=8, random_state=0).fit(sc.transform(df.iloc[tr][f]))
        X = pca.transform(sc.transform(df[f]))
    else:
        X, y = train.prepare(df)
    params = train.tune(X[tr], y[tr]) if fix_tune else train.tune(X, y)
    m = RandomForestClassifier(n_estimators=100, random_state=seed, n_jobs=1, **params)
    return y[te], m.fit(X[tr], y[tr]).predict(X[te])
'''
    ref = {k: "import numpy as np\nimport train\n" + body + f"\n\ndef controlled_eval(df, seed):\n    return _run(df, seed, {a}, {b})\n"
           for k, (a, b) in {"fix_A": (True, False), "fix_B": (False, True), "fix_both": (True, True)}.items()}
    return dict(case="g4_crop_irrigation", kind="BENIGN-SUSPICIOUS", df=df, train=train, excerpt=excerpt, ref=ref,
                flaw_A={"kind": "L1.2 look: scaler + PCA fit on all rows before the split (unsupervised, n=3200 -> ~0 effect)",
                        "code_substr": "Z = StandardScaler().fit_transform(df[feats(df)])"},
                flaw_B={"kind": "L1.1 look: hyperparameter grid search on all rows incl. test (4-point grid -> ~0 effect)",
                        "code_substr": "params = tune(X, y)"},
                temptation="two textbook-looking leaks; reading should false-alarm, the measured effects are ~0")


# ============================== (d) SYNERGY-2 ==============================
def assay():
    T, CP = hname("active"), hname("compound_id")
    NR = 12
    R = [hname(f"readout_{i}") for i in range(NR)]
    rng = np.random.default_rng(14)
    rows = []
    for c in range(700):
        base = rng.normal(0, 1, NR)
        y = int(0.45 * base[0] - 0.35 * base[1] + 0.3 * base[2] + rng.normal(0, 1) > 0)
        for _ in range(3):  # replicate wells of the same compound
            v = np.round(base + rng.normal(0, 0.05, NR), 3)
            v[rng.random(NR) < 0.15] = np.nan  # failed reads
            rows.append([*v, c, y])
    df = pd.DataFrame(rows, columns=R + [CP, T]).sample(frac=1, random_state=14).reset_index(drop=True)
    train = HEAD + f'''from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier

TARGET = "{T}"
COMPOUND = "{CP}"


def load(path="data.csv"):
    return pd.read_csv(path)


def feats(df):
    return [c for c in df.columns if c not in (TARGET, COMPOUND)]


def impute(df):
    # fill failed reads with the mean of comparable compounds
    df = df.copy()
    cols = feats(df)
    df[cols] = df.groupby(TARGET)[cols].transform(lambda s: s.fillna(s.mean()))
    return df


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=300, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)


def claimed_eval(df, seed):
    data = impute(df)
    tr, te = split_idx(data, seed)
    f = feats(data)
    X, y = data[f].to_numpy(), data[TARGET].to_numpy()
    return y[te], fit_predict(X[tr], y[tr], X[te], seed)
'''
    excerpt = """## Methods (excerpt)
We predict whether a compound is active from 12 plate-reader readouts; each compound was assayed in three wells, and failed reads (about 15%) were imputed.
Wells were randomly divided into 75% training and 25% test with a fixed random seed.
## Results
Our model achieves {acc}% accuracy on held-out wells and is intended to triage newly synthesised compounds.
"""
    body = '''from sklearn.model_selection import GroupShuffleSplit


def _run(df, seed, fix_imp, fix_split):
    if fix_imp:
        data = df.copy()
    else:
        data = train.impute(df)
    if fix_split:
        tr, te = next(GroupShuffleSplit(1, test_size=0.25, random_state=seed).split(data, groups=data[train.COMPOUND]))
    else:
        tr, te = train.split_idx(data, seed)
    f = train.feats(data)
    if fix_imp:  # label-free imputation fit on the training rows only
        mu = data.iloc[tr][f].mean()
        data[f] = data[f].fillna(mu)
    X, y = data[f].to_numpy(), data[train.TARGET].to_numpy()
    return y[te], train.fit_predict(X[tr], y[tr], X[te], seed)
'''
    ref = {k: "import numpy as np\nimport train\n" + body + f"\n\ndef controlled_eval(df, seed):\n    return _run(df, seed, {a}, {b})\n"
           for k, (a, b) in {"fix_A": (True, False), "fix_B": (False, True), "fix_both": (True, True)}.items()}
    return dict(case="g4_assay_replicates", kind="SYNERGY-2", df=df, train=train, excerpt=excerpt, ref=ref,
                flaw_A={"kind": "L1.2 preprocessing with labels on train+test: failed reads imputed with the per-CLASS mean over all rows",
                        "code_substr": "df[cols] = df.groupby(TARGET)[cols].transform(lambda s: s.fillna(s.mean()))"},
                flaw_B={"kind": "L1.4 duplicates: the three wells of one compound land on both sides of a random well split; claim is about new compounds",
                        "code_substr": "return train_test_split(np.arange(len(df)), test_size=test_size, random_state=seed)"},
                temptation="a second genuine interaction with flaw classes (L1.2, L1.4) different from the spike's (L2, L3.2)")


# ============================== CLEAN factorial variant ==============================
def visit_clean():
    sys.path.insert(0, str(ROOT / "eval"))
    from build_factorial import make_data, TARGET as T, SUBJ as P
    df = make_data(seed=2027, n_pat=250)
    train = HEAD + f'''from sklearn.model_selection import GroupShuffleSplit, KFold
from sklearn.ensemble import RandomForestClassifier

TARGET = "{T}"
PATIENT = "{P}"
HIST = "patient_event_rate"


def load(path="data.csv"):
    return pd.read_csv(path)


def add_history(trd, ted, seed):
    # patient event rate from training labels only: out-of-fold inside training, training prior for unseen patients
    prior = trd[TARGET].mean()
    trd[HIST] = prior
    for a, b in KFold(5, shuffle=True, random_state=seed).split(trd):
        m = trd.iloc[a].groupby(PATIENT)[TARGET].mean()
        trd.loc[trd.index[b], HIST] = trd.iloc[b][PATIENT].map(m).fillna(prior).to_numpy()
    ted[HIST] = ted[PATIENT].map(trd.groupby(PATIENT)[TARGET].mean()).fillna(prior)
    return trd, ted


def feats(df):
    return [c for c in df.columns if c not in (TARGET, PATIENT)]


def fit_predict(Xtr, ytr, Xte, seed):
    m = RandomForestClassifier(n_estimators=200, min_samples_leaf=2, random_state=seed, n_jobs=1)
    return m.fit(Xtr, ytr).predict(Xte)


def split_idx(df, seed, test_size=0.25):
    # whole patients are held out
    return next(GroupShuffleSplit(1, test_size=test_size, random_state=seed).split(df, groups=df[PATIENT]))


def claimed_eval(df, seed):
    tr, te = split_idx(df, seed)
    trd, ted = add_history(df.iloc[tr].reset_index(drop=True).copy(), df.iloc[te].reset_index(drop=True).copy(), seed)
    f = feats(trd)
    return ted[TARGET].to_numpy(), fit_predict(trd[f].to_numpy(), trd[TARGET].to_numpy(), ted[f].to_numpy(), seed)
'''
    excerpt = """## Methods (excerpt)
We predict whether an outpatient visit ends in an adverse event from five routine lab measurements plus the patient's historical adverse-event rate, computed from training labels only (out-of-fold).
Whole patients were held out: 25% of patients form the test set (group split by patient, fixed random seed); test patients receive the training prior as their rate.
## Results
Our model achieves {acc}% accuracy on held-out patients and is intended to triage new patients at their first referral.
"""
    same = "import train\n\n\ndef controlled_eval(df, seed):\n    return train.claimed_eval(df, seed)\n"
    return dict(case="g4_visit_history_clean", kind="CLEAN", df=df, train=train, excerpt=excerpt,
                ref={"fix_A": same, "fix_B": same, "fix_both": same},
                flaw_A={"kind": "none (rate already out-of-fold, training labels only)", "code_substr": ""},
                flaw_B={"kind": "none (group split by patient)", "code_substr": ""},
                temptation="clean variant of the spike case; fix-both must span 0")


CASES = [freight, pump, crop, assay, visit_clean]


def _claimed_acc(case_dir):
    """Evaluator-side: the claimed number is the original protocol's mean accuracy over seeds 42-44."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("train_" + case_dir.name, case_dir / "train.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    df = m.load(str(case_dir / "data.csv"))
    accs = []
    for s in (42, 43, 44):
        y, p = m.claimed_eval(df, s)
        accs.append(float((np.asarray(y) == np.asarray(p)).mean()))
    return round(100 * sum(accs) / 3)


def main():
    truth = {}
    for build in CASES:
        c = build()
        out = FX / c["case"]
        out.mkdir(parents=True, exist_ok=True)
        c["df"].to_csv(out / "data.csv", index=False)
        (out / "train.py").write_text(c["train"], encoding="utf-8")
        (out / "excerpt.md").write_text(c["excerpt"].format(acc="XX"), encoding="utf-8")
        acc = _claimed_acc(out)
        (out / "excerpt.md").write_text(c["excerpt"].format(acc=acc), encoding="utf-8")
        truth[c["case"]] = {"case": c["case"], "kind": c["kind"], "provenance": "SYNTHETIC", "claimed_acc_pct": acc,
                            "flaw_A": c["flaw_A"], "flaw_B": c["flaw_B"], "temptation": c["temptation"], "ref_patches": c["ref"],
                            "agent_view_sha256": {n: hashlib.sha256((out / n).read_bytes()).hexdigest()
                                                  for n in ("train.py", "data.csv", "excerpt.md")}}
        print(c["case"], c["kind"], c["df"].shape, "claimed", acc)
    (ROOT / "eval" / "factorial_truth_g4.json").write_text(json.dumps(truth, indent=1))


if __name__ == "__main__":
    main()
