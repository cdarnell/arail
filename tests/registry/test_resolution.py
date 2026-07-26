"""Registry seeding + resolve() precedence + persistence."""

from __future__ import annotations

import json
import os


def test_seed_from_env(tmp_registry):
    reg = tmp_registry
    state = reg.to_state()
    ids = {e["id"] for e in state["entries"]}
    assert {"tier0-local", "tier1-aerollm", "qkz-project-aware-2b",
            "cloud-anthropic", "cloud-xai", "gateway-custom"} <= ids

    tier0 = reg.entries["tier0-local"]
    assert tier0.model_id == "ai-engineer:latest"
    assert tier0.endpoint == "http://127.0.0.1:11434/v1"
    assert tier0.tier == 0

    tier1 = reg.entries["tier1-aerollm"]
    assert tier1.model_id == "Qwen2.5-7B-Instruct-4bit"
    assert tier1.provider_type == "aerollm"
    assert tier1.endpoint is None          # in-process, no HTTP server
    assert tier1.architecture == "dense"
    assert tier1.moe is None

    # Cloud entries are present and VISIBLE even while airgapped.
    assert "cloud-anthropic" in ids and "cloud-xai" in ids

    # Default bindings.
    assert reg.bindings["fast"] == "tier0-local"
    assert reg.bindings["reasoning"] == "tier1-aerollm"
    assert reg.bindings["build"] == "tier1-aerollm"

    # The registry file was written, with no health and no secrets.
    raw = json.loads(open(os.environ["ARAIL_MODEL_REGISTRY_FILE"]).read())
    assert raw["schema_version"] == 1
    assert all("health" not in e for e in raw["entries"])
    dumped = json.dumps(raw)
    assert "api_key" not in dumped.lower() or "key_env" in dumped


def test_profile_tier_mapping(tmp_registry):
    reg = tmp_registry
    assert reg.resolve("fast").entry.id == "tier0-local"
    assert reg.resolve("reasoning").entry.id == "tier1-aerollm"
    assert reg.resolve("build").entry.id == "tier1-aerollm"
    # long_context: nothing declares ≥32k ctx in this seed except possibly
    # tier1; either tier1 or the ctx-max entry is acceptable, never None.
    res = reg.resolve("long_context")
    assert res.entry is not None
    # tool_use falls to tier0 (no local entry declares tools).
    assert reg.resolve("tool_use").entry.id == "tier0-local"


def test_override_precedence(tmp_registry):
    reg = tmp_registry
    # Lab-wide binding change.
    reg.bind("reasoning", "tier0-local")
    assert reg.resolve("reasoning").entry.id == "tier0-local"
    # Tab-specific override beats lab binding.
    reg.bind("reasoning", "tier1-aerollm", tab="research")
    assert reg.resolve("reasoning", tab="research").entry.id == "tier1-aerollm"
    assert reg.resolve("reasoning", tab="agents").entry.id == "tier0-local"
    # Tab wildcard applies when no profile-specific override exists.
    reg.bind("*", "qkz-project-aware-2b", tab="agents")
    assert reg.resolve("fast", tab="agents").entry.id == "qkz-project-aware-2b"
    # Clearing restores the fallback chain of precedence.
    reg.bind("reasoning", None, tab="research")
    assert reg.resolve("reasoning", tab="research").entry.id == "tier0-local"


def test_config_version_bumps_on_mutation(tmp_registry):
    reg = tmp_registry
    v0 = reg.config_version
    reg.bind("reasoning", "tier0-local")
    assert reg.config_version > v0


def test_persistence_roundtrip(tmp_registry, monkeypatch):
    from arail.registry import core as reg_core

    reg = tmp_registry
    reg.bind("reasoning", "tier0-local")
    reg.bind("fast", "tier0-local", tab="research")
    v = reg.config_version

    reg_core.reset_registry()
    reg2 = reg_core.get_registry()
    reg2._ensure_loaded()
    assert reg2.bindings["reasoning"] == "tier0-local"
    assert reg2.tab_overrides["research"]["fast"] == "tier0-local"
    assert reg2.config_version >= v


def test_unknown_profile_rejected(tmp_registry):
    import pytest
    with pytest.raises(ValueError):
        tmp_registry.resolve("nope")
