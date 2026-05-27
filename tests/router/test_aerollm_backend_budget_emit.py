"""Integration tests 12–13 for AeroLLMBackend KV budget wiring.

Tests verify:
  12. _emit_budget_activity is called exactly once on first construction
      and not again on singleton reuse.
  13. rt_kwargs["kv_memory_budget"] is the int returned by _resolve_kv_budget,
      and absent when the resolver returns None.

Uses a fake aerollm_api module injected via sys.modules so construction
completes without loading real weights. Clears AeroLLMBackend._shared between
tests to reset singleton state.
"""

from __future__ import annotations

import sys
import os
import types
from typing import Any
from unittest.mock import patch, MagicMock, call

import pytest

# ---------------------------------------------------------------------------
# Build a minimal fake aerollm_api wheel
# ---------------------------------------------------------------------------

def _make_fake_aerollm_api() -> types.ModuleType:
    fake = types.ModuleType("aerollm_api")
    fake.__version__ = "0.0.0-test"

    class FakeRuntime:
        """Minimal stand-in for aerollm_api.Runtime."""

        _last_kwargs: "dict[str, Any] | None" = None

        def __init__(self, model_path: str, **kwargs: Any) -> None:
            FakeRuntime._last_kwargs = kwargs

        def start(self) -> None:
            pass

    fake.Runtime = FakeRuntime
    return fake


_FAKE_MODEL_DIR = "/tmp/fake-aerollm-model"
_GiB = 1024 ** 3


@pytest.fixture(autouse=True)
def _patch_env_and_model(monkeypatch, tmp_path):
    """Set env vars so AeroLLMBackend can construct without real model weights."""
    model_dir = tmp_path / "Qwen2.5-7B-Instruct-4bit"
    model_dir.mkdir()
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct-4bit")
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    monkeypatch.delenv("AEROLLM_DRAFT_MODEL", raising=False)
    monkeypatch.delenv("AEROLLM_RING_DEPTH", raising=False)


@pytest.fixture(autouse=True)
def _clear_shared():
    """Reset the AeroLLMBackend singleton between tests."""
    from arail.router.backends import AeroLLMBackend
    AeroLLMBackend._shared.clear()
    yield
    AeroLLMBackend._shared.clear()


# ---------------------------------------------------------------------------
# Test 12 — emit called exactly once; not again on singleton reuse
# ---------------------------------------------------------------------------
def test_budget_emit_called_once():
    """_emit_budget_activity fires on first construction only, not on reuse."""
    from arail.router.backends import AeroLLMBackend

    fake_aero = _make_fake_aerollm_api()
    known_result = {
        "budget_bytes": int(10 * _GiB),
        "reason": "KV budget resolved to 10.00 GiB (source=default, total=36.0 GiB, available=20.0 GiB)",
        "fields": {
            "pct_used": 0.60,
            "total_gib": 36.0,
            "available_gib": 20.0,
            "ceil_total_gib": 21.6,
            "ceil_available_gib": 15.5,
            "floor_gib": 2.0,
            "headroom_gib": 1.5,
            "source": "default",
        },
    }

    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch("arail.router.backends._resolve_kv_budget", return_value=known_result),
        patch.object(AeroLLMBackend, "_emit_budget_activity") as mock_emit,
    ):
        b1 = AeroLLMBackend()
        b2 = AeroLLMBackend()  # singleton reuse

    assert b1 is b2, "Expected singleton reuse"
    mock_emit.assert_called_once_with(known_result)


# ---------------------------------------------------------------------------
# Test 13a — kv_memory_budget kwarg is present and correct when resolver returns int
# ---------------------------------------------------------------------------
def test_kv_memory_budget_kwarg_present():
    """rt_kwargs['kv_memory_budget'] matches the int from _resolve_kv_budget."""
    from arail.router.backends import AeroLLMBackend

    fake_aero = _make_fake_aerollm_api()
    expected_bytes = int(15 * _GiB)
    known_result = {
        "budget_bytes": expected_bytes,
        "reason": "KV budget resolved to 15.00 GiB (source=default, total=36.0 GiB, available=20.0 GiB)",
        "fields": {"source": "default", "pct_used": 0.60,
                   "total_gib": 36.0, "available_gib": 20.0,
                   "ceil_total_gib": 21.6, "ceil_available_gib": 15.5,
                   "floor_gib": 2.0, "headroom_gib": 1.5},
    }

    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch("arail.router.backends._resolve_kv_budget", return_value=known_result),
        patch.object(AeroLLMBackend, "_emit_budget_activity"),
    ):
        AeroLLMBackend()

    assert fake_aero.Runtime._last_kwargs.get("kv_memory_budget") == expected_bytes
    assert isinstance(fake_aero.Runtime._last_kwargs["kv_memory_budget"], int)


