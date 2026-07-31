"""Wrapper for tests/cli/verbs_driver.sh (WP1 gates: T6, T7 partial, T9,
F33), plus a T33 check on setup.sh's passphrase-masking predicate.

The driver needs a real venv with `arail` importable for the `doctor`
scenarios (T9) — same ARAIL_TEST_VENV / sibling-checkout discovery as
tests/test_instance_start.py; it self-skips those specific scenarios
(printing "SKIP:") when none is found, same as the driver-internal skip
tests/instance_start_driver.sh uses, so this wrapper does not need its own
separate skip for that half.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DRIVER = REPO_ROOT / "tests" / "cli" / "verbs_driver.sh"
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


def test_verbs_driver_scenarios():
    env = dict(os.environ)
    venv = _find_test_venv()
    if venv is not None:
        env["ARAIL_TEST_VENV"] = venv
    result = subprocess.run(
        [_BASH, str(DRIVER)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK:" in result.stdout, result.stdout + result.stderr


# ---------------------------------------------------------------------------
# T33: setup.sh's passphrase-masking predicate (F24).
#
# REVIEW.md m6: this used to be a hand-RETYPED copy of setup.sh's
# conditional — deleting the real mask in setup.sh would not have failed
# this test, since nothing here ever reads setup.sh. Extracted verbatim
# instead (the SAME `_run_start_guard`/`inst_load_setup_functions`
# extraction-pins-the-literal-block discipline this repo already uses
# elsewhere, e.g. tests/test_daemon_predicate.py), never running the real
# (system-mutating) setup.sh end to end — same reasoning as
# tests/test_with_coder_flag.py's TestSetupShArgParsing, which mirrors
# setup.sh's argument-parsing loop for the identical reason.
# ---------------------------------------------------------------------------

SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"


def _extract_passphrase_mask_conditional() -> str:
    src = SETUP_SH.read_text(encoding="utf-8")
    marker_start = 'if [[ "${ARAIL_QUIET:-0}" == "1" ]] || [[ ! -t 1 ]]; then'
    marker_end = "fi"
    start_idx = src.index(marker_start)
    end_idx = src.index(marker_end, start_idx) + len(marker_end)
    return src[start_idx:end_idx]


_PASSPHRASE_MASK_CONDITIONAL = _extract_passphrase_mask_conditional()


def _run_snippet(env: dict | None = None) -> subprocess.CompletedProcess:
    # subprocess.run's captured stdout is always a pipe, never a tty — this
    # is the real-world case that matters (T33: CI redirects setup's
    # stdout to a file). A real tty is not simulated here.
    script = textwrap.dedent(f"""
        BOLD=""; RESET=""
        ARAIL_PASSWORD="super-secret-value"
        {_PASSPHRASE_MASK_CONDITIONAL}
    """)
    base_env = {**os.environ}
    if env:
        base_env.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=5,
        env=base_env,
    )


class TestPassphraseMasking:
    def test_masked_when_stdout_piped_default(self):
        """Default (no --quiet, no ARAIL_QUIET) but stdout is a pipe (the
        subprocess.run capture below) -> masked. This is the real-world CI
        case (T33)."""
        result = _run_snippet()
        assert "********" in result.stdout
        assert "super-secret-value" not in result.stdout

    def test_masked_when_quiet_env_set(self):
        result = _run_snippet(env={"ARAIL_QUIET": "1"})
        assert "********" in result.stdout
        assert "super-secret-value" not in result.stdout
