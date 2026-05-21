"""B2 fix-loop integration tests: OllamaNativeBackend reachable from _get_runtime_backend.

Sprint: 2026-05-18-provider-aware-chat-dropdown, fix-loop pass.

The prior sprint's unit tests proved OllamaNativeBackend works in isolation.
These tests prove it is REACHABLE from the dispatch path, and that a ctx
override set for an Ollama model actually propagates to options.num_ctx in
the dispatched request body.

This is the reachability gap that gave the unit tests false confidence (REVIEW.md B2).
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_runtime_backend_fresh(monkeypatch, runtime: str, model_id: str):
    """Call _get_runtime_backend with a cleared cache so we build a fresh backend."""
    from arail.portal import app as portal_app

    # Clear the cache so this call always builds fresh
    portal_app._RUNTIME_BACKEND_CACHE.clear()

    return portal_app._get_runtime_backend(runtime, model_id)


# ---------------------------------------------------------------------------
# B2-INT-1: _get_runtime_backend("ollama", ...) returns OllamaNativeBackend
# ---------------------------------------------------------------------------

def test_dispatch_ollama_returns_ollama_native_backend(monkeypatch):
    """B2 reachability: _get_runtime_backend('ollama', ...) must build
    OllamaNativeBackend, not OpenAICompatBackend."""
    from arail.router.backends import OllamaNativeBackend

    be = _get_runtime_backend_fresh(monkeypatch, "ollama", "ai-eng:latest")

    assert isinstance(be, OllamaNativeBackend), (
        f"Expected OllamaNativeBackend, got {type(be).__name__}. "
        "B2: ollama dispatch wiring is broken."
    )


def test_dispatch_ollama_backend_name_is_native(monkeypatch):
    """Dispatched ollama backend must identify itself as ollama:native."""
    be = _get_runtime_backend_fresh(monkeypatch, "ollama", "ai-eng:latest")

    assert be.backend_name == "ollama:native", (
        f"Expected backend_name='ollama:native', got {be.backend_name!r}"
    )


def test_dispatch_mlx_openai_still_returns_openai_compat(monkeypatch):
    """Non-ollama runtimes must still use OpenAICompatBackend (no regression)."""
    from arail.router.backends import OpenAICompatBackend, OllamaNativeBackend

    be = _get_runtime_backend_fresh(monkeypatch, "mlx-openai", "some-mlx-model")

    assert isinstance(be, OpenAICompatBackend), (
        f"mlx-openai should use OpenAICompatBackend, got {type(be).__name__}"
    )
    assert not isinstance(be, OllamaNativeBackend), (
        "mlx-openai must NOT be an OllamaNativeBackend"
    )


# ---------------------------------------------------------------------------
# B2-INT-2: ctx override set for an Ollama model flows into options.num_ctx
# ---------------------------------------------------------------------------

def test_ctx_override_flows_into_num_ctx_for_ollama(monkeypatch):
    """B2 end-to-end: when ARAIL_MODEL_CTX_OVERRIDES has an entry for model_id,
    the dispatched OllamaNativeBackend must have _num_ctx set, and a call to
    complete() must include options.num_ctx in the POST body.

    This proves the full path: set-ctx → resolve override → build backend → dispatch.
    """
    from arail.router.backends import OllamaNativeBackend

    model_id = "ai-eng:latest"
    expected_ctx = 16384

    # Plant a ctx override in the environment (as _persist_ctx_override would)
    overrides = {model_id: expected_ctx}
    monkeypatch.setenv("ARAIL_MODEL_CTX_OVERRIDES", json.dumps(overrides))

    be = _get_runtime_backend_fresh(monkeypatch, "ollama", model_id)

    assert isinstance(be, OllamaNativeBackend)
    assert be._num_ctx == expected_ctx, (
        f"Expected _num_ctx={expected_ctx}, got {be._num_ctx!r}. "
        "ctx override is not flowing into the dispatched backend."
    )

    # Now confirm complete() actually sends options.num_ctx in the POST body
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "message": {"role": "assistant", "content": "hello"},
        "model": model_id,
        "done": True,
    }
    be._session = MagicMock()
    be._session.post.return_value = fake_resp

    be.complete("test prompt", max_tokens=50)

    call_kwargs = be._session.post.call_args[1]
    body = call_kwargs.get("json", {})
    options = body.get("options", {})
    assert options.get("num_ctx") == expected_ctx, (
        f"options.num_ctx={options.get('num_ctx')!r} in POST body, expected {expected_ctx}. "
        "ctx override does not reach options.num_ctx."
    )


def test_no_ctx_override_means_no_num_ctx_in_dispatch(monkeypatch):
    """When no ctx override is set, the dispatched OllamaNativeBackend must have
    _num_ctx=None and complete() must omit options.num_ctx (preserve today's behavior)."""
    from arail.router.backends import OllamaNativeBackend

    model_id = "qwen3:8b"

    # Ensure no override env
    monkeypatch.delenv("ARAIL_MODEL_CTX_OVERRIDES", raising=False)

    be = _get_runtime_backend_fresh(monkeypatch, "ollama", model_id)

    assert isinstance(be, OllamaNativeBackend)
    assert be._num_ctx is None, (
        f"Expected _num_ctx=None when no override set, got {be._num_ctx!r}"
    )

    # Confirm complete() does NOT include num_ctx in body
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "message": {"role": "assistant", "content": "hi"},
        "model": model_id,
        "done": True,
    }
    be._session = MagicMock()
    be._session.post.return_value = fake_resp

    be.complete("test", max_tokens=10)

    call_kwargs = be._session.post.call_args[1]
    body = call_kwargs.get("json", {})
    options = body.get("options", {})
    assert "num_ctx" not in options, (
        f"options.num_ctx must be absent when no override, got options={options!r}"
    )


def test_dispatch_posts_to_api_chat_not_v1(monkeypatch):
    """B2 integration: the dispatched ollama backend must POST to /api/chat
    (root), not /v1/chat/completions (the shim that silently drops num_ctx)."""
    from arail.router.backends import OllamaNativeBackend

    be = _get_runtime_backend_fresh(monkeypatch, "ollama", "ai-eng:latest")
    assert isinstance(be, OllamaNativeBackend)

    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "message": {"role": "assistant", "content": "hi"},
        "model": "ai-eng:latest",
        "done": True,
    }
    be._session = MagicMock()
    be._session.post.return_value = fake_resp

    be.complete("hello", max_tokens=10)

    url_called = be._session.post.call_args[0][0]
    assert "/api/chat" in url_called, (
        f"Dispatched ollama backend must POST to /api/chat, got URL: {url_called!r}"
    )
    assert "/v1/" not in url_called, (
        f"Dispatched ollama backend must NOT POST to /v1/ (shim drops num_ctx), got: {url_called!r}"
    )


def test_dispatch_ollama_cache_key_is_tuple_runtime_model(monkeypatch):
    """Cache key is (runtime, model_id) — verify the dispatched backend is cached."""
    from arail.portal import app as portal_app

    model_id = "ai-eng:latest"
    portal_app._RUNTIME_BACKEND_CACHE.clear()

    be1 = portal_app._get_runtime_backend("ollama", model_id)
    be2 = portal_app._get_runtime_backend("ollama", model_id)

    assert be1 is be2, "Same (runtime, model_id) must return the cached backend instance"
