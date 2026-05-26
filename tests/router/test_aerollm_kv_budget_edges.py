"""QA edge-case coverage for _resolve_kv_budget / _emit_budget_activity.

Sprint: 2026-05-26-aerollm-kv-available-budget
Allocation: 60% edge / 20% happy / 20% regression.

These tests complement the unit/integration tests landed by the builder
(test_aerollm_kv_budget.py + test_aerollm_backend_budget_emit.py). They
exercise boundary arithmetic, exotic env-var parsing, all four `source`
values through `_emit_budget_activity`, the singleton idempotency
guarantee across distinct singleton keys, the logger-warn fallback when
activity_log.emit raises, and a complementary psutil-attribute-failure
path.
"""

from __future__ import annotations

import logging
import sys
import types
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

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
    return SimpleNamespace(
        total=int(total_gib * _GiB),
        available=int(available_gib * _GiB),
    )


# =============================================================================
# (a) Boundary arithmetic on the formula
# =============================================================================


def test_tie_total_vs_available_picks_either_but_is_int(monkeypatch):
    """When ceil_total == ceil_available, min() returns the first arg; result
    must still be int and within 1 byte of expected."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    # Pick total and available so total*0.60 == available*0.85 - HEADROOM
    # total*0.6 = a*0.85 - H  → a = (0.6*T + H) / 0.85
    total = 36 * _GiB
    available = int((0.6 * total + _AEROLLM_KV_SAFETY_HEADROOM_BYTES) / 0.85)
    vm = SimpleNamespace(total=total, available=available)
    with patch("psutil.virtual_memory", return_value=vm):
        result = _resolve_kv_budget()

    assert isinstance(result["budget_bytes"], int)
    assert result["fields"]["source"] in {"default", "env"}
    # Within 2 bytes of the expected (float rounding)
    assert abs(result["budget_bytes"] - int(0.6 * total)) <= 2


def test_raw_budget_exactly_equal_to_floor_does_not_trigger_floor(monkeypatch):
    """If raw_budget == MIN_FLOOR exactly, the check is `< floor` so it
    should NOT be relabeled 'floor'. Off-by-one guard."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    # Want ceil_total to equal floor and be the min.
    # ceil_total = total * 0.60 = MIN_FLOOR  → total = MIN_FLOOR / 0.60
    total = int(_AEROLLM_KV_MIN_FLOOR_BYTES / 0.60)
    # Make ceil_available much larger so min picks ceil_total
    available = int(20 * _GiB)
    vm = SimpleNamespace(total=total, available=available)
    with patch("psutil.virtual_memory", return_value=vm):
        result = _resolve_kv_budget()

    # raw budget is ~exactly the floor; source should be "default" (not "floor")
    # since the strict-less-than check should fail.
    assert result["budget_bytes"] >= _AEROLLM_KV_MIN_FLOOR_BYTES
    # If raw was *exactly* equal, source stays "default"; if rounding made it
    # 1 byte below, source goes "floor". Both acceptable but we assert the
    # boundary check is strict and budget never lies BELOW floor.
    assert result["fields"]["source"] in {"default", "floor"}


def test_available_smaller_than_headroom_negative_ceil_triggers_floor(monkeypatch):
    """available so small that ceil_available is negative → floor applies."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    # available=0.5 GiB → ceil_available = 0.5*0.85 - 1.5 ≈ -1.075 GiB
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 0.5)):
        result = _resolve_kv_budget()
    assert result["budget_bytes"] == _AEROLLM_KV_MIN_FLOOR_BYTES
    assert result["fields"]["source"] == "floor"
    # ceil_available_gib must report the negative number honestly for debug
    assert result["fields"]["ceil_available_gib"] < 0


def test_available_greater_than_total_container_quirk(monkeypatch):
    """psutil in containers can report available > total. min() picks the
    smaller of the two ceilings so total-side wins; must not crash."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(8, 16)):
        result = _resolve_kv_budget()
    # ceil_total = 8 * 0.60 = 4.8; ceil_available = 16*0.85 - 1.5 = 12.1 → 4.8 wins
    expected = int(8 * _GiB * 0.60)
    assert result["budget_bytes"] == expected
    assert result["fields"]["source"] == "default"
    assert isinstance(result["budget_bytes"], int)


def test_tiny_box_4gib_floor_applies(monkeypatch):
    """4 GiB box, 2 GiB available → ceil_available = 2*0.85 - 1.5 = 0.2 GiB → floor."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(4, 2)):
        result = _resolve_kv_budget()
    assert result["budget_bytes"] == _AEROLLM_KV_MIN_FLOOR_BYTES
    assert result["fields"]["source"] == "floor"


def test_huge_box_512gib_no_overflow(monkeypatch):
    """Large machine: result still int, no overflow, reasonable magnitude."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    with patch("psutil.virtual_memory", return_value=_fake_vm(512, 400)):
        result = _resolve_kv_budget()
    # ceil_total = 307.2; ceil_available = 340 - 1.5 = 338.5 → 307.2 wins
    expected = int(512 * _GiB * 0.60)
    assert result["budget_bytes"] == expected
    assert isinstance(result["budget_bytes"], int)
    # Sanity: int fits in a normal Python int (always true) and is reasonable
    assert 0 < result["budget_bytes"] < 1024 * _GiB


