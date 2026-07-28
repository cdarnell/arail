"""pytest wrapper for tests/instance_qa_driver.sh.

Sprint: sprints/2026-07-28-concurrent-worlds/ (QA pass).

Same shape as tests/test_instance_start.py: the driver owns the scenarios,
this file makes them visible to `pytest tests/` and to CI.

The second test is the load-bearing one — it asserts the exact set of
CURRENTLY-OPEN defect ids the driver expects to observe. If a builder fixes
one of them, the driver's own `fail` branch fires (it detects the fixed
behaviour explicitly) and this file goes red until the scenario is retired.
A bug therefore cannot be fixed *or* silently re-introduced without a test
change.

QA-fix pass (sprints/2026-07-28-concurrent-worlds/BUILD_LOG.md): QA-1, QA-2,
QA-3, and QA-5 are now fixed — the driver's scenarios were updated to assert
the CORRECT behaviour and no longer print any XFAIL line.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "instance_qa_driver.sh"
_BASH = shutil.which("bash")

# Defect ids the driver is expected to observe today. Each was filed in
# sprints/2026-07-28-concurrent-worlds/TEST_REPORT.md; QA-1/2/3/5 are fixed
# (see BUILD_LOG.md's "QA-fix pass"), so this set is now empty.
EXPECTED_OPEN_DEFECTS: set[str] = set()

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _run_driver() -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("ARAIL_TEST_VENV", str(REPO_ROOT / ".venv"))
    return subprocess.run(
        [_BASH, str(DRIVER)],
        capture_output=True, text=True, timeout=900, env=env,
        cwd=str(REPO_ROOT),
    )


@pytest.fixture(scope="module")
def driver_result() -> subprocess.CompletedProcess:
    return _run_driver()


def test_qa_start_driver_scenarios_pass(driver_result) -> None:
    out = driver_result.stdout + driver_result.stderr
    if out.strip().startswith("SKIP:"):
        pytest.skip(out.strip())
    assert driver_result.returncode == 0, out
    assert "OK:" in out, out


def test_the_open_defect_set_has_not_changed(driver_result) -> None:
    """Guards both directions: a fix that lands without retiring its scenario,
    and a regression that adds a new one.
    """
    out = driver_result.stdout + driver_result.stderr
    if out.strip().startswith("SKIP:"):
        pytest.skip(out.strip())
    observed = {
        line.split(":", 1)[1].strip().split()[0]
        for line in out.splitlines()
        if line.startswith("XFAIL:")
    }
    assert observed == EXPECTED_OPEN_DEFECTS, (
        "the set of open Concurrent-Worlds defects changed.\n"
        f"  expected: {sorted(EXPECTED_OPEN_DEFECTS)}\n"
        f"  observed: {sorted(observed)}\n"
        "If a defect was FIXED, delete its scenario branch in "
        "tests/instance_qa_driver.sh and remove its id here. If a NEW one "
        "appeared, file it in TEST_REPORT.md first."
    )