# ---------------------------------------------------------------------------
# Test 13b — kv_memory_budget kwarg is ABSENT when resolver returns None
# ---------------------------------------------------------------------------
def test_kv_memory_budget_kwarg_absent_when_resolver_returns_none():
    """rt_kwargs must NOT contain kv_memory_budget when budget_bytes=None."""
    from arail.router.backends import AeroLLMBackend

    fake_aero = _make_fake_aerollm_api()
    none_result = {
        "budget_bytes": None,
        "reason": "psutil unavailable; aerollm will auto-detect KV budget",
        "fields": {"source": "unavailable", "pct_used": 0.60,
                   "total_gib": None, "available_gib": None,
                   "ceil_total_gib": None, "ceil_available_gib": None,
                   "floor_gib": 2.0, "headroom_gib": 1.5},
    }

    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch("arail.router.backends._resolve_kv_budget", return_value=none_result),
        patch.object(AeroLLMBackend, "_emit_budget_activity"),
    ):
        AeroLLMBackend()

    assert "kv_memory_budget" not in fake_aero.Runtime._last_kwargs


# ---------------------------------------------------------------------------
# Test 14a — positive-path: _emit_budget_activity body runs; activity_log.emit
#            called with correct args (source="aerollm", level="info")
# ---------------------------------------------------------------------------
def test_emit_budget_activity_positive_path_info():
    """_emit_budget_activity runs for real (not patched out) and calls
    arail.activity.activity_log.emit with source='aerollm', level='info',
    and a message that contains the resolved budget description."""
    from arail.router.backends import AeroLLMBackend
    from unittest.mock import MagicMock
    import arail.activity as _activity_mod

    fake_aero = _make_fake_aerollm_api()
    known_result = {
        "budget_bytes": int(9 * _GiB),
        "reason": "KV budget resolved to 9.00 GiB (source=default, total=16.0 GiB, available=14.0 GiB)",
        "fields": {
            "source": "default",
            "pct_used": 0.60,
            "total_gib": 16.0,
            "available_gib": 14.0,
            "ceil_total_gib": 9.6,
            "ceil_available_gib": 9.0,
            "floor_gib": 2.0,
            "headroom_gib": 1.5,
        },
    }

    mock_emit = MagicMock()
    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch("arail.router.backends._resolve_kv_budget", return_value=known_result),
        patch.object(_activity_mod.activity_log, "emit", mock_emit),
    ):
        AeroLLMBackend()

    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == "aerollm", f"Expected source='aerollm', got {args[0]!r}"
    assert "KV budget resolved" in args[1], f"Message missing expected text: {args[1]!r}"
    assert kwargs.get("level") == "info", f"Expected level='info', got {kwargs.get('level')!r}"


# ---------------------------------------------------------------------------
# Test 14b — positive-path: source="floor" triggers level="warn"
# ---------------------------------------------------------------------------
def test_emit_budget_activity_positive_path_warn_on_floor():
    """When _resolve_kv_budget returns source='floor', _emit_budget_activity
    calls activity_log.emit with level='warn'."""
    from arail.router.backends import AeroLLMBackend
    from unittest.mock import MagicMock
    import arail.activity as _activity_mod

    fake_aero = _make_fake_aerollm_api()
    floor_result = {
        "budget_bytes": int(2 * _GiB),
        "reason": "KV budget clamped to floor 2.00 GiB (source=floor, total=4.0 GiB, available=1.0 GiB)",
        "fields": {
            "source": "floor",
            "pct_used": 0.60,
            "total_gib": 4.0,
            "available_gib": 1.0,
            "ceil_total_gib": 2.4,
            "ceil_available_gib": 0.0,
            "floor_gib": 2.0,
            "headroom_gib": 1.5,
        },
    }

    mock_emit = MagicMock()
    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch("arail.router.backends._resolve_kv_budget", return_value=floor_result),
        patch.object(_activity_mod.activity_log, "emit", mock_emit),
    ):
        AeroLLMBackend()

    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == "aerollm", f"Expected source='aerollm', got {args[0]!r}"
    assert kwargs.get("level") == "warn", f"Expected level='warn', got {kwargs.get('level')!r}"
