"""Contamination probes for the disguised EHG cases (3 calls per case, muse-spark-1.3-contributor). Usage: python runs_g8_cases/probe.py <case> <tag>
Logs go to runs_g8_cases/ (own call log, traces); hard cap 8 calls and USD 0.40 for this builder."""
import json, os, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs_g8_cases"
os.environ["NULLLAB_PHASE"] = "g8"
os.environ["NULLLAB_G8_LOG"] = str(OUT / "live_calls_g8cases.jsonl")
os.environ["NULLLAB_TRACES"] = str(OUT / "traces.jsonl")
sys.path.insert(0, str(ROOT))
from agent import llm  # noqa: E402
MODEL = "muse-spark-1.3-contributor"
CAP_CALLS, CAP_USD, EST = 8, 0.40, 0.03
SRC_WORDS = ("vandewiele", "physionet", "tpehg", "ehg", "fele", "oversampling-before", "arxiv")
DOM_WORDS = ("preterm", "premature", "pregnan", "birth", "obstet", "uterin", "electrohyster", "ehg", "emg", "labor", "labour", "gestation",
             "maternal", "fetal", "foetal")
def used():
    p = Path(os.environ["NULLLAB_G8_LOG"]); return sum(1 for _ in p.open()) if p.exists() else 0
def view(case, with_results=True):
    t = (ROOT / "real" / case / "train.py").read_text(encoding="utf-8"); e = (ROOT / "real" / case / "excerpt.md").read_text(encoding="utf-8")
    if not with_results: e = e.split("## Results")[0]
    return "train.py:\n" + t + "\n\nexcerpt.md:\n" + e
def nums(txt):
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", txt)]
def main(case, tag):
    out = {"case": case, "tag": tag, "model": MODEL, "calls_used_before": used()}
    if used() + 3 > CAP_CALLS or (used() + 3) * EST > CAP_USD: raise SystemExit("probe budget would be exceeded")
    sys_ = "You are a careful research assistant. Answer briefly."
    p1 = llm.live_complete(sys_, "The following code and methods excerpt come from a real, published study. If you recognise the study or its data "
                           "source, name it (authors/year/dataset). Otherwise reply exactly UNKNOWN.\n\n" + view(case), est_usd=EST, tag="g8c_p1", role="probe", model=MODEL, temperature=0)
    p2 = llm.live_complete(sys_, "Which real-world domain do the columns f01..f12 most likely come from, and what do they measure? Give your single best guess "
                           "in one sentence.\n\n" + view(case), est_usd=EST, tag="g8c_p2", role="probe", model=MODEL, temperature=0)
    p3 = llm.live_complete(sys_, "This pipeline reproduces a published study. What headline ROC-AUC did that study report for it? Give one number, or UNKNOWN "
                           "if you do not recognise the study.\n\n" + view(case, with_results=False), est_usd=EST, tag="g8c_p3", role="probe", model=MODEL, temperature=0)
    low1, low2 = p1.lower(), p2.lower()
    hit1 = [w for w in SRC_WORDS if w in low1]; hit2 = [w for w in DOM_WORDS if w in low2]
    ns = nums(p3) if "unknown" not in p3.lower()[:40] else []
    hit3 = [n for n in ns if 0.864 <= n <= 1.056 or 86.4 <= n <= 105.6]
    out.update({"P1_source": p1[:400], "P2_domain": p2[:400], "P3_headline": p3[:400], "source_hits": hit1, "domain_hits": hit2, "headline_numbers_within_10pct": hit3,
                "P1_pass": ("UNKNOWN" in p1.upper()) and not hit1, "P2_pass": not hit2, "P3_pass": not hit3})
    out["CLEAN"] = out["P1_pass"] and out["P2_pass"] and out["P3_pass"]
    out["calls_used_after"] = used()
    (OUT / f"probe_{case}_{tag}.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out, indent=1))
if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
