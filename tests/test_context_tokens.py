"""Unit tests for model_specs.context_tokens + context_label.

Sprint: 2026-05-18-provider-aware-chat-dropdown, Phase A step 2.
"""

from __future__ import annotations

import pytest

from arail.model_specs import context_tokens, context_label, lookup


# ---------------------------------------------------------------------------
# context_tokens — canonical cases from ARCHITECTURE.md
# ---------------------------------------------------------------------------

def test_128k_tokens_string():
    assert context_tokens("128K tokens") == 131072


def test_1m_tokens_string():
    assert context_tokens("1M tokens") == 1048576


def test_32k_lower():
    assert context_tokens("32k") == 32768


def test_bare_integer_string():
    assert context_tokens("4096") == 4096


def test_bare_integer_input():
    assert context_tokens(4096) == 4096


def test_none_returns_none():
    assert context_tokens(None) is None


def test_empty_string_returns_none():
    assert context_tokens("") is None


def test_unparseable_banana():
    assert context_tokens("banana") is None


# ---------------------------------------------------------------------------
# Additional coverage — units, capitalisation, edge values
# ---------------------------------------------------------------------------

def test_200k_tokens_upper():
    assert context_tokens("200K tokens") == 200 * 1024


def test_context_label_stripped():
    """'128K tokens' after stripping trailing word → '128K' → 131072."""
    assert context_tokens("128K tokens") == 131_072


def test_k_unit_case_insensitive_lowercase():
    assert context_tokens("32k") == 32768


def test_k_unit_case_insensitive_uppercase():
    assert context_tokens("32K") == 32768


def test_m_unit_uppercase():
    assert context_tokens("1M") == 1048576


def test_m_unit_lowercase():
    assert context_tokens("1m") == 1048576


def test_zero_returns_none():
    """0 is not a valid context window."""
    assert context_tokens(0) is None


def test_negative_int_returns_none():
    assert context_tokens(-1) is None


def test_fractional_k():
    """0.5K = 512 — valid llama.cpp n_ctx value."""
    assert context_tokens("0.5K") == 512


def test_comma_in_label_ignored():
    """'128,000 tokens' is not in our format — should return None gracefully."""
    result = context_tokens("128,000 tokens")
    assert result is None  # comma breaks our simple parse


def test_lru_cache_on_context_tokens():
    """context_tokens is @lru_cache — repeat calls are O(1) cache hits."""
    assert hasattr(context_tokens, "cache_info")
    context_tokens("64K")  # warm
    info = context_tokens.cache_info()
    assert info.hits >= 0  # cache is active


# ---------------------------------------------------------------------------
# context_label — returns context string from _SPECS registry
# ---------------------------------------------------------------------------

def test_context_label_qwen3_8b():
    """Qwen3-8B has '128K tokens' in its spec."""
    label = context_label("Qwen3-8B")
    assert label == "128K tokens"


def test_context_label_unknown_returns_none():
    assert context_label("totally-unknown-model-xyz-999") is None


def test_context_label_empty_string_returns_none():
    assert context_label("") is None


def test_context_tokens_of_context_label_roundtrips():
    """context_tokens(context_label(name)) should give a valid int for known models."""
    label = context_label("Qwen3-8B")
    assert label is not None
    tokens = context_tokens(label)
    assert tokens == 131072  # 128K
