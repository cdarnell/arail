"""Prompt-caching tests for the Claude backend and the researcher threading.

These exercise the cache-shaping logic offline (a fake Anthropic client) so no
network call is ever made. They cover:
  (b) non-Claude backends prepend `system` (byte-compatible flat behavior),
  (c) the airgap/security gating that keeps Claude out of local/airgapped mode,
  (d) ClaudeBackend cache_control shaping + usage parsing + the temp/top_p fix,
  (e) the researcher threading `system=` through its LLM helpers.
"""

from __future__ import annotations

import pytest


# ── Fakes ───────────────────────────────────────────────────────────────────

class _FakeUsage:
    def __init__(self, read=0, creation=0, output=7):
        self.cache_read_input_tokens = read
        self.cache_creation_input_tokens = creation
        self.output_tokens = output


class _FakeBlock:
    def __init__(self, text):
        self.type = "text"
        self.text = text


class _FakeResp:
    def __init__(self, text="hi", usage=None):
        self.content = [_FakeBlock(text)]
        self.usage = usage or _FakeUsage(read=999, creation=42, output=7)


class _FakeMessages:
    def __init__(self):
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResp()


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


def _make_claude_backend(monkeypatch, model="claude-sonnet-4-6",
                         supports_cache=True):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("MODEL_NAME", model)
    from arail.router.backends import ClaudeBackend
    be = ClaudeBackend()           # constructs a real (offline) SDK client
    be.client = _FakeClient()      # ...which we never call
    be._supports_cache = supports_cache
    return be


# ── (d) ClaudeBackend cache shaping ─────────────────────────────────────────

def test_claude_caches_system_when_above_floor(monkeypatch):
    be = _make_claude_backend(monkeypatch)                    # sonnet-4-6 → 2048
    big_system = "x" * (2048 * 4 + 100)                       # > 2048 tokens
    resp = be.complete("hello", system=big_system)
    kw = be.client.messages.last_kwargs
    assert isinstance(kw["system"], list)
    assert kw["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert kw["system"][0]["text"] == big_system
    # usage parsed onto the ModelResponse
    assert resp.cache_read_input_tokens == 999
    assert resp.cache_creation_input_tokens == 42
    assert resp.text == "hi"


def test_claude_system_plain_when_below_floor(monkeypatch):
    be = _make_claude_backend(monkeypatch)                    # floor 2048
    small_system = "tiny system prefix"                       # << 2048 tokens
    be.complete("hello", system=small_system)
    kw = be.client.messages.last_kwargs
    assert kw["system"] == small_system                       # plain string, no marker


def test_claude_old_sdk_sends_plain_system(monkeypatch):
    be = _make_claude_backend(monkeypatch, supports_cache=False)
    big_system = "x" * (2048 * 4 + 100)
    be.complete("hi", system=big_system)
    kw = be.client.messages.last_kwargs
    assert kw["system"] == big_system                         # no cache_control on old SDK


def test_claude_no_system_key_when_none(monkeypatch):
    be = _make_claude_backend(monkeypatch)
    be.complete("hello")
    kw = be.client.messages.last_kwargs
    assert "system" not in kw
    assert kw["messages"] == [{"role": "user", "content": "hello"}]


def test_claude_sends_only_top_p_when_set(monkeypatch):
    # Claude 4+ rejects temperature AND top_p together — must send at most one.
    be = _make_claude_backend(monkeypatch)
    be.complete("hi", temperature=0.7, top_p=0.9)
    kw = be.client.messages.last_kwargs
    assert kw.get("top_p") == 0.9
    assert "temperature" not in kw


def test_claude_sends_temperature_when_no_top_p(monkeypatch):
    be = _make_claude_backend(monkeypatch)
    be.complete("hi", temperature=0.5)
    kw = be.client.messages.last_kwargs
    assert kw["temperature"] == 0.5
    assert "top_p" not in kw


def test_claude_marks_last_message_breakpoint(monkeypatch):
    be = _make_claude_backend(monkeypatch)
    msgs = [
        {"role": "user", "content": "h1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "current question"},
    ]
    be.complete("ignored-flat-prompt", messages=msgs)
    sent = be.client.messages.last_kwargs["messages"]
    last = sent[-1]
    assert isinstance(last["content"], list)
    assert last["content"][-1]["cache_control"] == {"type": "ephemeral"}
    assert last["content"][-1]["text"] == "current question"
    # earlier turns left as plain strings
    assert sent[0] == {"role": "user", "content": "h1"}
    # the caller's list must not be mutated in place
    assert msgs[-1]["content"] == "current question"


def test_min_cacheable_prefix_floors():
    from arail.router.backends import _min_cacheable_prefix_tokens as floor
    assert floor("claude-sonnet-4-6") == 2048
    assert floor("claude-sonnet-4-20250514") == 1024
    assert floor("claude-opus-4-7") == 4096
    assert floor("claude-haiku-4-5") == 4096
    assert floor("some-unknown-model") == 4096   # conservative default


# ── (b) non-Claude backends prepend system (flat behavior preserved) ────────

def test_non_claude_backend_prepends_system(monkeypatch):
    monkeypatch.setenv("MODEL_API_BASE", "http://localhost:1234/v1")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    from arail.router.backends import OpenAICompatBackend
    be = OpenAICompatBackend()

    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "model": "local-model",
                "usage": {"completion_tokens": 3},
            }

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(be._session, "post", fake_post)
    be.complete("BODY", system="FROZEN")
    sent = captured["json"]["messages"]
    assert sent[0]["content"] == "FROZEN\n\nBODY"


def test_non_claude_backend_ignores_messages_param(monkeypatch):
    # messages= is Claude-only; local backends use the flat prompt.
    monkeypatch.setenv("MODEL_API_BASE", "http://localhost:1234/v1")
    monkeypatch.setenv("MODEL_NAME", "local-model")
    from arail.router.backends import OpenAICompatBackend
    be = OpenAICompatBackend()

    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}],
                    "model": "local-model", "usage": {"completion_tokens": 1}}

    monkeypatch.setattr(
        be._session, "post",
        lambda url, headers=None, json=None, timeout=None: (
            captured.__setitem__("json", json) or _Resp()),
    )
    be.complete("BODY", messages=[{"role": "user", "content": "STRUCTURED"}])
    sent = captured["json"]["messages"]
    assert sent[0]["content"] == "BODY"            # flat prompt, not the structured turn


