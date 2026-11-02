"""Pre-flight for compiled configs (G9, EVAL-12 'Robustness'): catch a crash in seconds, before a 7-minute sandbox run.

  1. lint(src)         pyflakes if installed in the venv, else stdlib `ast`: syntax error + 'name is never bound anywhere in the file'.
                       (Flow-insensitive on purpose: it reports only names that CANNOT exist, so it has no false alarms on valid code.)
  2. smoke(case, ...)  runs controlled_eval of fix_A / fix_B / fix_both on a 200-row DOWNSAMPLED copy of data.csv, one seed, in the same kind of
                       sandbox as the real run (same interpreter and pinned pandas/sklearn, scrubbed env, `-I`, sandbox/run._block_network: no network,
                       file allow-list). So an API that does not exist on the pinned library (G7 r3: DataFrame/Series.to_numpy(kind=...) on pandas 3.x)
                       crashes here exactly as it would in the long run. The unchanged claimed_eval ('orig') is NOT run (profiled: it is the bulk of the
                       cost and it is not model-authored), and ensemble-size knobs (N_TREES, N_ESTIMATORS, ...) are shrunk to a few units after import
                       so a 30 s budget holds on a loaded machine; that changes speed, not which code paths run.
                       Rows are taken at evenly spaced positions of the ORIGINAL order (never shuffled), so time order survives for temporal splits.
                       A smoke 'ok' proves only: it lints, it executes, it returns non-empty equal-length y/p vectors for each config.
                       It does NOT prove the fix is correct or the stats well-posed (a 200-row sample can legitimately give tiny test sets).
  3. check_plan(...)   build_configs from a planner plan + lint + smoke; returns a structured verdict with a repair-prompt text.

Nothing in sandbox/*, fidelity.py or llm.py is edited; they are imported and called."""
import ast
import builtins
import re
import shutil
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SMOKE_ROWS = 200
SMOKE_SEEDS = (42,)
SMOKE_TIMEOUT_S = 30
CONFIGS = ("fix_A", "fix_B", "fix_both")
_BUILTINS = set(dir(builtins)) | {"__file__", "__name__", "__doc__", "__spec__", "__package__", "__builtins__", "__path__"}


# ---------------- 1. lint ----------------
def _bound_names(tree):
    """Every identifier that is bound anywhere in the file (any scope): assignments, defs, classes, imports, args, except/with/for targets, comprehensions, globals."""
    names = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, (ast.Store, ast.Del)):
            names.add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(n.name)
        elif isinstance(n, ast.arg):
            names.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                names.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            names.add(n.name)
        elif isinstance(n, (ast.Global, ast.Nonlocal)):
            names.update(n.names)
        elif isinstance(n, ast.MatchAs) and n.name:
            names.add(n.name)
        elif isinstance(n, ast.MatchStar) and n.name:
            names.add(n.name)
        elif isinstance(n, ast.MatchMapping) and n.rest:
            names.add(n.rest)
    return names


def lint(src, filename="<patch>"):
    """Returns a list of {'line', 'kind', 'msg'}. Empty = clean."""
    try:
        tree = ast.parse(src, filename=filename)
    except SyntaxError as e:
        return [{"line": e.lineno, "kind": "SyntaxError", "msg": f"{e.msg} (line {e.lineno})"}]
    try:  # pyflakes is optional (NOT installed in this venv; this branch is untested, any failure falls through to the stdlib check)
        from pyflakes import checker as _pfc, messages as _pfm  # type: ignore
        chk = _pfc.Checker(tree, filename)
        return sorted(({"line": m.lineno, "kind": "NameError", "msg": f"undefined name '{m.message_args[0]}'"}
                       for m in chk.messages if isinstance(m, _pfm.UndefinedName)), key=lambda f: f["line"])
    except Exception:  # noqa: BLE001  (ImportError or any pyflakes API difference)
        pass
    bound, found, seen = _bound_names(tree) | _BUILTINS, [], set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id not in bound and (n.id, n.lineno) not in seen:
            seen.add((n.id, n.lineno))
            found.append({"line": n.lineno, "kind": "NameError", "msg": f"undefined name '{n.id}' (never defined, imported or assigned in the file)"})
    return sorted(found, key=lambda f: f["line"])


