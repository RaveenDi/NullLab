"""agent/cached_exec.py: the cached + parallel run must equal the uncached sandbox run (offline, $0, small corpus case)."""
import json
from pathlib import Path

import pytest

from agent import cached_exec as cx
from sandbox import executor

ROOT = Path(__file__).resolve().parent.parent
G5_R1 = ROOT / "runs_g5" / "r1.json"
CASE = ROOT / "corpus" / "clean_wine_correct"      # 178 rows, logistic regression: a few seconds


def _patches():
    rec = json.loads(G5_R1.read_text(encoding="utf-8"))["loop"]["clean_wine_correct"]
    return {k: rec["sources"][k] for k in ("fix_A", "fix_B", "fix_both")}


pytestmark = pytest.mark.skipif(not G5_R1.exists(), reason="runs_g5/r1.json not present")


def test_cached_output_is_identical_to_uncached(tmp_path):
    patches = _patches()
    base = executor.run_factorial(CASE, patches, seeds=(42, 43), timeout=300)
    assert base["status"] == "ok"
    first = cx.run_factorial_cached(CASE, patches, seeds=(42, 43), timeout=300, cache_dir=tmp_path / "c", workers=3)
    assert first["status"] == "ok" and first["cached_exec"]["orig_cache_hits"] == [] and first["cached_exec"]["orig_computed"] == [42, 43]
    assert cx.canonical(first["result"]) == cx.canonical(base["result"])          # byte-identical, wall-clock field excluded
    assert set(first["result"]) == set(base["result"]) == {"seeds", "metric", "elapsed_s"}
    # second call: orig comes from the cache, the answer is still byte-identical
    second = cx.run_factorial_cached(CASE, patches, seeds=(42, 43), timeout=300, cache_dir=tmp_path / "c", workers=2)
    assert second["cached_exec"]["orig_cache_hits"] == [42, 43] and second["cached_exec"]["orig_computed"] == []
    assert second["cached_exec"]["jobs_run"] == 6                                   # 2 seeds x 3 configs, no orig
    assert cx.canonical(second["result"]) == cx.canonical(base["result"])
    # statistics computed from it agree too
    from sandbox import factorial_stats
    assert json.dumps(factorial_stats.all_seeds(second["result"], n_boot=50), sort_keys=True) == \
        json.dumps(factorial_stats.all_seeds(base["result"], n_boot=50), sort_keys=True)


def test_crash_is_reported_like_the_executor(tmp_path):
    patches = _patches()
    patches["fix_B"] = patches["fix_B"] + "\ndef controlled_eval(df, seed):\n    return df.to_numpy(kind='stable'), None\n"
    ex = cx.run_factorial_cached(CASE, patches, seeds=(42,), timeout=300, cache_dir=tmp_path / "c")
    assert ex["status"] == "error" and "TypeError" in ex["stderr"] and "fix_B.py" in ex["stderr"]


def test_cache_key_depends_on_everything_it_should():
    v = {"python": "3", "numpy": "1"}
    k = cx.cache_key("a = 1", b"d", 42, v, "r")
    assert k == cx.cache_key("a = 1", b"d", 42, v, "r")
    assert len({k, cx.cache_key("a = 2", b"d", 42, v, "r"), cx.cache_key("a = 1", b"e", 42, v, "r"), cx.cache_key("a = 1", b"d", 43, v, "r"),
                cx.cache_key("a = 1", b"d", 42, {"python": "3", "numpy": "2"}, "r"), cx.cache_key("a = 1", b"d", 42, v, "r2")}) == 6


def test_global_randomness_detection_and_fallback(tmp_path):
    assert cx.uses_global_randomness("import numpy as np\nx = np.random.rand(3)\n")
    assert cx.uses_global_randomness("import random\nrandom.shuffle(a)\n")
    assert not cx.uses_global_randomness("import numpy as np\nrng = np.random.default_rng(1)\nx = rng.random(3)\n")
    patches = _patches()
    patches["fix_A"] = patches["fix_A"] + "\nimport numpy as _n\n_n.random.seed(0)\n" if False else patches["fix_A"].replace(
        "import numpy as np", "import numpy as np\nnp.random.seed(1)", 1)
    ex = cx.run_factorial_cached(CASE, patches, seeds=(42,), timeout=300, cache_dir=tmp_path / "c")
    assert "fallback" in ex["cached_exec"] and ex["status"] == "ok"


def test_install_uninstall_roundtrip():
    orig = executor.run_factorial
    cx.install()
    assert executor.run_factorial is cx.run_factorial_cached
    cx.install()                                    # idempotent
    cx.uninstall()
    assert executor.run_factorial is orig
