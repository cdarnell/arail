"""OllamaNativeBackend sends keep_alive so Tier 0 stays resident."""

from __future__ import annotations

import pytest

from arail.router.backends import OllamaNativeBackend


class _CapturingSession:
    def __init__(self):
        self.bodies = []

    def post(self, url, headers=None, json=None, timeout=None, stream=False):
        self.bodies.append(json)

        class _R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"message": {"content": "ok"}, "eval_count": 1,
                        "model": "m"}
        return _R()


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setenv("MODEL_NAME", "ai-engineer:latest")
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    be = OllamaNativeBackend()
    be._session = _CapturingSession()
    return be


def test_default_keep_alive_2h(backend):
    backend.complete("hi", max_tokens=8)
    assert backend._session.bodies[0]["keep_alive"] == "2h"


def test_empty_env_omits_keep_alive(backend, monkeypatch):
    monkeypatch.setenv("ARAIL_OLLAMA_KEEP_ALIVE", "")
    backend.complete("hi", max_tokens=8)
    assert "keep_alive" not in backend._session.bodies[0]


def test_pin_forever_passthrough(backend, monkeypatch):
    monkeypatch.setenv("ARAIL_OLLAMA_KEEP_ALIVE", "-1")
    backend.complete("hi", max_tokens=8)
    assert backend._session.bodies[0]["keep_alive"] == "-1"


def test_chat_gallery_new_path_gets_keep_alive_too(monkeypatch):
    # __new__-constructed instances (chat gallery) use the same staticmethod.
    be = OllamaNativeBackend.__new__(OllamaNativeBackend)
    be.base_url = "http://127.0.0.1:11434/v1"
    be.model_name = "llama3.2:1b"
    be.api_key = "not-needed"
    be._session = _CapturingSession()
    be.complete("hi", max_tokens=8)
    assert be._session.bodies[0]["keep_alive"] == "2h"
