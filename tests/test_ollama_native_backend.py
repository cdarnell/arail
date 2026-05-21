"""Unit tests for OllamaNativeBackend.

Sprint: 2026-05-18-provider-aware-chat-dropdown, Phase B step 5.

Covers:
  F-NEW: build via __new__, _num_ctx set by caller; complete reads defensively.
  F-OLLAMA-SHIM: POSTs to /api/chat (root), NOT /v1/chat/completions.
  num_ctx in body iff _num_ctx is set.
  Parses Ollama message.content response.
  Returns ModelResponse(backend="ollama_native").
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


def _build_native_backend(base_url="http://127.0.0.1:11434/v1",
                           model_name="ai-eng:latest",
                           num_ctx=None):
    """Build an OllamaNativeBackend via __new__ (the F-NEW path)."""
    from arail.router.backends import OllamaNativeBackend
    import requests as _req

    be = OllamaNativeBackend.__new__(OllamaNativeBackend)
    mock_session = MagicMock()
    be._session = mock_session
    be.base_url = base_url
    be.model_name = model_name
    be.api_key = "not-needed"
    be.backend_name = "ollama:native"
    be._num_ctx = num_ctx   # None = not set; int = use it
    return be, mock_session


def _fake_ollama_response(content="hello from ollama"):
    """Build a minimal Ollama /api/chat success response."""
    fake_resp = MagicMock()
    fake_resp.raise_for_status.return_value = None
    fake_resp.json.return_value = {
        "message": {"role": "assistant", "content": content},
        "model": "ai-eng:latest",
        "done": True,
    }
    return fake_resp


# ---------------------------------------------------------------------------
# F-OLLAMA-SHIM: must POST to /api/chat (root), not /v1/chat/completions
# ---------------------------------------------------------------------------

def test_ollama_native_posts_to_api_chat_not_v1():
    """F-OLLAMA-SHIM: complete() must POST to {root}/api/chat, never to /v1/."""
    be, mock_session = _build_native_backend(
        base_url="http://127.0.0.1:11434/v1"
    )
    mock_session.post.return_value = _fake_ollama_response()

    be.complete("test prompt", max_tokens=10)

    url_called = mock_session.post.call_args[0][0]
    assert "/api/chat" in url_called, f"Expected /api/chat in URL, got: {url_called!r}"
    assert "/v1/" not in url_called, f"Must not POST to /v1/ path, got: {url_called!r}"


def test_ollama_native_url_strips_v1_suffix():
    """Root is derived by stripping trailing /v1 from base_url."""
    be, mock_session = _build_native_backend(
        base_url="http://127.0.0.1:11434/v1"
    )
    mock_session.post.return_value = _fake_ollama_response()

    be.complete("test prompt", max_tokens=10)

    url_called = mock_session.post.call_args[0][0]
    assert url_called == "http://127.0.0.1:11434/api/chat", (
        f"Expected http://127.0.0.1:11434/api/chat, got: {url_called!r}"
    )


# ---------------------------------------------------------------------------
# F-NEW: build via __new__; _num_ctx set by caller; no AttributeError
# ---------------------------------------------------------------------------

def test_ollama_native_new_path_no_attribute_error_with_num_ctx():
    """F-NEW: building via __new__ and setting _num_ctx must not AttributeError."""
    be, mock_session = _build_native_backend(num_ctx=8192)
    mock_session.post.return_value = _fake_ollama_response()

    # Must not raise
    result = be.complete("hello", max_tokens=10)
    assert result is not None


def test_ollama_native_new_path_no_attribute_error_without_num_ctx():
    """F-NEW: building via __new__ with _num_ctx=None must not AttributeError."""
    be, mock_session = _build_native_backend(num_ctx=None)
    mock_session.post.return_value = _fake_ollama_response()

    result = be.complete("hello", max_tokens=10)
    assert result is not None


def test_ollama_native_getattr_defensive_reads_num_ctx():
    """F-NEW: complete() reads _num_ctx via getattr defensively.
    Even if _num_ctx was never set (partial __new__ build), no AttributeError."""
    from arail.router.backends import OllamaNativeBackend
    import requests as _req

    be = OllamaNativeBackend.__new__(OllamaNativeBackend)
    mock_session = MagicMock()
    be._session = mock_session
    be.base_url = "http://127.0.0.1:11434/v1"
    be.model_name = "ai-eng:latest"
    be.api_key = "not-needed"
    be.backend_name = "ollama:native"
    # Deliberately do NOT set _num_ctx — simulate a partial build

    mock_session.post.return_value = _fake_ollama_response()
    result = be.complete("hello", max_tokens=5)
    assert result is not None  # no AttributeError


# ---------------------------------------------------------------------------
# num_ctx in body iff _num_ctx is set
# ---------------------------------------------------------------------------

def test_ollama_native_num_ctx_in_body_when_set():
    """When _num_ctx is set, options.num_ctx must appear in the POST body."""
    be, mock_session = _build_native_backend(num_ctx=8192)
    mock_session.post.return_value = _fake_ollama_response()

    be.complete("hello", max_tokens=10)

    body = mock_session.post.call_args[1]["json"]
    assert "options" in body, "options key missing from body"
    assert body["options"].get("num_ctx") == 8192


def test_ollama_native_num_ctx_absent_from_body_when_not_set():
    """When _num_ctx is None, options.num_ctx must NOT appear in the POST body."""
    be, mock_session = _build_native_backend(num_ctx=None)
    mock_session.post.return_value = _fake_ollama_response()

    be.complete("hello", max_tokens=10)

    body = mock_session.post.call_args[1]["json"]
    options = body.get("options", {})
    assert "num_ctx" not in options, (
        f"num_ctx must be absent when _num_ctx is None, got options={options!r}"
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def test_ollama_native_parses_message_content():
    """complete() parses response.message.content correctly."""
    be, mock_session = _build_native_backend()
    mock_session.post.return_value = _fake_ollama_response("ollama says hello")

    result = be.complete("hi", max_tokens=10)
    assert result.text == "ollama says hello"


def test_ollama_native_returns_model_response_backend_name():
    """complete() returns ModelResponse with backend='ollama_native'."""
    be, mock_session = _build_native_backend()
    mock_session.post.return_value = _fake_ollama_response()

    result = be.complete("hi", max_tokens=10)
    assert result.backend == "ollama_native"


def test_ollama_native_stream_false_in_body():
    """Body must include stream:false (non-streaming complete call)."""
    be, mock_session = _build_native_backend()
    mock_session.post.return_value = _fake_ollama_response()

    be.complete("hi", max_tokens=10)

    body = mock_session.post.call_args[1]["json"]
    assert body.get("stream") is False


# ---------------------------------------------------------------------------
# BACKEND_MAP registration
# ---------------------------------------------------------------------------

def test_ollama_native_backend_registered_in_backend_map():
    """OllamaNativeBackend must be in BACKEND_MAP as 'ollama_native'."""
    from arail.router.backends import BACKEND_MAP, OllamaNativeBackend
    assert "ollama_native" in BACKEND_MAP
    assert BACKEND_MAP["ollama_native"] is OllamaNativeBackend
