"""Tests for the Anthropic prompt-cache prewarmer.

No network — `ClaudeBackend` is substituted with a fake at the module attr.
"""

from __future__ import annotations

import json

import pytest

from arail.router.backends import ModelResponse


# ── Fake backend ────────────────────────────────────────────────────────────

class _FakeBackend:
    _supports_cache = True

    def __init__(self, supports_cache: bool = True, raise_on_complete: bool = False):
        self._supports_cache = supports_cache
        self._raise = raise_on_complete
        self.calls: list[dict] = []

    def complete(self, prompt, max_tokens=512, temperature=0.7, top_p=None,
                 *, system=None, messages=None):
        if self._raise:
            raise RuntimeError("boom")
        self.calls.append({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        })
        return ModelResponse(
            text="",
            model="claude-sonnet-4-6",
            tokens_used=0,
            backend="claude",
            latency_ms=0.0,
            cost_usd=None,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=42,
        )


def _install_fake_backend(monkeypatch, **kwargs):
    fake = _FakeBackend(**kwargs)
    monkeypatch.setattr(
        "arail.router.backends.ClaudeBackend", lambda: fake)
    return fake


# ── Skip-paths (security-relevant: airgap never calls network) ──────────────

def test_prewarm_skipped_when_airgapped(monkeypatch):
    monkeypatch.delenv("LAB_MODE", raising=False)
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    from arail.router.cache_prewarm import prewarm_claude_cache
    out = prewarm_claude_cache()
    assert out == {"status": "skipped", "reason": "airgapped"}


def test_prewarm_skipped_without_api_key(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from arail.router.cache_prewarm import prewarm_claude_cache
    out = prewarm_claude_cache()
    assert out["status"] == "skipped"
    assert "ANTHROPIC_API_KEY" in out["reason"]


def test_prewarm_skipped_on_old_sdk(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _install_fake_backend(monkeypatch, supports_cache=False)
    from arail.router.cache_prewarm import prewarm_claude_cache
    out = prewarm_claude_cache()
    assert out["status"] == "skipped"
    assert "0.34.0" in out["reason"]


# ── Happy path ──────────────────────────────────────────────────────────────

def test_prewarm_warms_claude_with_frozen_system(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = _install_fake_backend(monkeypatch)
    from arail.router.cache_prewarm import prewarm_claude_cache

    out = prewarm_claude_cache(prompts=["first demo question"])
    assert out["status"] == "ok"
    assert out["prompts"] == 1
    assert out["cache_creation_tokens"] == 42       # the fake writes 42 per call

    # one Claude call, shaped correctly
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["max_tokens"] == 1                  # canonical prewarm value
    # frozen prefix is the cacheable lab-aware system prompt
    assert "How to answer" in call["system"]
    assert "Operator quickstart" in call["system"]
    assert "Timestamp:" not in call["system"]        # volatile must NOT leak
    # the structured turn carries the demo prompt verbatim
    assert call["messages"] == [{"role": "user", "content": "first demo question"}]
    assert call["prompt"] == "first demo question"


def test_prewarm_uses_provided_prompts_over_defaults(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = _install_fake_backend(monkeypatch)
    from arail.router.cache_prewarm import prewarm_claude_cache

    out = prewarm_claude_cache(prompts=["A", "B", "C"])
    assert out["prompts"] == 3
    sent_prompts = [c["prompt"] for c in fake.calls]
    assert sent_prompts == ["A", "B", "C"]


def test_prewarm_uses_config_file_when_no_args(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = _install_fake_backend(monkeypatch)
    # cache_prewarm reads `lab/data/prewarm_prompts.json` relative to cwd.
    (tmp_path / "lab" / "data").mkdir(parents=True)
    (tmp_path / "lab" / "data" / "prewarm_prompts.json").write_text(
        json.dumps(["from-file-one", "from-file-two"]), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    from arail.router.cache_prewarm import prewarm_claude_cache
    out = prewarm_claude_cache()
    assert out["prompts"] == 2
    assert [c["prompt"] for c in fake.calls] == ["from-file-one", "from-file-two"]


def test_prewarm_falls_back_to_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = _install_fake_backend(monkeypatch)
    monkeypatch.chdir(tmp_path)                # no config file present

    from arail.router.cache_prewarm import prewarm_claude_cache, _DEFAULT_PROMPTS
    out = prewarm_claude_cache()
    assert out["prompts"] == len(_DEFAULT_PROMPTS)
    assert [c["prompt"] for c in fake.calls] == list(_DEFAULT_PROMPTS)


def test_prewarm_records_per_prompt_errors_without_aborting(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    _install_fake_backend(monkeypatch, raise_on_complete=True)
    from arail.router.cache_prewarm import prewarm_claude_cache

    out = prewarm_claude_cache(prompts=["one", "two"])
    assert out["status"] == "ok"
    assert out["cache_creation_tokens"] == 0
    assert all("error" in d for d in out["details"])
    assert len(out["details"]) == 2                # both attempted, neither aborted
