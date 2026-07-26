"""Shared fixtures for model-registry tests.

Every test gets a tmp registry file and a fresh singleton — the registry is
process-global, so the reset must run around each test.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def tmp_registry(monkeypatch, tmp_path):
    """Fresh registry singleton persisted to a per-test tmp file.

    Also pins the model env to the known lab default (ollama_native +
    ai-engineer + aerollm Qwen2.5-7B-Instruct-4bit) so seeding is
    deterministic.
    """
    from arail.registry import core as reg_core

    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE",
                       str(tmp_path / "model_registry.json"))
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "ai-engineer:latest")
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    monkeypatch.delenv("OLLAMA_PORT", raising=False)
    monkeypatch.setenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct-4bit")
    monkeypatch.setenv("AEROLLM_RESEARCH", "true")
    monkeypatch.setenv("LAB_MODE", "airgapped")

    reg_core.reset_registry()
    reg = reg_core.get_registry()
    reg._ensure_loaded()   # tests inspect .entries/.bindings directly
    yield reg
    reg_core.reset_registry()
