"""BUG-2: bench output must not contain raw hostname or username.

The populated BENCH-v2.1.md is reviewed by operators and may be committed;
raw hostname or username from socket.gethostname() / getpass.getuser() must
never appear. The bench must instead emit a platform classification string
(e.g. 'darwin-arm64') derived from platform.system() + platform.machine().
"""

from __future__ import annotations

import getpass
import socket
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bench_ai_eng


def test_bench_output_has_no_hostname_leak(tmp_path):
    """The platform line in BENCH-v2.1.md must not contain socket.gethostname()."""
    real_hostname = socket.gethostname()
    out = tmp_path / "BENCH-v2.1.md"

    # Use --dry-run to produce output without real models
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/bench_ai_eng.py"),
         "--dry-run", "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"dry-run failed: {r.stderr}"
    content = out.read_text()
    assert real_hostname not in content, (
        f"Hostname '{real_hostname}' leaked into bench output. "
        "Replace socket.gethostname() with a platform classification."
    )


def test_bench_output_has_no_username_leak(tmp_path):
    """The bench output must not contain the operator's system username."""
    try:
        username = getpass.getuser()
    except Exception:
        pytest.skip("getpass.getuser() unavailable in this environment")

    out = tmp_path / "BENCH-v2.1.md"
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/bench_ai_eng.py"),
         "--dry-run", "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"dry-run failed: {r.stderr}"
    content = out.read_text()
    assert username not in content, (
        f"Username '{username}' leaked into bench output."
    )


def test_bench_host_field_is_platform_classification(tmp_path):
    """The Host field must be a platform classification like 'darwin-arm64',
    not a machine-specific string.
    """
    import platform, re
    expected = f"{platform.system().lower()}-{platform.machine().lower()}"

    out = tmp_path / "BENCH-v2.1.md"
    import subprocess
    r = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts/bench_ai_eng.py"),
         "--dry-run", "--out", str(out)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, f"dry-run failed: {r.stderr}"
    content = out.read_text()
    assert expected in content, (
        f"Expected platform classification '{expected}' in bench output but not found."
    )
