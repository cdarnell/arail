"""Wrapper for tests/cli/picker_driver.sh — the World picker at
`./arailctl start`, its memory of the last launched lab, `--pick`,
`--yes`, and the `switch` verb.

Same pattern as tests/test_cli_root_start.py wrapping
tests/cli/root_start_driver.sh. Needs a real venv with `arail` importable
(the driver builds seal-valid World bundles and its stub uvicorn binds
real sockets); self-skips (driver prints "SKIP:") when none is found.

Slower than most drivers (~4 min): the interactive scenarios run start.sh
under a REAL pty, because the picker is gated on `[[ -t 0 ]]` and a pipe
would silently take the non-interactive branch instead — so the behavior
under test is the real one, not a simulation of it. Two scenarios also
run the root lab's full readiness phase to completion, since that is the
only place the last-target memory is actually written.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "cli" / "picker_driver.sh"
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


def test_picker_driver_scenarios():
    venv = _find_test_venv()
    if venv is None:
        pytest.skip("no usable .venv found for ARAIL_TEST_VENV — cannot import arail.*")

    env = dict(os.environ)
    env["ARAIL_TEST_VENV"] = venv
    result = subprocess.run(
        [_BASH, str(DRIVER)],
        capture_output=True,
        text=True,
        timeout=600,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout, result.stdout + result.stderr
