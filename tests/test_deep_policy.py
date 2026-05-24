"""Throttle-aware deep-inference policy for the agents.

Covers the decision (`prefer_deep`/`background_safe`) and the transparent
deep→fast fallback (`complete_preferring_deep`) — all without loading real
model weights.
"""
from __future__ import annotations

import pytest

from arail.agents import deep_policy


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    deep_policy._reset_for_tests()
    monkeypatch.delenv("ARAIL_AGENT_DEEP", raising=False)
    monkeypatch.delenv("ARAIL_AEROLLM_BG_PRESSURE_PCT", raising=False)
    # Default world: aeroLLM importable + maximus tier (so tier/import don't block).
    monkeypatch.setattr(deep_policy, "_aerollm_importable", lambda: True)
    monkeypatch.setattr("arail.tier.is_maximus", lambda: True)
    yield
    deep_policy._reset_for_tests()


def _bg(monkeypatch, *, halted=False, window="heavy", profile="throughput", pressure=None):
    monkeypatch.setattr("arail.scheduler.jobs_halted", lambda: halted)
    monkeypatch.setattr("arail.scheduler.current_window", lambda *a, **k: window)
    monkeypatch.setattr("arail.runtime_profile.resolve", lambda *a, **k: (profile, "test"))
    monkeypatch.setattr("arail.router.mlx_guard.metal_memory_pressure", lambda: pressure)


# ── prefer_deep gating ──────────────────────────────────────────────────────

def test_foreground_prefers_deep_on_maximus():
    assert deep_policy.prefer_deep(foreground=True) is True


def test_minimalist_never_deep(monkeypatch):
    monkeypatch.setattr("arail.tier.is_maximus", lambda: False)
    assert deep_policy.prefer_deep(foreground=True) is False
    assert deep_policy.prefer_deep(foreground=False) is False


def test_kill_switch_forces_fast(monkeypatch):
    monkeypatch.setenv("ARAIL_AGENT_DEEP", "0")
    assert deep_policy.prefer_deep(foreground=True) is False


def test_no_aerollm_never_deep(monkeypatch):
    monkeypatch.setattr(deep_policy, "_aerollm_importable", lambda: False)
    assert deep_policy.prefer_deep(foreground=True) is False


# ── background_safe throttle ────────────────────────────────────────────────

def test_background_safe_when_heavy_window_low_pressure(monkeypatch):
    _bg(monkeypatch, window="heavy", profile="throughput", pressure=0.2)
    assert deep_policy.background_safe() is True
    assert deep_policy.prefer_deep(foreground=False) is True


def test_background_declines_during_active_window(monkeypatch):
    _bg(monkeypatch, window="active", profile="throughput", pressure=0.2)
    assert deep_policy.background_safe() is False
    assert deep_policy.prefer_deep(foreground=False) is False


def test_background_declines_when_operator_present(monkeypatch):
    _bg(monkeypatch, window="heavy", profile="interactive", pressure=0.2)
    assert deep_policy.background_safe() is False


def test_background_declines_when_profile_disallows(monkeypatch):
    # 'balanced' has background_aerollm=False.
    _bg(monkeypatch, window="idle", profile="balanced", pressure=0.2)
    assert deep_policy.background_safe() is False


def test_background_declines_under_memory_pressure(monkeypatch):
    _bg(monkeypatch, window="heavy", profile="throughput", pressure=0.9)
    assert deep_policy.background_safe() is False


def test_background_declines_when_jobs_halted(monkeypatch):
    _bg(monkeypatch, halted=True, window="heavy", profile="throughput", pressure=0.1)
    assert deep_policy.background_safe() is False


def test_unknown_pressure_does_not_block(monkeypatch):
    # metal_memory_pressure() returns None on non-MLX hosts → "unknown, proceed".
    _bg(monkeypatch, window="heavy", profile="throughput", pressure=None)
    assert deep_policy.background_safe() is True


# ── complete_preferring_deep fallback ───────────────────────────────────────

class _Resp:
    def __init__(self, text):
        self.text = text


class _Router:
    def __init__(self, text="ok", boom=False):
        self.text, self.boom, self.calls = text, boom, 0

    def complete(self, prompt, **kw):
        self.calls += 1
        if self.boom:
            raise RuntimeError("simulated Metal OOM")
        return _Resp(self.text)


def test_complete_uses_deep_when_preferred(monkeypatch):
    deep, fast = _Router("deep-answer"), _Router("fast-answer")
    monkeypatch.setattr(deep_policy, "get_deep_router", lambda: deep)
    out = deep_policy.complete_preferring_deep("hi", foreground=True, fast_router=fast)
    assert out == "deep-answer"
    assert deep.calls == 1 and fast.calls == 0


def test_complete_falls_back_to_fast_on_deep_failure(monkeypatch):
    deep, fast = _Router(boom=True), _Router("fast-answer")
    monkeypatch.setattr(deep_policy, "get_deep_router", lambda: deep)
    out = deep_policy.complete_preferring_deep("hi", foreground=True, fast_router=fast)
    assert out == "fast-answer"
    assert deep.calls == 1 and fast.calls == 1


def test_complete_uses_fast_when_not_preferred(monkeypatch):
    monkeypatch.setattr("arail.tier.is_maximus", lambda: False)  # not maximus → fast
    deep, fast = _Router("deep-answer"), _Router("fast-answer")
    monkeypatch.setattr(deep_policy, "get_deep_router", lambda: deep)
    out = deep_policy.complete_preferring_deep("hi", foreground=True, fast_router=fast)
    assert out == "fast-answer"
    assert deep.calls == 0 and fast.calls == 1
