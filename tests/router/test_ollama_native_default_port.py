"""Regression test for the dead-:1234 root cause.

MODEL_BACKEND=ollama_native with MODEL_API_BASE unset used to inherit
OpenAICompatBackend's LM Studio default (http://localhost:1234/v1), so every
plain ModelRouter() consumer (AutoResearch, all agents) hit a dead port while
Chat — which sets base_url explicitly via __new__ — worked. The backend now
defaults to the actual Ollama port.
"""

from __future__ import annotations

import pytest

from arail.router.backends import OllamaNativeBackend, OpenAICompatBackend
from arail.router.core import ModelRouter


@pytest.fixture(autouse=True)
def _model_env(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "ai-engineer:latest")
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    monkeypatch.delenv("OLLAMA_PORT", raising=False)


def test_plain_router_defaults_to_ollama_port():
    router = ModelRouter()
    assert router.backend_name == "ollama_native"
    assert router._backend.base_url == "http://127.0.0.1:11434/v1"
    assert router._backend.model_name == "ai-engineer:latest"


def test_explicit_model_api_base_still_wins(monkeypatch):
    monkeypatch.setenv("MODEL_API_BASE", "http://127.0.0.1:9999/v1")
    be = OllamaNativeBackend()
    assert be.base_url == "http://127.0.0.1:9999/v1"


def test_ollama_port_env_respected(monkeypatch):
    monkeypatch.setenv("OLLAMA_PORT", "21434")
    be = OllamaNativeBackend()
    assert be.base_url == "http://127.0.0.1:21434/v1"


def test_openai_compat_backend_unchanged():
    # The generic OpenAI-compat backend (LM Studio et al.) keeps its
    # documented :1234 default — only ollama_native was wrong.
    be = OpenAICompatBackend()
    assert be.base_url == "http://localhost:1234/v1"


def test_chat_gallery_new_path_unaffected():
    # The chat tab's __new__-based construction must keep working: no
    # __init__ side effects are required for a fully attribute-set instance.
    be = OllamaNativeBackend.__new__(OllamaNativeBackend)
    be.base_url = "http://127.0.0.1:11434/v1"
    be.model_name = "llama3.2:1b"
    be.api_key = "not-needed"
    assert be._ollama_root() == "http://127.0.0.1:11434"
    # complete() reads _num_ctx defensively even when never set (F-NEW).
    assert getattr(be, "_num_ctx", None) is None


def test_init_resolves_num_ctx():
    be = OllamaNativeBackend()
    assert hasattr(be, "_num_ctx")   # set (possibly None) by __init__
    assert be.backend_name == "ollama:native"