# ── (c) airgap / security gating ────────────────────────────────────────────

def test_claude_backend_requires_api_key(monkeypatch):
    # Caching must not have weakened the key gate that keeps Claude offline.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from arail.router.backends import ClaudeBackend
    with pytest.raises(ValueError):
        ClaudeBackend()


def test_airgapped_by_default(monkeypatch):
    monkeypatch.delenv("LAB_MODE", raising=False)
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    from arail.airgap import is_airgapped
    assert is_airgapped() is True


# ── (e) researcher threads system= through its LLM helpers ──────────────────

def test_researcher_llm_complete_threads_system(monkeypatch):
    from arail.agents import researcher
    monkeypatch.setattr(researcher.activity_log, "emit", lambda *a, **k: None)

    captured = {}

    class _Resp:
        text = "1. hypothesis one"

    class _FakeRouter:
        def complete(self, prompt, **kwargs):
            captured["prompt"] = prompt
            captured["system"] = kwargs.get("system")
            return _Resp()

    out = researcher._llm_complete(_FakeRouter(), "BODY", 100, system="SYSCTX")
    assert out == "1. hypothesis one"
    assert captured["system"] == "SYSCTX"
    assert captured["prompt"] == "BODY"
    assert not captured["prompt"].startswith("SYSCTX")   # sys_ctx not duplicated in body


def test_researcher_deep_complete_forwards_system(monkeypatch):
    from arail.agents import researcher
    monkeypatch.setattr(researcher.activity_log, "emit", lambda *a, **k: None)

    seen = {}

    class _Resp:
        text = "ok"

    class _FakeRouter:
        def complete(self, prompt, **kwargs):
            seen["system"] = kwargs.get("system")
            return _Resp()

    # deep_router=None → falls back to the fast router, system still forwarded.
    out = researcher._deep_complete(None, _FakeRouter(), "BODY", 200, system="SYSCTX")
    assert out == "ok"
    assert seen["system"] == "SYSCTX"
