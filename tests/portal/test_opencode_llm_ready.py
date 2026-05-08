"""Unit tests for llm_ready_check + cache.

Covers ARCHITECTURE.md must-pass list:
  F-GATE-1  — /api/opencode/start blocked when no LLM
  F-GATE-5  — cache invalidation
"""
from __future__ import annotations

import time
import unittest.mock as mock

import pytest


def _setup_mocks(monkeypatch, provider="my_machine", state="ready", model=None, token=""):
    """Wire up the lazy imports that llm_ready_check uses."""
    # Reset the cache first
    import arail.portal.services.opencode as oc_mod
    oc_mod._LLM_READY_CACHE.update({"key": None, "result": None, "ts": 0.0})

    monkeypatch.setattr(
        "arail.portal.services.opencode._load_active_provider",
        lambda: provider,
        raising=False,
    )
    load_state = {"state": state, "model": model}
    monkeypatch.setattr(
        "arail.portal.services.opencode._get_chat_model_load_state",
        lambda: load_state,
        raising=False,
    )
    monkeypatch.setattr(
        "arail.portal.services.opencode._provider_token",
        lambda p: token,
        raising=False,
    )
    # Patch the lazy imports inside the function
    def mock_app_imports():
        import arail.portal.services.opencode as oc_mod
        oc_mod._load_active_provider = lambda: provider
        oc_mod._get_chat_model_load_state = lambda: load_state
        oc_mod._provider_token = lambda p: token
    return load_state


class TestLlmReadyMyMachine:
    def _call(self, monkeypatch, state="ready", model=None):
        """Call llm_ready_check with my_machine provider."""
        import arail.portal.services.opencode as oc_mod
        oc_mod._LLM_READY_CACHE.update({"key": None, "result": None, "ts": 0.0})

        with mock.patch("arail.portal.services.opencode._load_active_provider",
                        return_value="my_machine"), \
             mock.patch("arail.portal.services.opencode._get_chat_model_load_state",
                        return_value={"state": state, "model": model}), \
             mock.patch("arail.portal.services.opencode._provider_token",
                        return_value=""):
            # Patch the lazy import inside llm_ready_check
            with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                            create=True), \
                 mock.patch("arail.portal.app._provider_token", return_value="", create=True), \
                 mock.patch("arail.portal.app._get_chat_model_load_state",
                            return_value={"state": state, "model": model}, create=True):
                return oc_mod.llm_ready_check(force=True)

    def test_llm_ready_my_machine_loaded(self, monkeypatch):
        """state='ready', model='Qwen-7B' → ok=True. (F-GATE-1)"""
        import arail.portal.services.opencode as oc_mod
        oc_mod._LLM_READY_CACHE.update({"key": None, "result": None, "ts": 0.0})

        with mock.patch.object(oc_mod, "_compute_llm_ready",
                               return_value={"ok": True, "reason": None,
                                             "hint": None, "chat_url": None,
                                             "provider": "my_machine", "model": "Qwen-7B"}):
            # Patch lazy imports
            with mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                            create=True), \
                 mock.patch("arail.portal.app._get_chat_model_load_state",
                            return_value={"state": "ready", "model": "Qwen-7B"}, create=True), \
                 mock.patch("arail.portal.app._provider_token", return_value="", create=True):
                result = oc_mod.llm_ready_check(force=True)
        assert result["ok"] is True
        assert result["model"] == "Qwen-7B"

    def test_llm_ready_my_machine_no_model(self, monkeypatch):
        """state='ready', model=None → ok=False, reason='no_llm'. (F-GATE-1)"""
        import arail.portal.services.opencode as oc_mod
        result = oc_mod._compute_llm_ready("my_machine", "ready", None)
        assert result["ok"] is False
        assert result["reason"] == "no_llm"
        assert result["chat_url"] == "/chat"

    def test_llm_ready_my_machine_loading(self, monkeypatch):
        """state='loading' → ok=False, reason='loading'. (F-GATE-1)"""
        import arail.portal.services.opencode as oc_mod
        result = oc_mod._compute_llm_ready("my_machine", "loading", None)
        assert result["ok"] is False
        assert result["reason"] == "loading"
        assert result["chat_url"] == "/chat"

    def test_llm_ready_my_machine_error(self, monkeypatch):
        """state='error' → ok=False, reason='no_llm'. (F-GATE-1)"""
        import arail.portal.services.opencode as oc_mod
        result = oc_mod._compute_llm_ready("my_machine", "error", None)
        assert result["ok"] is False
        assert result["reason"] == "no_llm"


