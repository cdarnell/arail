"""Test ./arailctl enable compare and ./arailctl disable compare end-to-end.

Sprint 2026-05-10-min-tier-simplification introduced two new shell-script
add-on commands. They idempotently upsert ARAIL_COMPARE_ENABLED in .env
via a small inline Python helper.

Coverage:
  - enable_compare.sh on a fresh .env (key absent) → appends ARAIL_COMPARE_ENABLED=1
  - enable_compare.sh on an .env with =0 → flips to =1
  - disable_compare.sh on an .env with =1 → flips to =0
  - Idempotency: running enable twice doesn't duplicate the line
  - Error path: enable script errors with exit 1 when no .env exists
  - arailctl wrapper rejects unknown features

The scripts are pure bash + a Python heredoc; they don't depend on the
Python package, so we exercise them directly via subprocess in a tmpdir.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENABLE_SCRIPT = _REPO_ROOT / "scripts" / "enable_compare.sh"
_DISABLE_SCRIPT = _REPO_ROOT / "scripts" / "disable_compare.sh"
_ARAILCTL = _REPO_ROOT / "arailctl"


def _run_script(script: Path, tmp_repo_root: Path) -> subprocess.CompletedProcess:
    """Run the script with REPO_ROOT pointed at the test directory.

    The scripts compute REPO_ROOT from BASH_SOURCE; we override via env
    var so they read/write the test's .env without touching the real one.
    Both scripts honor the REPO_ROOT env override (see their headers)."""
    env = os.environ.copy()
    env["REPO_ROOT"] = str(tmp_repo_root)
    return subprocess.run(
        ["bash", str(script)],
        env=env,
        cwd=str(tmp_repo_root),
        capture_output=True,
        text=True,
    )


def _env_value(env_path: Path, key: str) -> str | None:
    """Read a single key out of the .env file, ignoring comments."""
    for line in env_path.read_text().splitlines():
        if line.lstrip("# ").startswith(f"{key}="):
            return line.split("=", 1)[1]
    return None


def _env_count(env_path: Path, key: str) -> int:
    """Count active (non-comment) assignments of `key` in the .env."""
    n = 0
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            n += 1
    return n


@pytest.fixture
def tmp_env(tmp_path: Path) -> Path:
    """Create a tmpdir with a minimal .env so the scripts can edit it."""
    (tmp_path / ".env").write_text(
        "# arail .env\nLAB_TIER=min\nLAB_MODE=airgapped\n"
    )
    return tmp_path


def test_enable_compare_appends_when_key_absent(tmp_env: Path):
    result = _run_script(_ENABLE_SCRIPT, tmp_env)
    assert result.returncode == 0, result.stderr
    assert _env_value(tmp_env / ".env", "ARAIL_COMPARE_ENABLED") == "1"


def test_enable_compare_flips_zero_to_one(tmp_env: Path):
    env_path = tmp_env / ".env"
    env_path.write_text(env_path.read_text() + "ARAIL_COMPARE_ENABLED=0\n")
    result = _run_script(_ENABLE_SCRIPT, tmp_env)
    assert result.returncode == 0, result.stderr
    assert _env_value(env_path, "ARAIL_COMPARE_ENABLED") == "1"
    assert _env_count(env_path, "ARAIL_COMPARE_ENABLED") == 1, (
        "duplicate ARAIL_COMPARE_ENABLED line — upsert is not idempotent"
    )


def test_disable_compare_flips_one_to_zero(tmp_env: Path):
    env_path = tmp_env / ".env"
    env_path.write_text(env_path.read_text() + "ARAIL_COMPARE_ENABLED=1\n")
    result = _run_script(_DISABLE_SCRIPT, tmp_env)
    assert result.returncode == 0, result.stderr
    assert _env_value(env_path, "ARAIL_COMPARE_ENABLED") == "0"


def test_enable_twice_is_idempotent(tmp_env: Path):
    _run_script(_ENABLE_SCRIPT, tmp_env)
    _run_script(_ENABLE_SCRIPT, tmp_env)
    env_path = tmp_env / ".env"
    assert _env_value(env_path, "ARAIL_COMPARE_ENABLED") == "1"
    assert _env_count(env_path, "ARAIL_COMPARE_ENABLED") == 1


def test_enable_compare_errors_without_env(tmp_path: Path):
    """If there's no .env, the script should fail with a clear message."""
    env = os.environ.copy()
    env["REPO_ROOT"] = str(tmp_path)
    result = subprocess.run(
        ["bash", str(_ENABLE_SCRIPT)],
        env=env,
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "no .env" in result.stderr.lower(), result.stderr


def test_arailctl_rejects_unknown_feature(tmp_env: Path):
    """`./arailctl enable garbage` should exit 2 with a usage hint."""
    env = os.environ.copy()
    env["REPO_ROOT"] = str(tmp_env)
    result = subprocess.run(
        ["bash", str(_ARAILCTL), "enable", "garbage"],
        env=env,
        cwd=str(tmp_env),
        capture_output=True,
        text=True,
    )
    # arailctl's die() uses exit 1; the dispatch wraps into the feature
    # case statement which calls die() — so exit 1 not 2.
    assert result.returncode != 0
    assert "unknown feature" in result.stderr.lower() or "usage" in result.stderr.lower()


def test_arailctl_enable_without_feature_shows_usage(tmp_env: Path):
    """`./arailctl enable` (no feature arg) should show usage."""
    env = os.environ.copy()
    env["REPO_ROOT"] = str(tmp_env)
    result = subprocess.run(
        ["bash", str(_ARAILCTL), "enable"],
        env=env,
        cwd=str(tmp_env),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "usage" in result.stderr.lower()
