"""Unit tests for _resolve_kv_budget() (pure function — no AeroLLMBackend instantiation).

Tests 1–11 cover the behavior matrix from ARCHITECTURE.md §"Interface contracts".
Test 14 (regression) is included here per ARCHITECTURE.md §"Regression test".
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch, MagicMock

import pytest

from arail.router.backends import (
    _resolve_kv_budget,
    _AEROLLM_KV_MIN_FLOOR_BYTES,
    _AEROLLM_KV_SAFETY_HEADROOM_BYTES,
    _AEROLLM_KV_AVAILABLE_FRACTION,
    _AEROLLM_KV_PCT_DEFAULT,
)

_GiB = 1024 ** 3


def _fake_vm(total_gib: float, available_gib: float) -> SimpleNamespace:
    return SimpleNamespace(total=int(total_gib * _GiB), available=int(available_gib * _GiB))


# ---------------------------------------------------------------------------
# Test 1 — default pct, healthy box
# ---------------------------------------------------------------------------
def test_default_pct_healthy_box(monkeypatch):
    """total=36, available=20, env unset → min(21.6, 15.5) = 15.5 GiB; source=default."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 20)):
        result = _resolve_kv_budget()

    expected_bytes = int(20 * _GiB * _AEROLLM_KV_AVAILABLE_FRACTION - _AEROLLM_KV_SAFETY_HEADROOM_BYTES)
    assert result["budget_bytes"] == expected_bytes
    assert result["fields"]["source"] == "default"
    assert result["budget_bytes"] is not None
    assert isinstance(result["budget_bytes"], int)


# ---------------------------------------------------------------------------
# Test 2 — env pct lower than available ceiling
# ---------------------------------------------------------------------------
def test_env_pct_lower_than_available_ceiling(monkeypatch):
    """total=36, available=30, env=0.30 → min(10.8, 24) = 10.8 GiB; source=env."""
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "0.30")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()

    expected_bytes = int(36 * _GiB * 0.30)
    assert result["budget_bytes"] == expected_bytes
    assert result["fields"]["source"] == "env"


# ---------------------------------------------------------------------------
# Test 3 — env pct higher than available ceiling
# ---------------------------------------------------------------------------
def test_env_pct_higher_than_available_ceiling(monkeypatch):
    """total=36, available=8, env=0.80 → min(28.8, 5.3) = 5.3 GiB; source=env."""
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "0.80")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 8)):
        result = _resolve_kv_budget()

    ceil_available = 8 * _GiB * _AEROLLM_KV_AVAILABLE_FRACTION - _AEROLLM_KV_SAFETY_HEADROOM_BYTES
    expected_bytes = int(ceil_available)
    assert result["budget_bytes"] == expected_bytes
    # available-side won; source is still "env" because env pct was valid
    assert result["fields"]["source"] == "env"


# ---------------------------------------------------------------------------
# Test 4 — floor applied when box is starved
# ---------------------------------------------------------------------------
def test_floor_applied_when_box_starved(monkeypatch):
    """total=36, available=3 → raw=1.05 GiB → bumped to 2 GiB floor; source=floor."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 3)):
        result = _resolve_kv_budget()

    assert result["budget_bytes"] == _AEROLLM_KV_MIN_FLOOR_BYTES
    assert result["fields"]["source"] == "floor"


# ---------------------------------------------------------------------------
# Test 5 — env="0" falls back to default
# ---------------------------------------------------------------------------
def test_env_zero_falls_back_to_default(monkeypatch):
    """env=0 is out-of-range → fallback to 0.60; identical to test_default_pct_healthy_box."""
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "0")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 20)):
        result = _resolve_kv_budget()

    # Same as default path (pct=0.60, same memory)
    expected_bytes = int(20 * _GiB * _AEROLLM_KV_AVAILABLE_FRACTION - _AEROLLM_KV_SAFETY_HEADROOM_BYTES)
    assert result["budget_bytes"] == expected_bytes
    assert result["fields"]["source"] == "default"
    assert "invalid" in result["reason"]


# ---------------------------------------------------------------------------
# Test 6 — env="abc" falls back to default
# ---------------------------------------------------------------------------
def test_env_garbage_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "abc")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 20)):
        result = _resolve_kv_budget()

    assert result["fields"]["pct_used"] == _AEROLLM_KV_PCT_DEFAULT
    assert result["fields"]["source"] == "default"
    assert "invalid" in result["reason"]


# ---------------------------------------------------------------------------
# Test 7 — env="1.5" (above 1.0) falls back to default
# ---------------------------------------------------------------------------
def test_env_above_one_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "1.5")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 20)):
        result = _resolve_kv_budget()

    assert result["fields"]["pct_used"] == _AEROLLM_KV_PCT_DEFAULT
    assert result["fields"]["source"] == "default"
    assert "invalid" in result["reason"]


# ---------------------------------------------------------------------------
# Test 8 — psutil ImportError
# ---------------------------------------------------------------------------
def test_psutil_import_error(monkeypatch):
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch.dict("sys.modules", {"psutil": None}):
        result = _resolve_kv_budget()

    assert result["budget_bytes"] is None
    assert result["fields"]["source"] == "unavailable"


# ---------------------------------------------------------------------------
# Test 9 — psutil.virtual_memory raises
# ---------------------------------------------------------------------------
def test_psutil_call_raises(monkeypatch):
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    fake_psutil = MagicMock()
    fake_psutil.virtual_memory.side_effect = RuntimeError("kernel panic")
    with patch.dict("sys.modules", {"psutil": fake_psutil}):
        result = _resolve_kv_budget()

    assert result["budget_bytes"] is None
    assert result["fields"]["source"] == "unavailable"


# ---------------------------------------------------------------------------
# Test 10 — total=0 (defensive)
# ---------------------------------------------------------------------------
def test_total_zero_returns_none(monkeypatch):
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=SimpleNamespace(total=0, available=0)):
        result = _resolve_kv_budget()

    assert result["budget_bytes"] is None
    assert result["fields"]["source"] == "unavailable"


# ---------------------------------------------------------------------------
# Test 11 — returned bytes are int (not float)
# ---------------------------------------------------------------------------
def test_returned_bytes_are_int(monkeypatch):
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 20)):
        result = _resolve_kv_budget()

    assert isinstance(result["budget_bytes"], int), (
        f"budget_bytes must be int for PyO3 compatibility, got {type(result['budget_bytes'])}"
    )


# ---------------------------------------------------------------------------
# Test 14 (regression) — default env pct 0.60 preserves legacy value on idle box
# ---------------------------------------------------------------------------
def test_default_env_pct_060_preserves_legacy_value_on_idle_box(monkeypatch):
    """total=16, available=14 → min(9.6, 10.4) = 9.6 GiB — matches today's behavior."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(16, 14)):
        result = _resolve_kv_budget()

    # ceil_total = 16 * 0.60 = 9.6 GiB
    # ceil_available = 14 * 0.85 - 1.5 = 10.4 GiB
    # min = 9.6 GiB → total-side wins, matches legacy 0.60 * total behavior
    expected_bytes = int(16 * _GiB * _AEROLLM_KV_PCT_DEFAULT)
    assert result["budget_bytes"] == expected_bytes
    assert result["fields"]["source"] == "default"
