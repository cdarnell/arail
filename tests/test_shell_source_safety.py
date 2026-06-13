"""Shell-source safety for config files written by setup.sh / blueprint.sh.

`.env` and `lab.conf` are loaded via `set -a; source <file>` (arailctl,
scripts/start.sh, scripts/status.sh). Any value with whitespace or a shell
metacharacter must be quoted+escaped, or sourcing breaks ("command not found")
or executes embedded `$(...)`/backticks. The driver script exercises the real
helpers against hostile input.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

_BASH = shutil.which("bash")
_DRIVER = Path(__file__).parent / "shell_source_safety_driver.sh"


@pytest.mark.skipif(_BASH is None, reason="bash required")
def test_shell_sourced_configs_are_injection_safe():
    result = subprocess.run(
        [_BASH, str(_DRIVER)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (result.stdout + result.stderr)
    assert "OK:" in result.stdout
