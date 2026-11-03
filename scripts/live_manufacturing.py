"""One explicitly bounded public-data Meta audit; no credential values are printed.

Use --env-file to select an existing credential file explicitly. Nothing is copied.
"""
import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.engine import run_audit
from agent.provider import Provider, ProviderConfig

ap = argparse.ArgumentParser(description=__doc__)
ap.add_argument("--env-file", default=".env")
ap.add_argument("--case", default="examples/secom")
ap.add_argument("--out", default="out/jobs/manufacturing-live")
ap.add_argument("--critic", action="store_true")
a = ap.parse_args()
config = replace(ProviderConfig.from_env(a.env_file), timeout_s=120, retries=0)
provider = Provider(config, ROOT / a.out, max_usd=1.0, max_calls=4)
result = run_audit(ROOT / a.case, ROOT / a.out, live=True, critic=a.critic, provider=provider)
print(json.dumps({k: result.get(k) for k in ("status", "verdict", "summary", "error")}, indent=2))
print(json.dumps({"model_attempts": provider.ledger()["calls"], "reserved_estimate_usd": provider.ledger()["est_usd"]}))
raise SystemExit(0 if result["status"] == "completed" else 2)
