"""Tests for POST /api/chat/default + _apply_chat_defaults.

Sprint: 2026-05-18-provider-aware-chat-dropdown, Phase C step 10.

Covers F-DEFAULT-LEAK, clear path, per-message wins (A8).
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _make_client(monkeypatch, lab_mode="hybrid"):
    monkeypatch.setenv("LAB_MODE", lab_mode)
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# POST /api/chat/default — set path
# ---------------------------------------------------------------------------

def test_chat_default_set_local_ok(monkeypatch, isolated_secrets):
    """Setting a local (my_machine) default is always allowed."""
    client = _make_client(monkeypatch, lab_mode="airgapped")
    r = client.post(
        "/api/chat/default",
        json={"provider": "my_machine", "model": "qwen3:8b", "runtime": "ollama"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("provider") == "my_machine"


def test_chat_default_set_cloud_while_airgapped_refused(monkeypatch, isolated_secrets):
    """F-DEFAULT-LEAK: setting a cloud default while airgapped must be refused."""
    client = _make_client(monkeypatch, lab_mode="airgapped")
    r = client.post(
        "/api/chat/default",
        json={"provider": "claude", "model": "claude-opus-4-7", "runtime": "claude"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is False
    assert "airgapped" in body.get("error", "").lower()


def test_chat_default_set_cloud_in_hybrid_ok(monkeypatch, isolated_secrets):
    """Setting a cloud default in hybrid mode is allowed."""
    client = _make_client(monkeypatch, lab_mode="hybrid")
    r = client.post(
        "/api/chat/default",
        json={"provider": "claude", "model": "claude-sonnet-4-20250514", "runtime": "claude"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True


# ---------------------------------------------------------------------------
# POST /api/chat/default — clear path
# ---------------------------------------------------------------------------

def test_chat_default_clear(monkeypatch, isolated_secrets):
    """Clear removes ARAIL_CHAT_DEFAULT_MODEL from env."""
    monkeypatch.setenv("ARAIL_CHAT_DEFAULT_MODEL",
                       json.dumps({"model": "qwen3:8b", "runtime": "ollama"}))
    client = _make_client(monkeypatch)
    r = client.post("/api/chat/default", json={"clear": True})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("cleared") is True


# ---------------------------------------------------------------------------
# _apply_chat_defaults — unit tests
# ---------------------------------------------------------------------------

def test_apply_chat_defaults_per_message_wins(monkeypatch):
    """A8: if all three are provided, _apply_chat_defaults returns them unchanged."""
    monkeypatch.setenv("ARAIL_CHAT_DEFAULT_MODEL",
                       json.dumps({"model": "stored-model", "runtime": "stored-runtime"}))
    monkeypatch.setenv("COMPUTE_SOURCE", "stored-provider")

    from arail.portal.app import _apply_chat_defaults
    b, m, r = _apply_chat_defaults("my-backend", "my-model", "my-runtime")
    assert b == "my-backend"
    assert m == "my-model"
    assert r == "my-runtime"


def test_apply_chat_defaults_fills_blanks(monkeypatch):
    """Blanks (None) are filled from the stored default."""
    monkeypatch.setenv("ARAIL_CHAT_DEFAULT_MODEL",
                       json.dumps({"model": "qwen3:8b", "runtime": "ollama"}))
    monkeypatch.setenv("COMPUTE_SOURCE", "my_machine")
    monkeypatch.setenv("LAB_MODE", "hybrid")

    from arail.portal.app import _apply_chat_defaults
    b, m, r = _apply_chat_defaults(None, None, None)
    assert m == "qwen3:8b"
    assert r == "ollama"


def test_apply_chat_defaults_drops_cloud_default_when_airgapped(monkeypatch):
    """F-DEFAULT-LEAK: stored cloud default dropped when lab is airgapped."""
    monkeypatch.setenv("ARAIL_CHAT_DEFAULT_MODEL",
                       json.dumps({"model": "claude-opus-4-7", "runtime": "claude"}))
    monkeypatch.setenv("COMPUTE_SOURCE", "claude")
    monkeypatch.setenv("LAB_MODE", "airgapped")

    from arail.portal.app import _apply_chat_defaults, _CLOUD_PROVIDERS
    assert "claude" in _CLOUD_PROVIDERS  # sanity

    b, m, r = _apply_chat_defaults(None, None, None)
    # Cloud default must be dropped; fallback to my_machine or None
    assert m not in ("claude-opus-4-7",), (
        f"F-DEFAULT-LEAK: cloud model leaked through airgap: {m!r}"
    )
    assert b not in _CLOUD_PROVIDERS, (
        f"F-DEFAULT-LEAK: cloud backend leaked through airgap: {b!r}"
    )


def test_apply_chat_defaults_no_stored_default_returns_original(monkeypatch):
    """If no default is stored, return the original values unchanged."""
    monkeypatch.delenv("ARAIL_CHAT_DEFAULT_MODEL", raising=False)
    monkeypatch.setenv("LAB_MODE", "hybrid")

    from arail.portal.app import _apply_chat_defaults
    b, m, r = _apply_chat_defaults(None, "my-model", "my-runtime")
    assert m == "my-model"
    assert r == "my-runtime"


def test_apply_chat_defaults_bad_json_returns_original(monkeypatch):
    """Bad JSON in ARAIL_CHAT_DEFAULT_MODEL — must not raise, return original."""
    monkeypatch.setenv("ARAIL_CHAT_DEFAULT_MODEL", "NOT VALID JSON {{{")

    from arail.portal.app import _apply_chat_defaults
    b, m, r = _apply_chat_defaults(None, None, None)
    # Should return the originals (all None) without raising
    assert b is None
    assert m is None
    assert r is None
