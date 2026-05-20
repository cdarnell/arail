"""Tests for POST /api/chat/models/set-ctx.

Sprint: 2026-05-18-provider-aware-chat-dropdown, Phase C step 9.

Covers F-VALIDATE, F-CACHE, and the relaxed local-id gate.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _make_client(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# F-VALIDATE — relaxed local-id gate accepts Ollama ids, rejects cloud + traversal
# ---------------------------------------------------------------------------

def test_set_ctx_accepts_ollama_id(monkeypatch, tmp_path):
    """F-VALIDATE: an Ollama-installed model id must be accepted."""
    client = _make_client(monkeypatch)
    ollama_model = "qwen3:8b"

    # Patch detect_installed_models to include the ollama id
    with patch("arail.chat.detect_installed_models",
               return_value=[{"id": ollama_model, "runtime": "ollama"}]), \
         patch("arail.portal.app._persist_ctx_override", return_value={ollama_model: 8192}):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": ollama_model, "ctx": 8192},
        )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True, f"Ollama id rejected: {body!r}"


def test_set_ctx_rejects_cloud_model_id(monkeypatch):
    """F-VALIDATE: a cloud model id (not in local install) must be rejected."""
    client = _make_client(monkeypatch)

    with patch("arail.chat.detect_installed_models", return_value=[]):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": "claude-opus-4-7", "ctx": 8192},
        )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False, f"Cloud model id accepted (should reject): {body!r}"


def test_set_ctx_rejects_path_traversal_dotdot(monkeypatch):
    """F-VALIDATE: path traversal with .. must be rejected."""
    client = _make_client(monkeypatch)

    r = client.post(
        "/api/chat/models/set-ctx",
        json={"model_id": "../etc/passwd", "ctx": 4096},
    )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False, f"Path traversal accepted: {body!r}"
    assert "traversal" in body.get("error", "").lower() or "invalid" in body.get("error", "").lower()


def test_set_ctx_rejects_path_traversal_slash(monkeypatch):
    """F-VALIDATE: model_id with / must be rejected."""
    client = _make_client(monkeypatch)

    r = client.post(
        "/api/chat/models/set-ctx",
        json={"model_id": "some/path/model", "ctx": 4096},
    )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False


def test_set_ctx_rejects_ctx_below_256(monkeypatch):
    """ctx < 256 must be rejected."""
    client = _make_client(monkeypatch)
    ollama_model = "qwen3:8b"

    with patch("arail.chat.detect_installed_models",
               return_value=[{"id": ollama_model, "runtime": "ollama"}]):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": ollama_model, "ctx": 10},
        )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False


def test_set_ctx_rejects_ctx_above_1m(monkeypatch):
    """ctx > 1,000,000 must be rejected."""
    client = _make_client(monkeypatch)
    ollama_model = "qwen3:8b"

    with patch("arail.chat.detect_installed_models",
               return_value=[{"id": ollama_model, "runtime": "ollama"}]):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": ollama_model, "ctx": 2_000_000},
        )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False


# ---------------------------------------------------------------------------
# F-CACHE — set-ctx purges _RUNTIME_BACKEND_CACHE for the model
# ---------------------------------------------------------------------------

def test_set_ctx_purges_runtime_backend_cache(monkeypatch):
    """F-CACHE: after set-ctx, _RUNTIME_BACKEND_CACHE entries for model must be gone."""
    client = _make_client(monkeypatch)
    ollama_model = "qwen3:8b"

    from arail.portal import app as portal_app

    # Plant a stale cache entry
    portal_app._RUNTIME_BACKEND_CACHE[("ollama", ollama_model)] = object()
    portal_app._RUNTIME_BACKEND_CACHE[("mlx-openai", ollama_model)] = object()

    with patch("arail.chat.detect_installed_models",
               return_value=[{"id": ollama_model, "runtime": "ollama"}]), \
         patch("arail.portal.app._persist_ctx_override", return_value={ollama_model: 8192}):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": ollama_model, "ctx": 8192},
        )

    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True

    # Cache entries for this model must be purged
    remaining = [k for k in portal_app._RUNTIME_BACKEND_CACHE if k[1] == ollama_model]
    assert not remaining, f"Cache entries remain after set-ctx: {remaining}"


def test_set_ctx_sets_models_scan_ts_to_zero(monkeypatch):
    """F-CACHE: _MODELS_SCAN_TS must be reset to 0.0 after set-ctx."""
    client = _make_client(monkeypatch)
    ollama_model = "ai-eng:latest"

    from arail.portal import app as portal_app
    portal_app._MODELS_SCAN_TS = 999.0  # set to a non-zero value

    with patch("arail.chat.detect_installed_models",
               return_value=[{"id": ollama_model, "runtime": "ollama"}]), \
         patch("arail.portal.app._persist_ctx_override", return_value={ollama_model: 4096}):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": ollama_model, "ctx": 4096},
        )

    assert r.status_code == 200
    assert portal_app._MODELS_SCAN_TS == 0.0, (
        f"_MODELS_SCAN_TS not reset: {portal_app._MODELS_SCAN_TS}"
    )


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

def test_set_ctx_response_shape(monkeypatch):
    """Successful set-ctx must return {ok, model_id, ctx, ctx_overrides}."""
    client = _make_client(monkeypatch)
    ollama_model = "qwen3:8b"

    with patch("arail.chat.detect_installed_models",
               return_value=[{"id": ollama_model, "runtime": "ollama"}]), \
         patch("arail.portal.app._persist_ctx_override",
               return_value={ollama_model: 8192}):
        r = client.post(
            "/api/chat/models/set-ctx",
            json={"model_id": ollama_model, "ctx": 8192},
        )

    body = r.json()
    assert body.get("ok") is True
    assert body.get("model_id") == ollama_model
    assert body.get("ctx") == 8192
    assert "ctx_overrides" in body
