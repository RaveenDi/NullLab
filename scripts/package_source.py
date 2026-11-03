"""Package the current v2 product with an explicit public-data allow-list.

Historical real-domain cases, result generations, credentials and user cases never enter this archive.
"""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
files = set()
for name in ("README.md", "LICENSE", "requirements.txt", "requirements-dev.txt", "pyproject.toml", ".env.example", "nulllab_cli.py", "pipeline.py", "g4.py", "g5.py", "g6.py"):
    files.add(ROOT / name)
for directory in ("agent", "app", "sandbox", "baselines"):
    files.update(p for p in (ROOT / directory).rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix in (".py", ".html", ".css", ".js"))
# The package manifest declares this legacy Python package; include code, never
# its generated historical reports, recordings or assets.
files.update((ROOT / "report").glob("*.py"))
for name in ("secom", "secom_clean"):
    files.update(p for p in (ROOT / "examples" / name).iterdir() if p.is_file())
for name in ("README.md", "HISTORY.md", "FROZEN-FILES.md", "FROZEN-HASHES.json", "FROZEN-CHANGELOG.json", "ARCHITECTURE.md", "USAGE.md", "SECURITY.md", "DEPLOYMENT.md", "RESULTS-V2.md", "RELEASE-STATUS.md", "EVAL-V2-PILOT.md", "EVAL-V2-FOLLOWUP.md", "EVAL-V2-RELEASE.md", "FINAL-PRIORITIES.md", "RESEARCHER-ROADMAP.md", "RESEARCH-WORKSPACE-VALIDATION.md"):
    files.add(ROOT / "docs" / name)
for name in ("DECISIONS.md", "researcher-workflows.md", "methodology.md"):
    files.add(ROOT / "docs" / "reviews" / "research-room" / name)
files.add(ROOT / "docs" / "reviews" / "2026-11-04-responsive-layout.md")
files.add(ROOT / "docs" / "reviews" / "2026-11-04-shell-validation.md")
files.add(ROOT / "docs" / "reviews" / "2026-11-04-ci-evaluation-video.md")
files.add(ROOT / "docs" / "reviews" / "README.md")
for name in ("build_manufacturing.py", "package_demo.py", "package_source.py", "package_evaluation.py", "run_prospective_pilot.py", "regress_prospective_plans.py", "run_followup_pilot.py", "score_followup_pilot.py", "regress_followup_pilot.py", "run_release_evaluation.py", "run_release_confirmation.py"):
    files.add(ROOT / "scripts" / name)
for name in ("test_provider_v2.py", "test_app_v2.py", "test_engine_v2.py", "test_workspace_js.py", "test_guard_transform_v2.py", "test_study_v2.py", "test_workspace_api.py", "test_storage_v2.py"):
    files.add(ROOT / "tests" / name)
files.update(p for p in (ROOT / "submission").glob("*.md"))
files.add(ROOT / "submission" / "transcript.txt")
files.update(p for p in (ROOT / "eval" / "v2_cases").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
files.update(p for p in (ROOT / "eval" / "v2_followup_cases").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
files.update(p for p in (ROOT / "eval" / "v2_release").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
files.update(p for p in (ROOT / "eval" / "v2_confirmation").rglob("*") if p.is_file() and "__pycache__" not in p.parts)
for name in ("__init__.py", "V2-PILOT-NOTE.md", "V2-PROSPECTIVE-PROTOCOL.md", "v2_pilot_score.json", "v2_regression_score.json", "v2_truth.json", "v2_protocol_freeze.json"):
    files.add(ROOT / "eval" / name)
for name in ("v2_followup_score.json", "v2_followup_truth.json", "v2_followup_freeze.json", "v2_followup_preparation.json", "v2_followup_regression.json"):
    files.add(ROOT / "eval" / name)
manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
out = ROOT / "out" / "nulllab-v2-source.zip"
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(files):
        z.write(p, p.relative_to(ROOT))
    z.writestr("SOURCE-MANIFEST.json", json.dumps(manifest, indent=2))
    z.writestr("NOTICE", "SECOM: McCann and Johnston (2008), UCI Machine Learning Repository, DOI 10.24432/C54305, CC BY 4.0. https://archive.ics.uci.edu/dataset/179/secom\nConstructed evaluation variants and fixed-zero preprocessing are ours. Third-party libraries/services retain their terms.\n")
    z.writestr("tests/__init__.py", "")
    z.writestr("SOURCE-README.md", "# Current product source subset\n\nThis archive builds the supported v2 CLI and localhost workspace. It includes the public manufacturing examples and synthetic evaluation fixtures. Legacy Python modules remain for package compatibility; their historical datasets, generated reports and archived experiments are excluded. The full historical freeze suite described in the repository README requires the full local repository and is not part of this subset.\n\nInstall with `python -m pip install .`; install development dependencies with `python -m pip install -r requirements-dev.txt`. Check the included product tests with `python -m pytest tests/test_engine_v2.py tests/test_provider_v2.py tests/test_app_v2.py tests/test_workspace_js.py tests/test_study_v2.py tests/test_workspace_api.py -q`. The JavaScript check requires Node. `nulllab-v2-evaluation.zip` is a separate, input-bound evidence archive. See docs/RELEASE-STATUS.md for actual results and open gates.\n")
print(out)
