"""Test-suite hooks.

* Marks tests that take over a minute as `slow` without editing the (possibly frozen) test files.
  CI runs `pytest -m "not slow and not live"`. Durations measured 2026-11-02 on a Windows laptop (full run, 341 tests, about 10 min).
* In CI only (`CI` env var set): a test that fails because a gitignored `real/*/data.csv` is absent from a fresh clone
  is reported as skipped, not failed. Locally the data exists and nothing is skipped, so a real failure is never hidden.
"""

import os
from pathlib import Path

import pytest

SLOW = {
    "tests/test_nulllab.py::test_end_to_end_new_cases_agree",  # 70-95 s
}


# Tests that need the gitignored real/*/data.csv files but fail with a crash instead of FileNotFoundError when they are absent.
NEEDS_REAL_DATA = {
    "tests/test_ehg_runner.py::test_run_stage_mocked",
    "tests/test_g9_runner.py::test_run_stage_mocked_and_score",
    "tests/test_guard_g9.py::test_ehg_known_correct_fixes_accepted_and_overlap_measured",
    "tests/test_guard_g9.py::test_esl_selection_moved_into_fold_accepted",
    "tests/test_guard_g9.py::test_civilwar_temporal_split_accepted_clean_one_rejected_as_noop",
}
_REAL = Path(__file__).resolve().parent.parent / "real"


def _real_data_missing() -> bool:
    return any(d.is_dir() and (d / "train.py").exists() and not (d / "data.csv").exists() for d in _REAL.glob("*"))


def pytest_collection_modifyitems(config, items):
    missing = _real_data_missing()
    for item in items:
        nid = item.nodeid.replace("\\", "/")
        if nid in SLOW:
            item.add_marker(pytest.mark.slow)
        if missing and nid in NEEDS_REAL_DATA:
            item.add_marker(pytest.mark.skip(reason="gitignored real/*/data.csv absent (fresh clone)"))


def _is_absent_case_data(exc: BaseException) -> bool:
    if not isinstance(exc, FileNotFoundError):
        return False
    name = str(getattr(exc, "filename", "") or exc).replace("\\", "/")
    return "/real/" in name and name.endswith("data.csv")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if (
        os.environ.get("CI")
        and call.when in ("setup", "call")
        and rep.failed
        and call.excinfo is not None
        and _is_absent_case_data(call.excinfo.value)
    ):
        rep.outcome = "skipped"
        rep.longrepr = (
            str(item.path),
            item.location[1],
            "Skipped: gitignored case data absent in a fresh clone (CI only)",
        )
