"""R4 — catalog back-compat regression test.

Sprint: 2026-05-18-provider-aware-chat-dropdown, Phase A step 3 (F-CATALOG).

Verifies:
1. Legacy YAML rows (no provider/ctx fields) still load and as_dict() works.
2. Rows WITH provider/ctx fields survive as_dict() — not silently dropped.
3. Existing test_chat_model_sync.py behavior unaffected (covered by running it).
"""

from __future__ import annotations

import pytest

from arail.chat import CatalogEntry, load_catalog


# ---------------------------------------------------------------------------
# R4a — legacy row (no new fields) still loads
# ---------------------------------------------------------------------------

def test_catalog_entry_legacy_row_loads():
    """A CatalogEntry created without provider/ctx fields works fine."""
    e = CatalogEntry(
        id="qwen2.5:7b",
        name="Qwen 2.5 7B",
        family="qwen",
        size_gb=4.7,
        released="2024-09",
        source="ollama",
        good_at=["chat"],
        description="test",
        install="ollama pull qwen2.5:7b",
        tier="recommended",
    )
    d = e.as_dict()
    assert d["id"] == "qwen2.5:7b"
    assert d["provider"] is None
    assert d["ctx"] is None


def test_catalog_entry_legacy_row_provider_defaults_none():
    """Legacy rows default provider to None, not a missing key."""
    e = CatalogEntry(
        id="ai-eng:latest",
        name="AI Engineer",
        family="qukaizen",
        size_gb=2.0,
        released="2026-05",
        source="ollama",
        good_at=["chat"],
        description="test",
        install="",
        tier="recommended",
    )
    d = e.as_dict()
    assert "provider" in d
    assert d["provider"] is None


def test_catalog_entry_legacy_row_ctx_defaults_none():
    """Legacy rows default ctx to None, not a missing key."""
    e = CatalogEntry(
        id="ai-eng:latest",
        name="AI Engineer",
        family="qukaizen",
        size_gb=2.0,
        released="2026-05",
        source="ollama",
        good_at=["chat"],
        description="test",
        install="",
        tier="recommended",
    )
    d = e.as_dict()
    assert "ctx" in d
    assert d["ctx"] is None


# ---------------------------------------------------------------------------
# R4b — cloud row WITH provider/ctx survives as_dict()
# ---------------------------------------------------------------------------

def test_catalog_entry_cloud_row_provider_survives_as_dict():
    """F-CATALOG: provider field must appear in as_dict() output."""
    e = CatalogEntry(
        id="claude-opus-4-7",
        name="Claude Opus 4.7",
        family="claude",
        size_gb=0,
        released="",
        source="cloud",
        good_at=[],
        description="",
        install="",
        tier="flagship",
        provider="claude",
        ctx="200K tokens",
    )
    d = e.as_dict()
    assert d["provider"] == "claude"
    assert d["ctx"] == "200K tokens"


def test_catalog_entry_cloud_row_all_known_keys_present():
    """as_dict() must include all fields (no accidental omission)."""
    e = CatalogEntry(
        id="grok-3",
        name="Grok 3",
        family="xai",
        size_gb=0,
        released="",
        source="cloud",
        good_at=["chat", "code"],
        description="xAI flagship",
        install="",
        tier="flagship",
        provider="xai",
        ctx="131072 tokens",
    )
    d = e.as_dict()
    expected_keys = {
        "id", "name", "family", "size_gb", "released", "source",
        "good_at", "description", "install", "tier", "provider", "ctx",
    }
    assert expected_keys.issubset(d.keys()), f"Missing keys: {expected_keys - d.keys()}"


# ---------------------------------------------------------------------------
# R4c — load_catalog() still loads when catalog has no cloud rows
# ---------------------------------------------------------------------------

def test_load_catalog_returns_list():
    """load_catalog() returns a list (may be empty in test env)."""
    result = load_catalog()
    assert isinstance(result, list)


def test_load_catalog_all_entries_have_provider_key():
    """Every loaded entry has provider in its as_dict() output."""
    for entry in load_catalog():
        d = entry.as_dict()
        assert "provider" in d, f"Entry {entry.id!r} missing 'provider' in as_dict()"
        assert "ctx" in d, f"Entry {entry.id!r} missing 'ctx' in as_dict()"
