"""Wrapper for tests/instance_start_driver.sh (WP4 gate).

Same pattern as tests/test_shell_source_safety.py wrapping
tests/shell_source_safety_driver.sh: the driver is a self-contained bash
script that drives the real scripts/start.sh end-to-end against stubbed
uvicorn/ollama/browser binaries; this file just runs it and asserts on the
OK/FAIL contract.

The driver needs a real venv with `arail` importable (for
arail.world_mount's slug-jail + seal verification, and for
tests/world_bundle_builder.py's fixture builder). This worktree ships no
.venv — ARAIL_TEST_VENV (or the sibling checkout's .venv, tried by the
driver itself) supplies one. See BUILD_LOG.md's WP4 section for the exact
environment note.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "instance_start_driver.sh"
_BASH = shutil.which("bash")

pytestmark = pytest.mark.skipif(_BASH is None, reason="bash required")


def _find_test_venv() -> str | None:
    candidates = [
        os.environ.get("ARAIL_TEST_VENV", ""),
        str(REPO_ROOT / ".venv"),
        str(REPO_ROOT.parent / ".venv"),  # sibling checkout (this worktree's case)
    ]
    for c in candidates:
        if c and Path(c, "bin", "python").exists():
            return c
    return None


def test_instance_start_driver_scenarios():
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
