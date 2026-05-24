"""Theme resolution + slug derivation.

The curated AI glossary is the always-on default; only an explicit override
changes the theme. The research goal never auto-switches it.
"""

from __future__ import annotations

import pytest

from arail import dictionary
from arail.dictionary import (
    theme_slug, resolve_theme, DEFAULT_SLUG, DEFAULT_THEME,
)


@pytest.fixture(autouse=True)
def _clear_override():
    dictionary.clear_override()
    yield
    dictionary.clear_override()


def test_theme_slug_basic():
    assert theme_slug("AI / Model Tuning") == "ai-model-tuning"
    assert theme_slug("Trip to Japan!") == "trip-to-japan"


def test_theme_slug_empty_defaults():
    assert theme_slug("") == DEFAULT_SLUG
    assert theme_slug("   ") == DEFAULT_SLUG
    assert theme_slug("!!!") == DEFAULT_SLUG


def test_theme_slug_capped_at_48():
    s = theme_slug("a" * 80 + " very long theme label that keeps going")
    assert len(s) <= 48
    assert not s.endswith("-")


def test_default_is_ai_glossary():
    theme = resolve_theme()
    assert theme["source"] == "default"
    assert theme["label"] == DEFAULT_THEME["label"]
    assert theme_slug(theme["label"]) == "ai-model-tuning"


def test_override_sets_theme():
    dictionary.set_override("agriculture")
    theme = resolve_theme()
    assert theme["source"] == "override"
    assert theme["label"] == "agriculture"
    # Arbitrary topic with no special keywords -> general archetype.
    assert theme["archetype"] == "general"


def test_travel_override_instruction_mentions_pronunciation():
    dictionary.set_override("trip to Japan")
    theme = resolve_theme()
    assert theme["archetype"] == "travel"
    assert "pronunciation" in theme["instruction"].lower()


def test_research_override_archetype():
    dictionary.set_override("benchmark RAG latency")
    theme = resolve_theme()
    assert theme["archetype"] == "research"


def test_clear_override_returns_to_default():
    dictionary.set_override("agriculture")
    dictionary.clear_override()
    theme = resolve_theme()
    assert theme["source"] == "default"


def test_explicit_override_arg_beats_module_state():
    dictionary.set_override("agriculture")
    theme = resolve_theme("trip to Japan")
    assert theme["label"] == "trip to Japan"


def test_empty_override_is_ignored():
    dictionary.set_override("   ")
    theme = resolve_theme()
    assert theme["source"] == "default"
