"""Goal-event hook — on_goal_event clears the override and never generates."""

from __future__ import annotations

import pytest

from arail import dictionary
from arail.dictionary import resolve_theme, on_goal_event


@pytest.fixture(autouse=True)
def _clear_override():
    dictionary.clear_override()
    yield
    dictionary.clear_override()


def test_goal_set_clears_override():
    dictionary.set_override("agriculture")
    assert dictionary.get_override() == "agriculture"
    on_goal_event("goal_set", {"record": {"id": "z"}})
    assert dictionary.get_override() is None


def test_goal_cleared_clears_override():
    dictionary.set_override("agriculture")
    on_goal_event("goal_cleared", {"goal_id": "z"})
    assert dictionary.get_override() is None


def test_unrelated_event_leaves_override():
    dictionary.set_override("agriculture")
    on_goal_event("something_else", {})
    assert dictionary.get_override() == "agriculture"


def test_on_goal_event_never_calls_router(monkeypatch):
    # The OOM guard depends on generation being on-demand only. The goal hook
    # must NOT trigger any inference.
    called = {"n": 0}

    def _boom(*a, **k):
        called["n"] += 1
        raise AssertionError("router must not be constructed on goal event")

    monkeypatch.setattr("arail.dictionary.generate_terms", _boom)
    dictionary.set_override("agriculture")
    on_goal_event("goal_set", {"record": {"id": "z"}})
    assert called["n"] == 0


def test_theme_returns_to_default_after_goal_event():
    # Goal changes clear the override, so the theme falls back to the AI
    # glossary default — the goal never silently becomes the theme.
    dictionary.set_override("custom thing")
    on_goal_event("goal_set", {"record": {"id": "g1"}})
    theme = resolve_theme()
    assert theme["source"] == "default"
