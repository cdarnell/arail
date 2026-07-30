"""Wrapper for tests/cli/root_start_driver.sh (WP2 gates: T13-T17, F1,
F29, F30, F31).

Same pattern as tests/test_instance_start.py wrapping
tests/instance_start_driver.sh. Needs a real venv with `arail` importable
(the driver's serving stub uvicorn binds real sockets and the fake repo's
python must be able to `import arail`); self-skips (driver prints "SKIP:")
when none is found.

This driver is slower than the others (~70s) — it deliberately exercises
several real readiness-gate timeouts (10s degrade caps, one 30s daemon-mode
cap) rather than mocking the polling loops, so the timing behavior under
test is real, not simulated.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "cli" / "root_start_driver.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _find_test_venv() -> str | None:
    candidates = [
        os.environ.get("ARAIL_TEST_VENV", ""),
        str(REPO_ROOT / ".venv"),
        str(REPO_ROOT.parent / ".venv"),
    ]
    for c in candidates:
        if c and Path(c, "bin", "python").exists():
            return c
    return None


def test_root_start_driver_scenarios():
    venv = _find_test_venv()
    if venv is None:
        pytest.skip("no usable .venv found for ARAIL_TEST_VENV — cannot import arail.*")

    env = dict(os.environ)
    env["ARAIL_TEST_VENV"] = venv
    result = subprocess.run(
        [_BASH, str(DRIVER)],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout, result.stdout + result.stderr