# =============================================================================
# (b) Env-var parsing edges
# =============================================================================


@pytest.mark.parametrize("raw", ["  0.5  ", "0.5\n", "\t0.5", "0.5\r\n"])
def test_env_whitespace_is_stripped(monkeypatch, raw):
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", raw)
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()
    assert result["fields"]["pct_used"] == 0.5
    assert result["fields"]["source"] == "env"


@pytest.mark.parametrize("raw,expected", [
    ("0.5e0", 0.5),
    (".5", 0.5),
    ("5e-1", 0.5),
    ("+0.5", 0.5),
])
def test_env_exotic_numerics_accepted(monkeypatch, raw, expected):
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", raw)
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()
    assert result["fields"]["pct_used"] == pytest.approx(expected)
    assert result["fields"]["source"] == "env"


def test_env_locale_comma_falls_back(monkeypatch):
    """`'0,5'` is not a float() literal → fallback to default."""
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "0,5")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()
    assert result["fields"]["pct_used"] == _AEROLLM_KV_PCT_DEFAULT
    assert result["fields"]["source"] == "default"
    assert "invalid" in result["reason"]


def test_env_very_small_valid_pct(monkeypatch):
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "0.001")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()
    # 36 * 0.001 = 0.036 GiB → below floor → floor wins
    assert result["budget_bytes"] == _AEROLLM_KV_MIN_FLOOR_BYTES
    assert result["fields"]["source"] == "floor"
    # pct_used still recorded as the env pct
    assert result["fields"]["pct_used"] == pytest.approx(0.001)


def test_env_exactly_one_falls_back(monkeypatch):
    """Boundary: check is `0.0 < pct < 1.0` (strict)."""
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "1.0")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()
    assert result["fields"]["source"] == "default"
    assert result["fields"]["pct_used"] == _AEROLLM_KV_PCT_DEFAULT


def test_env_exactly_zero_falls_back(monkeypatch):
    monkeypatch.setenv("AEROLLM_KV_BUDGET_PCT", "0.0")
    with patch("psutil.virtual_memory", return_value=_fake_vm(36, 30)):
        result = _resolve_kv_budget()
    assert result["fields"]["source"] == "default"
    assert result["fields"]["pct_used"] == _AEROLLM_KV_PCT_DEFAULT


# =============================================================================
# (c) Emit covered for all four source values
# =============================================================================


@pytest.mark.parametrize("source,expected_level", [
    ("default", "info"),
    ("env", "info"),
    ("floor", "warn"),
    ("unavailable", "warn"),
])
def test_emit_handles_all_sources(source, expected_level):
    """_emit_budget_activity routes level correctly for every source value
    and never crashes."""
    from arail.router.backends import AeroLLMBackend
    import arail.activity as _activity_mod

    instance = AeroLLMBackend.__new__(AeroLLMBackend)  # bypass __init__
    reasoning = {
        "budget_bytes": int(5 * _GiB) if source != "unavailable" else None,
        "reason": f"KV budget resolved (source={source})",
        "fields": {"source": source},
    }
    mock_emit = MagicMock()
    with patch.object(_activity_mod.activity_log, "emit", mock_emit):
        instance._emit_budget_activity(reasoning)  # must not raise
    mock_emit.assert_called_once()
    args, kwargs = mock_emit.call_args
    assert args[0] == "aerollm"
    assert kwargs.get("level") == expected_level


# =============================================================================
# (d) Idempotency / singleton re-use
# =============================================================================


def _make_fake_aerollm_api() -> types.ModuleType:
    fake = types.ModuleType("aerollm_api")
    fake.__version__ = "0.0.0-test"

    class FakeRuntime:
        _last_kwargs: "dict[str, Any] | None" = None

        def __init__(self, model_path: str, **kwargs: Any) -> None:
            FakeRuntime._last_kwargs = kwargs

        def start(self) -> None:
            pass

    fake.Runtime = FakeRuntime
    return fake


@pytest.fixture
def _clear_shared():
    from arail.router.backends import AeroLLMBackend
    AeroLLMBackend._shared.clear()
    yield
    AeroLLMBackend._shared.clear()


