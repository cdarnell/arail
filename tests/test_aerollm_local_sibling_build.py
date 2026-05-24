"""AeroLLM is built from the LOCAL sibling repo — not pip, not maturin develop.

Guards the install contract: setup.sh delegates to scripts/build-aerollm.sh,
the helper fails loudly with clone instructions when the sibling repo is
missing, and no `maturin develop` command is ever executed (it breaks the
Metal kernel compile on macOS arm64).
"""
from __future__ import annotations

import os
import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[1]
BUILD = REPO / "scripts" / "build-aerollm.sh"
SETUP = REPO / "scripts" / "setup.sh"


def _noncomment(text: str) -> str:
    """Drop comment-only lines so we test executed code, not cautionary notes."""
    return "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))


def test_helper_exists_and_is_executable():
    assert BUILD.exists()
    assert os.access(BUILD, os.X_OK)


def test_status_runs_without_sibling_repo(tmp_path):
    r = subprocess.run(
        ["bash", str(BUILD), "status"],
        capture_output=True, text=True,
        env={**os.environ, "ARAIL_AEROLLM_REPO": str(tmp_path / "nope"), "NO_COLOR": "1"},
    )
    assert r.returncode == 0, r.stderr
    assert "AeroLLM" in r.stdout


def test_build_fails_clearly_when_sibling_missing(tmp_path):
    r = subprocess.run(
        ["bash", str(BUILD), "build"],
        capture_output=True, text=True,
        env={**os.environ, "ARAIL_AEROLLM_REPO": str(tmp_path / "missing"), "NO_COLOR": "1"},
    )
    assert r.returncode == 1
    out = (r.stdout + r.stderr).lower()
    assert "clone" in out and "aerollm" in out


def test_setup_delegates_to_local_sibling_helper():
    txt = SETUP.read_text()
    assert "build-aerollm.sh" in txt
    # Still maximus-gated.
    assert "not 'maximus'" in txt or 'LAB_TIER:-minimalist}" != "maximus"' in txt


def test_no_maturin_develop_is_executed():
    for f in (SETUP, BUILD):
        code = _noncomment(f.read_text())
        assert "maturin develop" not in code, f.name


def test_helper_builds_with_cargo_not_pip():
    code = _noncomment(BUILD.read_text())
    assert "cargo build --release -p aerollm-api" in code
    assert "pip install aerollm" not in code
