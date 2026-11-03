"""Bounded offline audit probes; no API requests, execution of cases, or full test suite."""

import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agent import bundle, hybrid, llm, transport
from sandbox import factorial_stats

results = {}

with tempfile.TemporaryDirectory(prefix="nulllab_audit_replay_") as tmp:
    trace = Path(tmp) / "trace.jsonl"
    trace.write_text(
        json.dumps({"key": llm.prompt_key("system", "user", llm.MODEL), "reply": "ok"}) + "\n", encoding="utf-8"
    )
    llm.set_replay(trace)
    results["plain_replay"] = llm.live_complete_ex("system", "user")[0]
    transport.install()
    try:
        llm.live_complete_ex("system", "user")
        results["installed_transport_replay"] = "success"
    except RecursionError:
        results["installed_transport_replay"] = "RecursionError"
    finally:
        transport.uninstall()
        llm.set_replay(None)

results["mixed_verdict"] = hybrid._verdict_from({"sign": "mixed"})

# Overlap the scope lifetimes as concurrent callers can do, without threads/network.
original = llm.live_complete
def fake(*a, **k):
    return "{}"
llm.live_complete = fake
a, b = hybrid.Ledger(), hybrid.Ledger()
scope_a = hybrid.recording_llm(a, "planner", True)
scope_b = hybrid.recording_llm(b, "referee", True)
try:
    scope_a.__enter__()
    scope_b.__enter__()
    llm.live_complete("system", "user")
    both_recorded = (a.totals()["calls"], b.totals()["calls"])
    scope_a.__exit__(None, None, None)
    llm.live_complete("system", "user")
    second_call_not_recorded = b.totals()["calls"] == 1
    scope_b.__exit__(None, None, None)
    stale_proxy_restored = llm.live_complete is not fake
    results["overlapping_provider_scopes"] = {
        "one_call_counted_in_both_ledgers": both_recorded == (1, 1),
        "second_call_not_recorded": second_call_not_recorded,
        "stale_proxy_restored": stale_proxy_restored,
    }
finally:
    llm.live_complete = original

# Build exports only; never execute copied train.py or its modifications.
with tempfile.TemporaryDirectory(prefix="nulllab_audit_export_") as tmp:
    case = Path(tmp) / "leak_prescale"
    case.mkdir()
    for name in ("train.py", "excerpt.md", "data.csv"):
        shutil.copyfile(ROOT / "corpus" / "leak_prescale" / name, case / name)
    data = case / "data.csv"
    data.write_bytes(data.read_bytes() + b"\n")
    changed_hash = hashlib.sha256(data.read_bytes()).hexdigest()
    out = Path(tmp) / "bundle.zip"
    bundle.build_bundle(case, out, run=str(ROOT / "runs_rulefix" / "leak_prescale.json"))
    with zipfile.ZipFile(out) as z:
        manifest = json.loads(z.read("prereg/INPUT_HASHES.json"))
        results["changed_input_export"] = {
            "bundle_created_without_mismatch_rejection": True,
            "current_hash_described_as_audited": manifest["sha256"]["data.csv"] == changed_hash,
            "manifest_note": manifest["note"],
        }

# NumPy broadcasts one prediction across two labels unless shape is checked.
bad = {k: {"y": [0, 1], "p": [1]} for k in factorial_stats.CONFIGS}
stats = factorial_stats.factorial_stats(bad, n_boot=10)
results["invalid_vector_shape"] = {"accepted": True, "reported_n": stats["n"], "accuracy": stats["acc"]}
print(json.dumps(results, indent=2))
