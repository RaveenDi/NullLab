"""Input-bound, readable memos for outcomes without a measured control."""

from __future__ import annotations

import html
import json
from pathlib import Path
import uuid
import zipfile

from agent import evidence
from agent.bundle import scan_secrets


def _text(value):
    return html.escape(str(value), quote=False).replace("|", "\\|")


def _items(value):
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def render(result):
    lines = ["# NullLab research assessment", "", f"Case: {_text(result.get('case', 'unknown'))}", f"Outcome: **{_text(result.get('verdict', 'INCONCLUSIVE'))}**", "", "**No counterfactual was measured. This memo is not empirical clearance of the evaluation.**", ""]
    if result.get("error"):
        lines.extend(["Reported error: " + _text(result["error"]), ""])
    declaration = result.get("study")
    if declaration:
        lines.extend(["## Author study declarations", "", "These are author-provided statements, not independently verified facts.", "", "```json", json.dumps(declaration, ensure_ascii=False, indent=2), "```", ""])
    review = result.get("study_review") or {}
    facts = review.get("facts") or {}
    if facts:
        lines.extend(["## Dataset and column roles", "", "```json", json.dumps({"predictors": review.get("predictor_columns", []), "excluded": review.get("excluded_columns", []), "aggregate_facts": facts}, indent=2, ensure_ascii=False), "```", ""])
    baseline = result.get("baseline")
    if baseline:
        lines.extend(["## Executed baseline only", "", f"Metric: {_text(baseline.get('metric'))}; average score: {_text(baseline.get('score'))}.", "No control comparison follows from this baseline score.", "", "| Seed | Score | Scored rows |", "|---|---|---|"])
        for seed, score in (baseline.get("per_seed_scores") or {}).items():
            lines.append(f"| {_text(seed)} | {_text(score)} | {_text((baseline.get('n_scored') or {}).get(seed, 'not recorded'))} |")
        lines.extend(["", _text(baseline.get("reference_note", "")), ""])
    else:
        lines.extend(["## Execution", "", "No baseline was executed. Resolve the recorded questions or scope limitations before starting a new audit.", ""])
    questions = list(dict.fromkeys(_items(result.get("questions")) + _items(review.get("questions"))))
    gaps = list(dict.fromkeys(_items(result.get("scope_gaps")) + _items(review.get("scope_gaps"))))
    for heading, items in (("Questions to answer", questions), ("Scope limitations", gaps)):
        if items:
            lines.extend(["## " + heading, ""] + ["- " + _text(item) for item in items] + [""])
    for label, field in (("Planner assessment", "plan"), ("Independent methodology assessment", "independent_review"), ("Final critique", "critic")):
        record = result.get(field)
        if record:
            if not isinstance(record, dict):
                lines.extend(["## " + label, "", "Malformed assessment response; inspect the recorded error. No conclusion is inferred from it.", ""])
                continue
            lines.extend(["## " + label, "", _text(record.get("reason", "Recorded opinion, not an experimental finding")), ""])
            lines.extend("- " + _text(item) for item in _items(record.get("concerns")))
            lines.append("")
    lines.extend(["## Limits and provenance", ""] + ["- " + _text(item) for item in result.get("limitations", [])] + ["", "Input manifest: `" + str(result["evidence"]["manifest_sha256"]) + "`", "", "Resolve questions by creating a new input-bound revision and running it. Earlier outcomes are retained; author answers do not upgrade an earlier result.", ""])
    return "\n".join(lines)


def export(result_path, expected_schema):
    path = Path(result_path).resolve()
    result = json.loads(path.read_text(encoding="utf-8"))
    if result.get("schema") != expected_schema or result.get("status") not in ("completed", "inconclusive", "failed", "cancelled"):
        raise ValueError("Only terminal v2 assessments can be exported")
    if result.get("record") or result.get("summary"):
        raise ValueError("A measured result requires its verified control bundle")
    snapshot = path.parent / "inputs"
    evidence.verify(snapshot, result)
    files = [snapshot / name for name in evidence.INPUTS if result["evidence"]["inputs"].get(name) is not None]
    memo = render(result)
    for p in [path, *files]:
        if p.is_symlink() or scan_secrets(p.read_text(encoding="utf-8")):
            raise ValueError("Assessment contains a symbolic link or credential-like text; no export was created")
    if scan_secrets(memo):
        raise ValueError("Assessment text contains credential-like content")
    output = path.parent / ("assessment-" + uuid.uuid4().hex + ".zip")
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(path, "result.json")
        for p in files:
            archive.write(p, "inputs/" + p.name)
        archive.writestr("assessment.md", memo)
        archive.writestr("README.md", "# NullLab unmeasured assessment\n\nNo controlled effect was measured; this is not scientific clearance. Read assessment.md and result.json for baseline execution, author declarations, open questions and limitations. Only manifest-bound inputs are included. Source code is executable: inspect it before running. It may contain private data; review before sharing. A fresh local audit requires an installed NullLab environment: python -m agent.engine inputs --out NEW_DIRECTORY. That is a new run under the installed instrument, not an exact model replay or an automatic resolution.\n")
        archive.writestr("requirements.txt", "\n".join(f"{name}=={version}" for name, version in result["evidence"]["environment"].items() if name != "python" and version) + "\n")
    return output
