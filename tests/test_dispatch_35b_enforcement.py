"""Test the server-side 35B dispatch override (architect MUST-HIT A1).

Sprint: 2026-05-03-models-admin-dashboard

Headline scenario:
  Client posts to `/api/chat` with `backend: "mlx"` (a non-Deep backend) AND a
  model where `must_stream() == True` (e.g. Llama-3.1-70B). Server MUST silently
  override and route through the AirLLM Deep backend, NOT mlx. The client's
  backend selection is advisory; the SERVER decides.

We don't actually invoke a real model — we mock both the Deep backend and the
primary router and assert which one was called.
"""

from __future__ import annotations

import asyncio
import importlib
import os
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fakes — minimal stand-ins for the Deep / primary backends
# ---------------------------------------------------------------------------

@dataclass
class _FakeResponse:
    text: str = "ok"
    backend: str = "fake"
    model: str = "fake-model"
    latency_ms: float = 1.0
    tokens_used: int = 1


class _FakeDeepBackend:
    """Stand-in for the AirLLM optional backend."""
    backend_name = "airllm"
    model_name = "Llama-3.1-70B"

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt, max_tokens=None, temperature=None, top_p=None):
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return _FakeResponse(backend="airllm", model="Llama-3.1-70B")


class _FakePrimaryBackend:
    backend_name = "mlx"
    model_name = "mlx-default-7B"


class _FakePrimaryRouter:
    backend_name = "mlx"
    _backend = _FakePrimaryBackend()

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt, max_tokens=None, temperature=None, top_p=None):
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return _FakeResponse(backend="mlx", model="mlx-default-7B")


@pytest.fixture()
def patched_app(monkeypatch):
    from arail.portal import app as app_mod

    fake_deep = _FakeDeepBackend()
    fake_router = _FakePrimaryRouter()

    monkeypatch.setattr(app_mod, "_get_optional_chat_backend",
                        lambda name: fake_deep if name == "airllm" else (_ for _ in ()).throw(ValueError(name)))
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: fake_router)
    monkeypatch.setattr(app_mod, "_is_airllm_installed", lambda: True)
    return app_mod, fake_deep, fake_router


# ---------------------------------------------------------------------------
# A1 — Direct API bypass with backend=mlx + 70B model → still routed to Deep
# ---------------------------------------------------------------------------

def test_chat_with_backend_mlx_and_70b_model_routes_to_deep(patched_app, monkeypatch):
    """A1 (HEADLINE): client lies about backend, server still routes via AirLLM."""
    app_mod, fake_deep, fake_router = patched_app
    # Ensure the candidate model is over the floor when picked from MODEL_NAME too
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    client = TestClient(app_mod.app)
    r = client.post("/api/chat", json={
        "message": "hello",
        "backend": "mlx",  # client claims they want mlx (non-Deep)
        "model": "Llama-3.1-70B",  # but the model is 70B → must_stream=True
    })
    assert r.status_code == 200, r.text
    body = r.json()
    # The server-side override is what matters. Two assertions:
    # 1. The Deep backend's complete() was called (not the primary router's)
    assert len(fake_deep.calls) == 1, "Deep backend was NOT invoked despite >35B model"
    assert len(fake_router.calls) == 0, "Primary router was invoked — override leaked"
    # 2. The response surfaces deep=True, signaling the override happened
    assert body.get("deep") is True
    # 3. Response backend is the Deep one
    assert body.get("backend") == "airllm"


def test_chat_with_no_backend_and_70b_model_routes_to_deep(patched_app, monkeypatch):
    """Variant: backend not set at all + 70B model → still Deep."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    r = TestClient(app_mod.app).post("/api/chat", json={
        "message": "hello", "model": "Llama-3.1-70B",
    })
    assert r.status_code == 200, r.text
    assert len(fake_deep.calls) == 1
    assert len(fake_router.calls) == 0
    assert r.json()["deep"] is True


def test_chat_with_llama4_maverick_routes_to_deep(patched_app, monkeypatch):
    """Llama-4 Maverick (400B via override) also forces Deep regardless of backend."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    r = TestClient(app_mod.app).post("/api/chat", json={
        "message": "hello",
        "backend": "mlx",
        "model": "Llama-4-Maverick-17B-128E-Instruct-fp8",
    })
    assert r.status_code == 200, r.text
    assert len(fake_deep.calls) == 1
    assert len(fake_router.calls) == 0


