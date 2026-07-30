"""Wrapper for tests/cli/color_driver.sh (WP1 gate: F25).

Same pattern as tests/test_shell_source_safety.py wrapping
tests/shell_source_safety_driver.sh: the driver is a self-contained bash
script; this file just runs it and asserts on the OK/FAIL contract.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "cli" / "color_driver.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def test_color_driver_scenarios():
    result = subprocess.run(
        [_BASH, str(DRIVER)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout, result.stdout + result.stderr