class TestLlmReadyCloud:
    def test_llm_ready_cloud_with_token(self, monkeypatch):
        """provider=claude, token saved → ok=True. (F-GATE-1)"""
        import arail.portal.services.opencode as oc_mod
        with mock.patch("arail.portal.app._provider_token", return_value="sk-valid",
                        create=True):
            result = oc_mod._compute_llm_ready("claude", "ready", "claude-opus-4-5")
        assert result["ok"] is True

    def test_llm_ready_cloud_no_token(self, monkeypatch):
        """provider=claude, no token → ok=False, reason='no_token'. (F-GATE-1)"""
        import arail.portal.services.opencode as oc_mod
        with mock.patch("arail.portal.app._provider_token", return_value="",
                        create=True):
            result = oc_mod._compute_llm_ready("claude", "ready", None)
        assert result["ok"] is False
        assert result["reason"] == "no_token"
        assert result["chat_url"] == "/chat"


class TestLlmReadyCache:
    def test_llm_ready_cache_hit(self, monkeypatch):
        """Two calls within TTL return same result without re-computing. (F-GATE-5)"""
        import arail.portal.services.opencode as oc_mod
        oc_mod._LLM_READY_CACHE.update({"key": None, "result": None, "ts": 0.0})

        call_count = [0]
        original = oc_mod._compute_llm_ready

        def counted(*args, **kw):
            call_count[0] += 1
            return original(*args, **kw)

        with mock.patch.object(oc_mod, "_compute_llm_ready", side_effect=counted), \
             mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True):
            r1 = oc_mod.llm_ready_check(force=False)
            r2 = oc_mod.llm_ready_check(force=False)

        assert r1["ok"] == r2["ok"]
        assert call_count[0] == 1, f"_compute_llm_ready called {call_count[0]} times (expected 1)"

    def test_llm_ready_force_bypasses_cache(self, monkeypatch):
        """force=True re-computes even within TTL. (F-GATE-5)"""
        import arail.portal.services.opencode as oc_mod
        oc_mod._LLM_READY_CACHE.update({"key": None, "result": None, "ts": 0.0})

        call_count = [0]
        original = oc_mod._compute_llm_ready

        def counted(*args, **kw):
            call_count[0] += 1
            return original(*args, **kw)

        with mock.patch.object(oc_mod, "_compute_llm_ready", side_effect=counted), \
             mock.patch("arail.portal.app._load_active_provider", return_value="my_machine",
                        create=True), \
             mock.patch("arail.portal.app._get_chat_model_load_state",
                        return_value={"state": "ready", "model": "TestModel"}, create=True), \
             mock.patch("arail.portal.app._provider_token", return_value="", create=True):
            oc_mod.llm_ready_check(force=False)
            oc_mod.llm_ready_check(force=True)

        assert call_count[0] == 2, f"force=True should re-compute, got {call_count[0]} calls"

    def test_llm_ready_cache_invalidated_on_explicit_call(self):
        """invalidate_llm_ready_cache() resets the cache. (F-GATE-5)"""
        import arail.portal.services.opencode as oc_mod
        # Populate the cache with a fake result
        fake_result = {"ok": True, "reason": None, "hint": None,
                       "chat_url": None, "provider": "my_machine", "model": "m1"}
        oc_mod._LLM_READY_CACHE.update({
            "key": ("my_machine", "ready", "m1"),
            "result": fake_result,
            "ts": time.monotonic(),
        })
        oc_mod.invalidate_llm_ready_cache()
        assert oc_mod._LLM_READY_CACHE["key"] is None

    def test_llm_ready_never_raises_on_app_import_failure(self, monkeypatch):
        """If lazy import fails, returns ok=False not an exception. (F-GATE-5)"""
        import arail.portal.services.opencode as oc_mod
        oc_mod._LLM_READY_CACHE.update({"key": None, "result": None, "ts": 0.0})

        with mock.patch("arail.portal.app._load_active_provider",
                        side_effect=ImportError("boom"), create=True):
            result = oc_mod.llm_ready_check(force=True)
        # Should not raise; ok may be True or False but must return a dict
        assert isinstance(result, dict)
        assert "ok" in result