# ---------------- 2. smoke execution ----------------
def _even(idx, k):
    """k evenly spaced elements of the list idx (all of it if k >= len)."""
    if k >= len(idx):
        return list(idx)
    return [idx[(i * (len(idx) - 1)) // (k - 1)] for i in range(k)] if k > 1 else [idx[0]]


def downsample_csv(src_csv, dst_csv, rows=SMOKE_ROWS, target=None):
    """Copy about `rows` data rows (original order kept, never shuffled) plus the header. Rows are evenly spaced WITHIN each class so that every
    class survives in every stretch of time (a 1.6 percent minority class would otherwise vanish from a plain 200-row slice and break valid code
    with 'a cannot be empty'). Up to rows//4 minority rows are kept (this distorts the base rate; the smoke run checks that code runs, not what it scores).
    `target` = label column name (default: the last column). Pure text/csv: no pandas, no shuffling."""
    import csv
    import io
    lines = Path(src_csv).read_text(encoding="utf-8").splitlines()
    head, body = lines[0], [x for x in lines[1:] if x.strip()]
    if len(body) <= rows:
        keep = list(range(len(body)))
    else:
        cols = next(csv.reader(io.StringIO(head)))
        t = cols.index(target) if target in cols else len(cols) - 1
        lab = [next(csv.reader(io.StringIO(x)))[t] for x in body]
        by = {}
        for i, l in enumerate(lab):
            by.setdefault(l, []).append(i)
        classes = sorted(by, key=lambda l: len(by[l]))          # smallest first
        keep, budget = [], rows
        for n, l in enumerate(classes):
            share = max(1, budget // (len(classes) - n)) if n else min(len(by[l]), max(1, rows // 4))
            take = _even(by[l], min(share, budget - (len(classes) - n - 1)))
            keep += take
            budget -= len(take)
        keep = sorted(set(keep))
    Path(dst_csv).write_text("\n".join([head] + [body[i] for i in keep]) + "\n", encoding="utf-8")
    return len(keep)


def target_of(train_src):
    m = re.search(r"""^TARGET\s*=\s*["'](\w+)["']""", train_src, re.M)
    return m.group(1) if m else None


_TB_FILE = re.compile(r'File "([^"]*?([^\\/"]+))", line (\d+), in (\S+)')


def parse_traceback(stderr, patch_files=("fix_A.py", "fix_B.py", "fix_both.py")):
    """Pull the final exception and the last frame inside one of the patch files out of a Python traceback."""
    text = stderr or ""
    lines = [l for l in text.strip().splitlines() if l.strip()]
    exc = lines[-1] if lines else ""
    kind, _, msg = exc.partition(":")
    frames = _TB_FILE.findall(text)
    mine = [f for f in frames if f[1] in patch_files]
    out = {"exception": exc[:300], "kind": kind.strip() if re.fullmatch(r"[\w.]+", kind.strip() or "?") else "Error", "message": msg.strip()[:300]}
    if mine:
        _, fname, ln, fn = mine[-1]
        out.update(config=fname[:-3], line=int(ln), function=fn)
        m = re.search(re.escape(f'line {ln}, in {fn}') + r"\r?\n\s+(.+)", text)
        if m:
            out["code"] = m.group(1).strip()[:200]
    elif frames:
        out.update(config=None, line=int(frames[-1][2]), function=frames[-1][3])
    return out


def repair_text(v):
    """The text a repair prompt can feed back (same spirit as factorial_g8's crash feedback, but produced before the long run)."""
    if v["ok"]:
        return ""
    where = f" in {v['config']}" if v.get("config") else ""
    line = f" at line {v['line']}" if v.get("line") else ""
    code = f"\n  offending code: {v['code']}" if v.get("code") else ""
    return (f"PRE-FLIGHT FAILED ({v['stage']}){where}{line}: {v['kind']}: {v['message']}{code}\n"
            "Fix ONLY this (for example an argument or method that does not exist on the pinned library version, or a name that is not defined) "
            "and keep the rest of the plan. The pinned library versions are those of this environment; use only calls you are sure exist.")


RUNNER = r'''import importlib.util, json, os, sys
sys.path.insert(0, os.getcwd())
import numpy  # noqa: F401  heavy imports before the network / file allow-list is applied
import train
try:  # same pre-load as sandbox/run_factorial.py (native thread-pool libraries are resolved before dlopen is blocked)
    from sklearn.neighbors import KNeighborsClassifier
    KNeighborsClassifier(n_neighbors=1).fit([[0.0], [1.0]], [0, 1]).predict([[0.2]])
except Exception:
    pass
from run import _block_network
_block_network()
SHRINK = ("N_TREES", "N_ESTIMATORS", "N_ITER", "N_ROUNDS", "EPOCHS", "N_BOOT", "N_REPEATS")
out = {"seeds": {}}
mods = {}
for c in ("fix_A", "fix_B", "fix_both"):
    spec = importlib.util.spec_from_file_location(c, c + ".py")
    mods[c] = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mods[c])
    for k in SHRINK:
        if isinstance(getattr(mods[c], k, None), int) and getattr(mods[c], k) > 8:
            setattr(mods[c], k, 8)
df = train.load("data.csv")
for s in [int(x) for x in sys.argv[1].split(",")]:
    res = {}
    for c in ("fix_A", "fix_B", "fix_both"):
        y, p = mods[c].controlled_eval(df, s)
        res[c] = {"n_y": len(y), "n_p": len(p)}
    out["seeds"][str(s)] = res
json.dump(out, open("smoke_result.json", "w"))
'''


def _result_problems(result):
    bad = []
    for seed, res in (result.get("seeds") or {}).items():
        for cfg in CONFIGS:
            r = res.get(cfg) or {}
            if not r.get("n_y") or r.get("n_y") != r.get("n_p"):
                bad.append(f"{cfg}: returned empty or unequal y/p vectors on the {SMOKE_ROWS}-row sample (seed {seed})")
    return bad


def _run_smoke(tmp, seeds, timeout):
    import json
    import subprocess
    import sys
    from sandbox import executor
    shutil.copy(ROOT / "sandbox" / "run.py", tmp / "run.py")
    (tmp / "smoke_runner.py").write_text(RUNNER, encoding="utf-8")
    cmd = [sys.executable, "-I", "smoke_runner.py", ",".join(map(str, seeds))]
    try:
        r = subprocess.run(cmd, cwd=str(tmp), env=executor._scrubbed_env(), capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "timeout"}
    if r.returncode != 0 or not (tmp / "smoke_result.json").exists():
        return {"status": "error", "stderr": r.stderr[-2000:]}
    return {"status": "ok", "result": json.loads((tmp / "smoke_result.json").read_text())}


SIZE_SENSITIVE = ("ValueError", "IndexError", "ZeroDivisionError", "LinAlgError", "UndefinedMetricWarning", "RuntimeError", "AssertionError")


def smoke(case_dir, patches, rows=SMOKE_ROWS, seeds=SMOKE_SEEDS, timeout=SMOKE_TIMEOUT_S):
    """Smoke with one escalation: a failure that a tiny sample can cause by itself (ValueError, IndexError, ...) is re-run once on 3x the rows;
    if it still fails it is reported with definitive=False (the caller may warn instead of block). TypeError, AttributeError, NameError,
    ImportError, KeyError, SyntaxError, a timeout etc. do not depend on the sample size: definitive=True."""
    t0 = time.time()
    v = _smoke_once(case_dir, patches, rows, seeds, timeout)
    v["definitive"] = not v["ok"]
    if not v["ok"] and v["stage"] == "smoke" and v["kind"] in SIZE_SENSITIVE:
        left = timeout - (time.time() - t0)
        if left > 8:
            v2 = _smoke_once(case_dir, patches, rows * 3, seeds, left)
            v2["escalated_from"] = {"rows": rows, "kind": v["kind"], "message": v["message"]}
            v2["definitive"] = False
            v2["elapsed_s"] = round(time.time() - t0, 2)
            return v2
        v["definitive"] = False
    v["elapsed_s"] = round(time.time() - t0, 2)
    return v


def _smoke_once(case_dir, patches, rows=SMOKE_ROWS, seeds=SMOKE_SEEDS, timeout=SMOKE_TIMEOUT_S):
    """patches = {'fix_A': src, 'fix_B': src, 'fix_both': src} (full compiled train.py variants as built by fidelity.build_configs).
    Returns {'ok', 'stage': 'lint'|'smoke', 'kind', 'message', 'config', 'line', 'code', 'elapsed_s', 'repair_text', 'rows'}; never raises on a patch fault."""
    t0 = time.time()
    case_dir = Path(case_dir)
    v = {"ok": True, "stage": "smoke", "kind": None, "message": "", "config": None, "line": None, "code": None, "rows": rows}

    def done():
        v["elapsed_s"] = round(time.time() - t0, 2)
        v["repair_text"] = repair_text(v)
        return v
    for cfg in CONFIGS:  # stage 1: lint every config (cheap, no process)
        if not isinstance(patches.get(cfg), str):
            v.update(ok=False, stage="lint", kind="StructureError", message=f"{cfg}: no source was compiled", config=cfg)
            return done()
        f = lint(patches[cfg], f"{cfg}.py")
        if f:
            v.update(ok=False, stage="lint", kind=f[0]["kind"], message=f[0]["msg"], config=cfg, line=f[0]["line"])
            src_lines = patches[cfg].splitlines()
            if f[0]["line"] and 0 < f[0]["line"] <= len(src_lines):
                v["code"] = src_lines[f[0]["line"] - 1].strip()[:200]
            v["all_findings"] = f[:10]
            return done()
    tmp = Path(tempfile.mkdtemp(prefix="nulllab_smoke_"))  # stage 2: sandbox run on a downsampled copy
    try:
        shutil.copy(case_dir / "train.py", tmp / "train.py")
        v["rows"] = downsample_csv(case_dir / "data.csv", tmp / "data.csv", rows, target_of((case_dir / "train.py").read_text(encoding="utf-8")))
        for cfg in CONFIGS:
            (tmp / f"{cfg}.py").write_text(patches[cfg], encoding="utf-8")
        ex = _run_smoke(tmp, tuple(seeds), timeout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if ex["status"] == "timeout":
        v.update(ok=False, kind="Timeout", message=f"the {v['rows']}-row smoke run exceeded {timeout}s (an unbounded loop or a very heavy call)")
    elif ex["status"] != "ok":
        tb = parse_traceback(ex.get("stderr", ""))
        v.update(ok=False, kind=tb["kind"], message=tb["message"] or tb["exception"], config=tb.get("config"), line=tb.get("line"), code=tb.get("code"),
                 exception=tb["exception"])
    else:
        bad = _result_problems(ex["result"])
        if bad:
            v.update(ok=False, kind="EmptyResult", message="; ".join(bad[:3]))
    return done()


def check_plan(case_dir, plan, rows=SMOKE_ROWS, timeout=SMOKE_TIMEOUT_S):
    """Compile a planner plan with fidelity.build_configs and pre-flight it. Static-guard violations are NOT judged here (that is factorial_g7.guard)."""
    from agent import fidelity
    src = (Path(case_dir) / "train.py").read_text(encoding="utf-8")
    cfgs = fidelity.build_configs(src, (plan or {}).get("edits"))
    bad = [x for c in cfgs.values() for x in c["violations"] if x.startswith("STRUCTURE") or "syntax" in x.lower()]
    if any(c["src"] is None for c in cfgs.values()):
        v = {"ok": False, "stage": "lint", "kind": "StructureError", "message": (bad or ["plan has no compilable edits"])[0], "config": None,
             "line": None, "code": None, "elapsed_s": 0.0, "rows": 0}
        v["repair_text"] = repair_text(v)
        return v
    return smoke(case_dir, {k: cfgs[k]["src"] for k in CONFIGS}, rows=rows, timeout=timeout)


def replay_recorded(case_dir, record_json, case_name, rows=SMOKE_ROWS, timeout=SMOKE_TIMEOUT_S):
    """Smoke the recorded final plan of a saved run file (e.g. runs_g7/r3.json, civilwar_disguised). Offline, $0."""
    import json
    rec = json.loads(Path(record_json).read_text(encoding="utf-8"))["loop"][case_name]
    return check_plan(case_dir, rec["final_plan"], rows=rows, timeout=timeout)
