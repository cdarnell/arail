"""Wrapper for tests/cli/status_driver.sh (WP5 gates: T3, T8, T10-T12,
T34, F2, F18, F20 — sprints/2026-07-29-elite-cli/ARCHITECTURE.md §7/§12).

Same pattern as tests/test_cli_root_start.py wrapping root_start_driver.sh.
Needs a real venv with `arail` importable; self-skips (driver prints
"SKIP:") when none is found.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "cli" / "status_driver.sh"
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


def test_status_driver_scenarios():
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
