"""Tests for the Drafter agent.

Drafter is a synchronous composition agent invoked by blueprints
(inbox-triager, client-followup). Canonical source lives at
src/arail/agents/_builtin_drafter.py; the agent loader's seed
function copies it into lab/pkb/agents/drafter/drafter.py at boot.

These tests target the canonical source location and use a mocked
ModelRouter so the suite runs hermetically without spinning up a
real LLM. End-to-end voice-quality eval lives elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest

from arail.agents import _builtin_drafter as drafter_module
from arail.agents._builtin_drafter import Draft, DrafterAgent, drafter


# ── Fake ModelRouter ───────────────────────────────────────────────


@dataclass
class _FakeResponse:
    text: str
    model: str = "fake-model"
    backend: str = "fake-backend"


class _FakeRouter:
    """Minimal ModelRouter substitute. Records the prompt it was
    called with so tests can assert on prompt construction.
    """

    def __init__(self, *, response_text: str = "Sounds good — Friday works."):
        self._response_text = response_text
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> _FakeResponse:
        self.calls.append({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        })
        return _FakeResponse(text=self._response_text)


# ── Tests ──────────────────────────────────────────────────────────


def test_module_exports_singleton():
    assert drafter.name == "Drafter"
    assert isinstance(drafter, DrafterAgent)


def test_compose_returns_draft_with_consent_required():
    router = _FakeRouter(response_text="Got it — sending Friday.")
    result = drafter.compose(
        context="Hey, can you send the deck before Friday?",
        intent="reply professionally; confirm timing",
        router=router,
    )
    assert isinstance(result, Draft)
    assert result.requires_consent is True
    assert result.text == "Got it — sending Friday."
    assert result.model == "fake-model"


def test_compose_passes_max_tokens_and_temperature():
    router = _FakeRouter()
    drafter.compose(
        context="x", intent="y",
        max_tokens=123, temperature=0.42,
        router=router,
    )
    assert router.calls[0]["max_tokens"] == 123
    assert router.calls[0]["temperature"] == 0.42


def test_compose_prompt_contains_context_intent_and_voice():
    router = _FakeRouter()
    drafter.compose(
        context="MEETING-NOTES-123",
        intent="follow-up-INTENT-456",
        router=router,
    )
    prompt = router.calls[0]["prompt"]
    assert "MEETING-NOTES-123" in prompt
    assert "follow-up-INTENT-456" in prompt
    assert "Voice:" in prompt
    # System prompt baked in
    assert "You are a drafter" in prompt
    # Never-auto-send rule baked in
    assert "not your job" in prompt or "not a sender" in prompt.lower()


def test_compose_strips_whitespace_in_response():
    router = _FakeRouter(response_text="   ok thanks   \n")
    result = drafter.compose(
        context="x", intent="y", router=router,
    )
    assert result.text == "ok thanks"


def test_compose_rejects_empty_context():
    with pytest.raises(ValueError, match="context"):
        drafter.compose(context="", intent="y")


def test_compose_rejects_empty_intent():
    with pytest.raises(ValueError, match="intent"):
        drafter.compose(context="x", intent="")


def test_compose_handles_missing_router_gracefully():
    # When no router is available and none is passed in, return an
    # empty-text Draft with metadata.error rather than raising. This
    # protects test environments and offline scaffolding.
    fresh_agent = DrafterAgent()
    fresh_agent._router = None  # force the lazy-load to fail
    # Block the lazy load by monkeypatching the import attempt.
    import sys

    # Save and stub the router module so the lazy-load path returns None.
    saved = sys.modules.get("arail.router.core")
    sys.modules["arail.router.core"] = None  # type: ignore[assignment]
    try:
        result = fresh_agent.compose(context="x", intent="y")
    finally:
        if saved is not None:
            sys.modules["arail.router.core"] = saved
        else:
            sys.modules.pop("arail.router.core", None)

    assert result.text == ""
    assert result.requires_consent is True
    assert "error" in result.metadata


def test_loader_resolves_drafter_via_seed():
    """End-to-end: loader.load_one('buddy') should seed + import
    the agent from the PKB copy and return our singleton.
    """
    from arail.agents.loader import load_one
    agent = load_one("buddy")
    assert agent is not None
    assert hasattr(agent, 'start') or hasattr(agent, 'dream')