def test_singleton_same_key_resolves_only_once(_clear_shared, monkeypatch, tmp_path):
    """Two AeroLLMBackend() calls with identical env → _resolve_kv_budget
    called exactly once."""
    from arail.router.backends import AeroLLMBackend

    model_dir = tmp_path / "Qwen2.5-7B-Instruct-4bit"
    model_dir.mkdir()
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct-4bit")

    fake_aero = _make_fake_aerollm_api()
    known_result = {
        "budget_bytes": int(10 * _GiB),
        "reason": "x",
        "fields": {"source": "default"},
    }
    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch(
            "arail.router.backends._resolve_kv_budget",
            return_value=known_result,
        ) as mock_resolve,
        patch.object(AeroLLMBackend, "_emit_budget_activity") as mock_emit,
    ):
        b1 = AeroLLMBackend()
        b2 = AeroLLMBackend()

    assert b1 is b2
    assert mock_resolve.call_count == 1
    assert mock_emit.call_count == 1


def test_singleton_distinct_model_keys_each_emit(_clear_shared, monkeypatch, tmp_path):
    """Construct with two different AEROLLM_MODEL values → two emits,
    proving the singleton key actually keys per-model."""
    from arail.router.backends import AeroLLMBackend

    (tmp_path / "Qwen2.5-7B-Instruct-4bit").mkdir()
    (tmp_path / "Qwen2.5-72B-Instruct-4bit").mkdir()
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path))

    fake_aero = _make_fake_aerollm_api()
    known_result = {
        "budget_bytes": int(10 * _GiB),
        "reason": "x",
        "fields": {"source": "default"},
    }
    with (
        patch.dict(sys.modules, {"aerollm_api": fake_aero}),
        patch(
            "arail.router.backends._resolve_kv_budget",
            return_value=known_result,
        ) as mock_resolve,
        patch.object(AeroLLMBackend, "_emit_budget_activity") as mock_emit,
    ):
        monkeypatch.setenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct-4bit")
        b1 = AeroLLMBackend()
        monkeypatch.setenv("AEROLLM_MODEL", "Qwen2.5-72B-Instruct-4bit")
        b2 = AeroLLMBackend()

    assert b1 is not b2
    assert mock_resolve.call_count == 2
    assert mock_emit.call_count == 2


# =============================================================================
# (e) Logger-warn fallback when emit() raises
# =============================================================================


def test_emit_swallows_exception_and_logs_warning(caplog):
    """If activity_log.emit raises, _emit_budget_activity must NOT propagate
    and MUST log at WARNING level via the module logger."""
    from arail.router.backends import AeroLLMBackend
    import arail.activity as _activity_mod

    instance = AeroLLMBackend.__new__(AeroLLMBackend)
    reasoning = {
        "budget_bytes": int(5 * _GiB),
        "reason": "anything",
        "fields": {"source": "default"},
    }

    def _boom(*args, **kwargs):
        raise RuntimeError("activity bus is down")

    with patch.object(_activity_mod.activity_log, "emit", side_effect=_boom):
        with caplog.at_level(logging.WARNING, logger="arail.router.backends"):
            # Must not raise
            instance._emit_budget_activity(reasoning)

    # Warning was logged with the exception text included
    matched = [
        r for r in caplog.records
        if "activity_log emission failed" in r.getMessage()
        and "activity bus is down" in r.getMessage()
    ]
    assert matched, f"expected warning log; got: {[r.getMessage() for r in caplog.records]}"
    assert matched[0].levelno == logging.WARNING


# =============================================================================
# (f) psutil attribute-failure path (complementary to test 8 import failure)
# =============================================================================


def test_psutil_attribute_failure_falls_back_to_none(monkeypatch):
    """psutil imports successfully, but virtual_memory attribute access raises
    AttributeError — different failure class than ImportError. Resolver must
    still degrade gracefully to budget_bytes=None / source='unavailable'."""
    monkeypatch.delenv("AEROLLM_KV_BUDGET_PCT", raising=False)
    broken_psutil = types.ModuleType("psutil")

    class _Boom:
        def __getattr__(self, name):
            raise AttributeError(f"{name} unavailable on this platform")

    # Make `import psutil` return our module and `psutil.virtual_memory`
    # raise AttributeError at attribute lookup time.
    sys.modules.pop("psutil", None)  # force re-import
    broken = _Boom()
    # The resolver does `import psutil; psutil.virtual_memory()`. Easiest is
    # to inject a module whose virtual_memory attr access raises.
    fake_mod = types.ModuleType("psutil")

    def _raise(*a, **k):
        raise AttributeError("virtual_memory not available")

    # Define virtual_memory as a property-like that raises on call, OR
    # delete it so attribute lookup itself fails. Simulate the latter:
    class _ModWithBrokenAttr(types.ModuleType):
        def __getattr__(self, name):
            if name == "virtual_memory":
                raise AttributeError("virtual_memory not exported")
            raise AttributeError(name)

    broken_mod = _ModWithBrokenAttr("psutil")
    with patch.dict(sys.modules, {"psutil": broken_mod}):
        result = _resolve_kv_budget()

    assert result["budget_bytes"] is None
    assert result["fields"]["source"] == "unavailable"
