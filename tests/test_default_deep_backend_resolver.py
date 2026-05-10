"""Tests for `_resolve_default_deep_backend()` — the platform-aware deep
backend selector that powers ARAIL's 0.1.0 alpha aeroLLM/AirLLM split.

The resolver must:
  1. Honor an explicit ``ARAIL_DEEP_BACKEND`` env override (when valid)
  2. Auto-detect aerollm on macOS arm64 when the wheel is importable
  3. Fall back to airllm everywhere else (CUDA, Linux x86, AeroLLM unbuilt)
  4. Treat unknown override values as "fall through to auto-detect"
     (with a warning) instead of raising

The function is the foundation for Phase A.2 of the alpha plan, which
wires the three hard-coded ``"airllm"`` dispatch sites into this
resolver. Until then, the resolver is informational (read by
``/api/models`` for UI labelling) and does not change which backend
dispatch chooses on a chat call. These tests pin its contract so the
A.2 wiring goes in safely."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# Ensure src/ is importable when running standalone (matches CI layout).
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))

from arail.portal import app as portal_app


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Make sure ARAIL_DEEP_BACKEND is unset before every test so we
    measure the auto-detect path unless explicitly overridden."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    yield


# ── Override path ────────────────────────────────────────────────────────


def test_explicit_override_aerollm(monkeypatch):
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "aerollm")
    assert portal_app._resolve_default_deep_backend() == "aerollm"


def test_explicit_override_airllm(monkeypatch):
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "airllm")
    assert portal_app._resolve_default_deep_backend() == "airllm"


def test_override_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "AeroLLM")
    assert portal_app._resolve_default_deep_backend() == "aerollm"


def test_override_is_whitespace_stripped(monkeypatch):
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "  airllm  ")
    assert portal_app._resolve_default_deep_backend() == "airllm"


def test_invalid_override_falls_through_to_autodetect(monkeypatch):
    """Unknown override values must NOT raise; they fall through to the
    platform auto-detect with a logged warning. Operators see their
    typo via the activity log without losing the lab."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "cloud-bogus")
    result = portal_app._resolve_default_deep_backend()
    assert result in ("aerollm", "airllm"), \
        f"expected fallback to a known backend, got {result!r}"


def test_empty_override_falls_through(monkeypatch):
    """Empty string should be treated as 'no override' (auto-detect)."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "")
    result = portal_app._resolve_default_deep_backend()
    assert result in ("aerollm", "airllm")


# ── Auto-detect path (macOS arm64) ───────────────────────────────────────


def test_macos_arm64_with_aerollm_returns_aerollm(monkeypatch):
    """On Apple Silicon with aerollm_api importable, default is aerollm."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    with patch("platform.system", return_value="Darwin"), \
         patch("platform.machine", return_value="arm64"):
        # aerollm_api is already installed in the venv; no further
        # patching needed. Confirm it actually resolves.
        result = portal_app._resolve_default_deep_backend()
        assert result == "aerollm", \
            f"expected aerollm on Apple Silicon w/ aerollm_api, got {result!r}"


def test_macos_arm64_without_aerollm_falls_back_to_airllm(monkeypatch):
    """If the aerollm_api wheel isn't built, even Apple Silicon falls
    back to airllm. This covers the developer-bootstrap state where
    setup.sh hasn't been re-run since the rename."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)

    # Hide aerollm_api from the import system for the duration of the call.
    saved = sys.modules.pop("aerollm_api", None)

    def _missing(name, *a, **kw):
        if name == "aerollm_api":
            raise ImportError("aerollm_api hidden by test")
        return _real_import(name, *a, **kw)

    _real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__
    with patch("platform.system", return_value="Darwin"), \
         patch("platform.machine", return_value="arm64"), \
         patch("builtins.__import__", side_effect=_missing):
        try:
            result = portal_app._resolve_default_deep_backend()
        finally:
            if saved is not None:
                sys.modules["aerollm_api"] = saved

    assert result == "airllm", \
        f"expected airllm fallback when aerollm_api is missing, got {result!r}"


# ── Auto-detect path (non-Apple-Silicon) ─────────────────────────────────


def test_macos_intel_returns_airllm(monkeypatch):
    """Intel Mac (x86_64) — no aerollm mlx-native; falls back to airllm."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    with patch("platform.system", return_value="Darwin"), \
         patch("platform.machine", return_value="x86_64"):
        assert portal_app._resolve_default_deep_backend() == "airllm"


def test_linux_returns_airllm(monkeypatch):
    """Linux (CUDA or x86 CPU) — aerollm CUDA backend is scaffold-only,
    so airllm is the default until it lands."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    with patch("platform.system", return_value="Linux"), \
         patch("platform.machine", return_value="x86_64"):
        assert portal_app._resolve_default_deep_backend() == "airllm"


def test_windows_returns_airllm(monkeypatch):
    """Windows (where someone runs WSL) — same fallback as Linux."""
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    with patch("platform.system", return_value="Windows"), \
         patch("platform.machine", return_value="AMD64"):
        assert portal_app._resolve_default_deep_backend() == "airllm"


# ── Override beats auto-detect ───────────────────────────────────────────


def test_override_beats_apple_silicon_autodetect(monkeypatch):
    """Even on Apple Silicon w/ aerollm_api available, an explicit
    ARAIL_DEEP_BACKEND=airllm wins. Operators can dogfood the legacy
    backend without uninstalling aerollm."""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "airllm")
    with patch("platform.system", return_value="Darwin"), \
         patch("platform.machine", return_value="arm64"):
        assert portal_app._resolve_default_deep_backend() == "airllm"


def test_override_beats_linux_default(monkeypatch):
    """Same in reverse — operator can opt into aerollm on Linux even
    though auto-detect would pick airllm. (Useful once the aerollm
    CUDA backend ships and operators want to test it.)"""
    monkeypatch.setenv("ARAIL_DEEP_BACKEND", "aerollm")
    with patch("platform.system", return_value="Linux"), \
         patch("platform.machine", return_value="x86_64"):
        assert portal_app._resolve_default_deep_backend() == "aerollm"
