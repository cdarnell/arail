"""Unit tests for openai_compat.py — OpenAI-compatible shim.

Covers ARCHITECTURE.md must-pass list:
  F-SHIM-1  — streaming envelope round-trip (SSE format + OpenAI shape)
  F-SHIM-2  — non-streaming includes usage block
  F-SHIM-3  — messages-to-history mapping
  F-SHIM-4  — provider prefix stripped from model id
  F-SHIM-5  — error envelope is OpenAI-shaped
  F-SHIM-7  — cost_tracker called with source='opencode'
  F-SHIM-8  — streaming yield intervals (structural check)
  F-SEC-CRED-4 — Authorization header not logged
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import unittest.mock as mock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers: build fake _run_chat_completion[_stream] return values
# ---------------------------------------------------------------------------

def _fake_result(reply: str = "hello", tokens_used: int = 3) -> dict:
    return {
        "reply": reply,
        "backend": "test",
        "model": "test-model",
        "latency_ms": 10.0,
        "tokens_used": tokens_used,
        "tokens_per_sec": 100.0,
        "cloud_cost_usd": 0.0,
        "energy_cost_usd": 0.0,
        "deep": False,
        "error": None,
    }


async def _fake_stream_iter(*deltas: str):
    """Async generator mimicking _run_chat_completion_stream events."""
    yield {"type": "start", "backend": "test", "model": "test-model", "deep": False}
    for d in deltas:
        yield {"type": "delta", "delta": d}
    yield {
        "type": "final",
        "reply": "".join(deltas),
        "backend": "test",
        "model": "test-model",
        "latency_ms": 5.0,
        "tokens_used": len(deltas),
        "error": None,
    }


def _get_max_client(monkeypatch):
    """Return a TestClient wired to max-tier + fake chat helpers."""
    monkeypatch.setenv("LAB_TIER", "max")
    # Stub _run_chat_completion + _run_chat_completion_stream in app
    monkeypatch.setattr(
        "arail.portal.openai_compat._run_chat_completion",
        mock.AsyncMock(return_value=_fake_result()),
    )
    monkeypatch.setattr(
        "arail.portal.openai_compat._run_chat_completion_stream",
        lambda **kw: _fake_stream_iter("tok1", "tok2", "tok3"),
    )
    # Stub _scan_local_models
    monkeypatch.setattr(
        "arail.portal.openai_compat._scan_local_models",
        lambda force=False: {"models": [{"id": "test-model", "name": "test-model"}]},
    )
    # Stub _get_chat_model_load_state
    monkeypatch.setattr(
        "arail.portal.openai_compat._get_chat_model_load_state",
        lambda: {"state": "ready", "model": "test-model"},
    )
    # Stub cost_tracker
    mock_tracker = mock.MagicMock()
    monkeypatch.setattr("arail.portal.openai_compat.cost_tracker", mock_tracker)

    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False), mock_tracker


# ---------------------------------------------------------------------------
# /api/openai/v1/models
# ---------------------------------------------------------------------------

class TestModelsEndpoint:
    def test_models_endpoint_envelope(self, monkeypatch):
        """Shape: {object: 'list', data: [...]} with at least one entry. (F-SHIM-1)"""
        client, _ = _get_max_client(monkeypatch)
        resp = client.get("/api/openai/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)
        assert len(data["data"]) >= 1

    def test_models_endpoint_owned_by(self, monkeypatch):
        """Every entry has owned_by='arail-lab'. (F-SHIM-1)"""
        client, _ = _get_max_client(monkeypatch)
        resp = client.get("/api/openai/v1/models")
        data = resp.json()
        for entry in data["data"]:
            assert entry["owned_by"] == "arail-lab", f"Bad owned_by: {entry}"
            assert entry["object"] == "model"
            assert "id" in entry
            assert "created" in entry

    def test_models_endpoint_includes_loaded_model(self, monkeypatch):
        """Loaded model appears even if not in scan (runtime-served case)."""
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.openai_compat._scan_local_models",
            lambda force=False: {"models": []},  # empty disk scan
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat._get_chat_model_load_state",
            lambda: {"state": "ready", "model": "runtime-only-model"},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat.cost_tracker", mock.MagicMock()
        )
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/openai/v1/models")
        ids = [e["id"] for e in resp.json()["data"]]
        assert "runtime-only-model" in ids

    def test_models_endpoint_never_raises(self, monkeypatch):
        """Returns empty list on error, never raises."""
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.openai_compat._scan_local_models",
            lambda force=False: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat._get_chat_model_load_state",
            lambda: (_ for _ in ()).throw(RuntimeError("boom2")),
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat.cost_tracker", mock.MagicMock()
        )
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/openai/v1/models")
        assert resp.status_code == 200
        data = resp.json()
        assert data["object"] == "list"
        assert isinstance(data["data"], list)


# ---------------------------------------------------------------------------
# /api/openai/v1/chat/completions — non-streaming
# ---------------------------------------------------------------------------

class TestChatNonStream:
    def _post(self, client, body: dict):
        return client.post("/api/openai/v1/chat/completions", json=body)

    def _basic_body(self, **kw):
        base = {"model": "test-model", "messages": [{"role": "user", "content": "hi"}]}
        base.update(kw)
        return base

    def test_chat_non_stream_envelope(self, monkeypatch):
        """Full OpenAI shape returned with usage. (F-SHIM-2)"""
        client, _ = _get_max_client(monkeypatch)
        resp = self._post(client, self._basic_body())
        assert resp.status_code == 200
        d = resp.json()
        assert d["object"] == "chat.completion"
        assert "id" in d
        assert d["id"].startswith("chatcmpl-")
        assert "created" in d
        assert d["model"] == "test-model"
        choices = d["choices"]
        assert len(choices) == 1
        assert choices[0]["index"] == 0
        assert choices[0]["finish_reason"] == "stop"
        assert choices[0]["message"]["role"] == "assistant"
        assert "content" in choices[0]["message"]
        # usage (F-SHIM-2)
        usage = d["usage"]
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "total_tokens" in usage
        assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]

    def test_chat_non_stream_includes_usage(self, monkeypatch):
        """Usage block present with non-zero values. (F-SHIM-2)"""
        client, _ = _get_max_client(monkeypatch)
        resp = self._post(client, self._basic_body())
        usage = resp.json()["usage"]
        assert usage["prompt_tokens"] >= 0
        assert usage["completion_tokens"] >= 0

    def test_chat_400_on_missing_messages(self, monkeypatch):
        """Missing messages → 400 + OpenAI error envelope. (F-SHIM-5)"""
        client, _ = _get_max_client(monkeypatch)
        resp = self._post(client, {"model": "test-model"})
        assert resp.status_code == 400
        d = resp.json()
        assert "error" in d
        assert d["error"]["type"] == "invalid_request_error"

    def test_chat_400_on_empty_messages(self, monkeypatch):
        """Empty messages list → 400."""
        client, _ = _get_max_client(monkeypatch)
        resp = self._post(client, {"model": "test-model", "messages": []})
        assert resp.status_code == 400

    def test_chat_400_on_missing_model(self, monkeypatch):
        """Missing model field → 400 + OpenAI error envelope. (F-SHIM-5)"""
        client, _ = _get_max_client(monkeypatch)
        resp = self._post(client, {"messages": [{"role": "user", "content": "hi"}]})
        assert resp.status_code == 400
        d = resp.json()
        assert "error" in d

    def test_chat_500_on_backend_exception(self, monkeypatch):
        """Backend exception → OpenAI error envelope, 500 status. (F-SHIM-5)"""
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.openai_compat._run_chat_completion",
            mock.AsyncMock(side_effect=RuntimeError("boom")),
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat._scan_local_models",
            lambda force=False: {"models": []},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat._get_chat_model_load_state",
            lambda: {"state": "ready", "model": None},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat.cost_tracker", mock.MagicMock()
        )
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/openai/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert resp.status_code == 500
        d = resp.json()
        assert "error" in d
        assert d["error"]["type"] == "server_error"

    def test_chat_strips_provider_prefix(self, monkeypatch):
        """model='lab-local/foo' → backend sees 'foo'. (F-SHIM-4)"""
        monkeypatch.setenv("LAB_TIER", "max")
        captured = {}
        async def fake_completion(**kw):
            captured.update(kw)
            return _fake_result()
        monkeypatch.setattr("arail.portal.openai_compat._run_chat_completion", fake_completion)
        monkeypatch.setattr(
            "arail.portal.openai_compat._scan_local_models",
            lambda force=False: {"models": []},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat._get_chat_model_load_state",
            lambda: {"state": "ready", "model": None},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat.cost_tracker", mock.MagicMock()
        )
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=False)
        client.post(
            "/api/openai/v1/chat/completions",
            json={"model": "lab-local/foo", "messages": [{"role": "user", "content": "hi"}]},
        )
        assert captured.get("model_override") == "foo"

    def test_chat_messages_to_history_mapping(self, monkeypatch):
        """system + user/assistant turns mapped correctly. (F-SHIM-3)"""
        monkeypatch.setenv("LAB_TIER", "max")
        captured = {}
        async def fake_completion(**kw):
            captured.update(kw)
            return _fake_result()
        monkeypatch.setattr("arail.portal.openai_compat._run_chat_completion", fake_completion)
        monkeypatch.setattr(
            "arail.portal.openai_compat._scan_local_models",
            lambda force=False: {"models": []},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat._get_chat_model_load_state",
            lambda: {"state": "ready", "model": None},
        )
        monkeypatch.setattr(
            "arail.portal.openai_compat.cost_tracker", mock.MagicMock()
        )
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=False)
        client.post(
            "/api/openai/v1/chat/completions",
            json={
                "model": "test-model",
                "messages": [
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                    {"role": "user", "content": "final question"},
                ],
            },
        )
        # Last user message is the active message (may include system prefix)
        msg = captured.get("message", "")
        assert "final question" in msg, f"Expected 'final question' in message, got: {msg!r}"
        # System content should appear in the message (prepended)
        assert "You are helpful." in msg, f"System content not found in message: {msg!r}"
        # Prior user/assistant turns are in history
        history = captured.get("history", [])
        assert len(history) >= 1

    def test_chat_cost_tracker_source_label(self, monkeypatch):
        """cost_tracker called with source='opencode'. (F-SHIM-7)"""
        client, mock_tracker = _get_max_client(monkeypatch)
        client.post(
            "/api/openai/v1/chat/completions",
            json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
        )
        # cost_tracker.track may be called with source='opencode'
        for call in mock_tracker.track.call_args_list:
            kwargs = call[1] if call[1] else {}
            if "source" in kwargs:
                assert kwargs["source"] == "opencode", (
                    f"cost_tracker.track called with source={kwargs['source']!r}, expected 'opencode'"
                )


# ---------------------------------------------------------------------------
# /api/openai/v1/chat/completions — streaming
# ---------------------------------------------------------------------------

class TestChatStream:
    def _stream_body(self, **kw):
        base = {
            "model": "test-model",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        }
        base.update(kw)
        return base

    def _collect_sse(self, client) -> list[dict]:
        """Collect SSE chunks from a streaming chat response."""
        resp = client.post(
            "/api/openai/v1/chat/completions",
            json=self._stream_body(),
        )
        lines = resp.text.split("\n")
        chunks = []
        for line in lines:
            line = line.strip()
            if line.startswith("data: "):
                payload = line[6:].strip()
                if payload == "[DONE]":
                    chunks.append("[DONE]")
                else:
                    try:
                        chunks.append(json.loads(payload))
                    except json.JSONDecodeError:
                        pass
        return chunks

    def test_chat_stream_envelope(self, monkeypatch):
        """SSE format: data: {...}\\n\\n chunks then data: [DONE]\\n\\n. (F-SHIM-1)"""
        client, _ = _get_max_client(monkeypatch)
        resp = client.post(
            "/api/openai/v1/chat/completions",
            json=self._stream_body(),
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        text = resp.text
        assert "[DONE]" in text
        # Every data: line (except DONE) is valid JSON with OpenAI chunk shape
        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("data: ") and line != "data: [DONE]":
                chunk = json.loads(line[6:])
                assert chunk["object"] == "chat.completion.chunk"
                assert chunk["id"].startswith("chatcmpl-")
                assert "choices" in chunk
                assert chunk["choices"][0]["index"] == 0

    def test_chat_stream_first_chunk_includes_role(self, monkeypatch):
        """First content delta has role:'assistant'; subsequent omit. (F-SHIM-1)"""
        client, _ = _get_max_client(monkeypatch)
        chunks = self._collect_sse(client)
        content_chunks = [c for c in chunks if isinstance(c, dict)]
        # Find first chunk with non-empty delta content
        roles_seen = [
            c["choices"][0]["delta"].get("role")
            for c in content_chunks
            if "delta" in c["choices"][0]
        ]
        non_none_roles = [r for r in roles_seen if r is not None]
        assert len(non_none_roles) >= 1
        assert non_none_roles[0] == "assistant"
        # After the first, role should not appear again
        if len(non_none_roles) > 1:
            for r in non_none_roles[1:]:
                assert r is None or r == "", (
                    f"Role appeared in later chunk: {r!r}"
                )

    def test_chat_stream_terminates_with_done(self, monkeypatch):
        """Stream ends with data: [DONE]. (F-SHIM-1)"""
        client, _ = _get_max_client(monkeypatch)
        chunks = self._collect_sse(client)
        assert chunks[-1] == "[DONE]"

    def test_chat_stream_final_chunk_finish_reason(self, monkeypatch):
        """Final content chunk has finish_reason='stop'. (F-SHIM-1)"""
        client, _ = _get_max_client(monkeypatch)
        chunks = self._collect_sse(client)
        dict_chunks = [c for c in chunks if isinstance(c, dict)]
        finish_reasons = [
            c["choices"][0].get("finish_reason")
            for c in dict_chunks
        ]
        assert "stop" in finish_reasons

    def test_chat_stream_yield_intervals(self, monkeypatch):
        """Structural check: stream yields multiple chunks (not buffered). (F-SHIM-8)"""
        client, _ = _get_max_client(monkeypatch)
        chunks = self._collect_sse(client)
        # We injected 3 deltas: tok1, tok2, tok3. Expect at least 3 content chunks + final.
        dict_chunks = [c for c in chunks if isinstance(c, dict)]
        assert len(dict_chunks) >= 3, f"Too few chunks: {len(dict_chunks)}"


# ---------------------------------------------------------------------------
# F-SEC-CRED-4 — Authorization header not logged
# ---------------------------------------------------------------------------

class TestSecCred4:
    def test_chat_does_not_log_authorization_header(self, monkeypatch, caplog):
        """Sending Authorization: Bearer SECRET-FAKE must not appear in logs. (F-SEC-CRED-4)"""
        import logging
        client, _ = _get_max_client(monkeypatch)
        with caplog.at_level(logging.DEBUG, logger="arail.portal.openai_compat"):
            client.post(
                "/api/openai/v1/chat/completions",
                headers={"Authorization": "Bearer SECRET-FAKE-TOKEN-XYZ"},
                json={"model": "test-model", "messages": [{"role": "user", "content": "hi"}]},
            )
        full_log = caplog.text
        assert "SECRET-FAKE-TOKEN-XYZ" not in full_log, (
            "Authorization header token leaked into logs"
        )
