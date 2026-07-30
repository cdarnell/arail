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
# T33: setup.sh's passphrase-masking predicate (F24). Mirrors the exact
# conditional in scripts/setup.sh's main() end-of-run banner rather than
# running the real (system-mutating) setup.sh end to end — same
# established pattern as tests/test_with_coder_flag.py's
# TestSetupShArgParsing, which mirrors setup.sh's argument-parsing loop
# for the identical reason.
# ---------------------------------------------------------------------------

_PASSPHRASE_MASK_SNIPPET = textwrap.dedent("""
    ARAIL_PASSWORD="super-secret-value"
    if [[ "${ARAIL_QUIET:-0}" == "1" ]] || [[ ! -t 1 ]]; then
        echo "MASKED"
    else
        echo "$ARAIL_PASSWORD"
    fi
""")


def _run_snippet(env: dict | None = None) -> subprocess.CompletedProcess:
    # subprocess.run's captured stdout is always a pipe, never a tty — this
    # is the real-world case that matters (T33: CI redirects setup's
    # stdout to a file). A real tty is not simulated here.
    base_env = {**os.environ}
    if env:
        base_env.update(env)
    return subprocess.run(
        ["bash", "-c", _PASSPHRASE_MASK_SNIPPET],
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
        assert "MASKED" in result.stdout
        assert "super-secret-value" not in result.stdout

    def test_masked_when_quiet_env_set(self):
        result = _run_snippet(env={"ARAIL_QUIET": "1"})
        assert "MASKED" in result.stdout
        assert "super-secret-value" not in result.stdout
