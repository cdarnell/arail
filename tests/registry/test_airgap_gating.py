"""Cloud providers are visible-blocked while airgapped — never hidden."""

from __future__ import annotations


def test_cloud_entries_blocked_but_visible_when_airgapped(tmp_registry):
    reg = tmp_registry   # LAB_MODE=airgapped from the fixture
    state = reg.to_state()
    ids = {e["id"] for e in state["entries"]}
    assert "cloud-anthropic" in ids and "cloud-xai" in ids

    reg.bind("reasoning", "cloud-anthropic")
    res = reg.resolve("reasoning")
    # Falls back to a local model with a visible reason.
    assert res.entry is not None and res.entry.provider_type in ("local", "aerollm")
    assert res.fallback is not None
    assert res.fallback.reason == "blocked_airgap"
    assert "airgapped" in res.fallback.detail


def test_cloud_needs_key_when_hybrid(tmp_registry, monkeypatch):
    reg = tmp_registry
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reg.bind("reasoning", "cloud-anthropic")
    res = reg.resolve("reasoning")
    assert res.fallback is not None
    assert res.fallback.reason == "no_key"
    assert "ANTHROPIC_API_KEY" in res.fallback.detail


def test_cloud_resolvable_when_hybrid_with_key(tmp_registry, monkeypatch):
    reg = tmp_registry
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-not-real")
    reg.bind("reasoning", "cloud-anthropic")
    res = reg.resolve("reasoning")
    assert res.entry is not None and res.entry.id == "cloud-anthropic"
    assert res.fallback is None


def test_local_entries_unaffected_by_airgap(tmp_registry):
    reg = tmp_registry
    assert reg.resolve("fast").entry.id == "tier0-local"
    assert reg.resolve("reasoning").entry.id == "tier1-aerollm"