def test_chat_with_8b_model_does_not_force_deep(patched_app, monkeypatch):
    """Inverse: a small model should NOT force Deep — primary router gets it."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    r = TestClient(app_mod.app).post("/api/chat", json={
        "message": "hello",
        "model": "Qwen3-8B-4bit",
    })
    assert r.status_code == 200, r.text
    # Small model + no backend → goes through the primary router
    assert len(fake_deep.calls) == 0
    assert len(fake_router.calls) == 1
    assert r.json().get("deep") is False


def test_chat_dispatch_override_emits_activity_log(patched_app, monkeypatch):
    """The override path emits an info activity_log line for audit trails."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    captured = []
    real_emit = app_mod.activity_log.emit

    def _spy(source, message, level="info"):
        captured.append((source, message, level))
        return real_emit(source, message, level)

    monkeypatch.setattr(app_mod.activity_log, "emit", _spy)

    r = TestClient(app_mod.app).post("/api/chat", json={
        "message": "hello",
        "backend": "mlx",
        "model": "Llama-3.1-70B",
    })
    assert r.status_code == 200
    # Find a chat-source emit that mentions "35B+" — that's the override audit line
    matches = [m for src, m, lvl in captured if src == "chat" and "35B+" in m]
    assert matches, f"expected an activity_log line about 35B+ override; got: {captured}"


# ---------------------------------------------------------------------------
# Streaming path inherits the same override (A7)
# ---------------------------------------------------------------------------

def test_stream_path_also_routes_to_deep_for_70b(patched_app, monkeypatch):
    """A7: _run_chat_completion_stream also calls _prepare_chat_context, so
    the override is inherited for free. We exercise the dispatch logic by
    invoking the helper directly with backend=mlx + a 70B model and asserting
    the prepared context routes through Deep."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    ctx = app_mod._prepare_chat_context(
        message="hi", history=[],
        backend_override="mlx",
        model_override="Llama-3.1-70B",
    )
    # Should not produce an error_result for an installed AirLLM
    assert ctx.get("error_result") is None
    # Deep backend should be the chosen one
    assert ctx.get("deep_backend") is fake_deep
    assert ctx["wants_deep"] is True
    assert ctx["optional_backend_name"] == "airllm"


def test_stream_path_does_not_override_for_8b_model(patched_app, monkeypatch):
    """The override is a one-way bump: small model is NOT bumped."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Qwen3-8B-4bit")

    ctx = app_mod._prepare_chat_context(
        message="hi", history=[],
        backend_override=None,
        model_override="Qwen3-8B-4bit",
    )
    assert ctx.get("deep_backend") is None
    assert ctx["wants_deep"] is False


# ---------------------------------------------------------------------------
# AirLLM not installed (A3) — the override path still degrades gracefully
# ---------------------------------------------------------------------------

def test_override_when_airllm_missing_returns_friendly_error(patched_app, monkeypatch):
    """A3: AirLLM not installed → server emits an error_result, NOT a 5xx."""
    app_mod, fake_deep, fake_router = patched_app

    def _raise(name):
        raise ImportError(f"{name} backend not installed (test)")

    monkeypatch.setattr(app_mod, "_get_optional_chat_backend", _raise)

    r = TestClient(app_mod.app).post("/api/chat", json={
        "message": "hello",
        "backend": "mlx",
        "model": "Llama-3.1-70B",
    })
    # 200 + readable reply (per _optional_backend_error_result contract)
    assert r.status_code == 200
    body = r.json()
    assert "reply" in body
    # Either reply or error mentions install / AirLLM / not installed
    text = (body.get("reply") or "") + " " + (body.get("error") or "")
    assert ("not installed" in text.lower()
            or "airllm" in text.lower()
            or "upgrade" in text.lower())


# ---------------------------------------------------------------------------
# MODEL_NAME env var fallback when no explicit model passed
# ---------------------------------------------------------------------------

def test_override_via_model_name_env_var(patched_app, monkeypatch):
    """If no model is passed and MODEL_NAME is a 70B, dispatch routes to Deep."""
    app_mod, fake_deep, fake_router = patched_app
    monkeypatch.setenv("MODEL_NAME", "Llama-3.1-70B")

    ctx = app_mod._prepare_chat_context(
        message="hi", history=[],
        backend_override=None,
        model_override=None,
    )
    assert ctx["wants_deep"] is True
    assert ctx["optional_backend_name"] == "airllm"
