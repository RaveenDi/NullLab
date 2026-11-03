"""Package public synthetic evaluation evidence without credentials or private jobs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent.bundle import scan_secrets
from agent.evidence import verify


def main():
    files = set()
    for folder in ("prospective-offline-results", "prospective-live-results", "prospective-regression-results", "followup-v2-results", "followup-v2-regression"):
        base = ROOT / "out" / folder
        results = sorted([*base.glob("*/result.json"), *base.glob("*/*/result.json")])
        for result_file in results:
            result = json.loads(result_file.read_text(encoding="utf-8"))
            if result.get("evidence"):
                verify(result_file.parent / "inputs", result)
            for name in ("result.json", "provider-ledger.json", "provider-traces.jsonl"):
                p = result_file.parent / name
                if p.is_file():
                    files.add(p)
            inputs = result_file.parent / "inputs"
            if inputs.is_dir():
                files.update(p for p in inputs.iterdir() if p.is_file())
        for name in ("schedule.json", "totals.json", "instrument.json"):
            p = base / name
            if p.is_file():
                files.add(p)
    for cohort in ("v2_cases", "v2_followup_cases"):
        files.update(p for p in (ROOT / "eval" / cohort).rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for snapshot, manifest in (("out/followup-v2-instrument", "eval/v2_followup_freeze.json"), ("out/followup-v2-regression/instrument", "out/followup-v2-regression/instrument.json")):
        mapping = json.loads((ROOT / manifest).read_text())["files"]
        for name, expected in mapping.items():
            p = ROOT / snapshot / name
            if hashlib.sha256(p.read_bytes()).hexdigest() != expected:
                raise ValueError(f"Instrument snapshot mismatch: {name}")
            files.add(p)
    for name in ("v2_pilot_score.json", "v2_regression_score.json", "v2_truth.json", "v2_protocol_freeze.json", "V2-PILOT-NOTE.md", "V2-PROSPECTIVE-PROTOCOL.md"):
        files.add(ROOT / "eval" / name)
    files.add(ROOT / "docs" / "EVAL-V2-PILOT.md")
    files.add(ROOT / "docs" / "EVAL-V2-FOLLOWUP.md")
    files.add(ROOT / "docs" / "EVAL-V2-RELEASE.md")
    files.update(p for p in (ROOT / "eval" / "v2_release").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    files.update(p for p in (ROOT / "eval" / "v2_confirmation").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
    for name in ("v2_followup_score.json", "v2_followup_truth.json", "v2_followup_freeze.json", "v2_followup_preparation.json", "v2_followup_regression.json"):
        files.add(ROOT / "eval" / name)
    payloads = {}
    for p in sorted(files):
        data = p.read_bytes()
        scanned = data.decode("utf-8")
        if p.suffix in (".py", ".txt") and (any(part in ("followup-v2-instrument", "instrument") for part in p.parts) or p.name == "preparation-runner.py.txt"):
            # Source legitimately names the environment variable. Reject literal
            # credentials, then scan other token patterns without that name.
            if re.search(r'''MODEL_API_KEY\s*=\s*["'][A-Za-z0-9._/-]{16,}["']''', scanned):
                raise ValueError(f"Refusing hardcoded credential: {p.relative_to(ROOT)}")
            scanned = scanned.replace("MODEL_API_KEY", "")
        if scan_secrets(scanned):
            raise ValueError(f"Refusing credential-like evidence: {p.relative_to(ROOT)}")
        payloads[p.relative_to(ROOT).as_posix()] = data
    manifest = {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()}
    output = ROOT / "out" / "nulllab-v2-evaluation.zip"
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr(name, data)
        archive.writestr("EVIDENCE-MANIFEST.json", json.dumps(manifest, indent=2))
        archive.writestr("README.txt", "Internal synthetic evaluation only. Original frozen pilots and post-fix development regressions are separate. Follow-up original and repaired instrument sources are captured. Stored-response fixtures are not valid model replay under changed prompts. No external users or empirical clean specificity are established. Case source is executable: inspect before running. No credentials, raw private data or unrelated jobs are included.\n")
    print(f"{output}: {len(payloads)} public evidence files")


if __name__ == "__main__":
    main()
