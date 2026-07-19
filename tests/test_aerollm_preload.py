"""Tier-1 preload: safe-window gated, slot-serialized, kill-switchable."""

from __future__ import annotations

import asyncio

import pytest

from arail.portal import model_warmth
from arail.registry import health as reg_health
from arail.registry.store import TIER1_ID


@pytest.fixture
def tmp_registry(monkeypatch, tmp_path):
    """Local copy of tests/registry/conftest.py's fixture (scoped there)."""
    from arail.registry import core as reg_core
    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE",
                       str(tmp_path / "model_registry.json"))
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "ai-engineer:latest")
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    monkeypatch.setenv("AEROLLM_MODEL", "gpt-oss-20b-MLX-4bit")
    reg_core.reset_registry()
    reg = reg_core.get_registry()
    reg._ensure_loaded()
    yield reg
    reg_core.reset_registry()


@pytest.fixture
def _no_resident(monkeypatch):
    monkeypatch.setattr(model_warmth, "_tier1_resident", lambda: False)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.run(coro)


def test_not_safe_skips_construction(tmp_registry, monkeypatch, _no_resident):
    from arail.agents import deep_policy
    called = []
    monkeypatch.setattr(deep_policy, "prefer_deep",
                        lambda foreground=False: False)
    monkeypatch.setattr(deep_policy, "get_deep_router",
                        lambda: called.append(1))
    assert _run(model_warmth._preload_once()) == "not_safe"
    assert called == []


def test_safe_constructs_once_and_probes(tmp_registry, monkeypatch, _no_resident):
    from arail.agents import deep_policy
    called = []
    monkeypatch.setattr(deep_policy, "prefer_deep",
                        lambda foreground=False: True)
    monkeypatch.setattr(deep_policy, "background_safe", lambda: True)
    monkeypatch.setattr(deep_policy, "get_deep_router",
                        lambda: called.append(1) or object())
    status = _run(model_warmth._preload_once())
    assert status == "loaded"
    assert called == [1]
    assert TIER1_ID not in reg_health._WARMING       # cleared after load


def test_presence_arriving_while_queued_aborts(tmp_registry, monkeypatch,
                                               _no_resident):
    from arail.agents import deep_policy
    called = []
    monkeypatch.setattr(deep_policy, "prefer_deep",
                        lambda foreground=False: True)
    # Safe at first check, unsafe once inside the slot.
    monkeypatch.setattr(deep_policy, "background_safe", lambda: False)
    monkeypatch.setattr(deep_policy, "get_deep_router",
                        lambda: called.append(1))
    assert _run(model_warmth._preload_once()) == "not_safe_after_wait"
    assert called == []
    assert TIER1_ID not in reg_health._WARMING


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("ARAIL_AEROLLM_PRELOAD", "0")
    assert model_warmth._enabled() is False
    # The loop returns immediately without touching anything.
    _run(model_warmth.aerollm_preload_loop())


def test_already_resident_short_circuits(tmp_registry, monkeypatch):
    from arail.agents import deep_policy
    monkeypatch.setattr(model_warmth, "_tier1_resident", lambda: True)
    monkeypatch.setattr(deep_policy, "get_deep_router",
                        lambda: (_ for _ in ()).throw(AssertionError))
    assert _run(model_warmth._preload_once()) == "already_resident"
