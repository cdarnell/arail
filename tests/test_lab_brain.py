"""Lab brain smoke tests — system prompt composition."""

from __future__ import annotations

import pytest

from oglab import brand, lab_brain


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for k in ("LAB_NAME", "LAB_TAGLINE", "LAB_INTENT", "LAB_INTENT_NAME",
              "MODEL_BACKEND", "MODEL_NAME"):
        monkeypatch.delenv(k, raising=False)
    brand.reset_brand_cache()
    yield
    brand.reset_brand_cache()


def test_default_prompt_mentions_brand_and_capabilities():
    p = lab_brain.build_system_prompt()
    # Brand layer
    assert "OGLab" in p
    assert "AI Lab Blueprint" in p
    # Capabilities reference is included by default
    assert "Model router" in p
    assert "Scheduler" in p
    assert "Personal Knowledge Base" in p
    assert "./oglab" in p
    # State block
    assert "Current lab state" in p
    # How-to answer guidance at the end
    assert "How to answer" in p


def test_branded_prompt_uses_custom_name(monkeypatch):
    monkeypatch.setenv("LAB_NAME", "PeanutLab")
    monkeypatch.setenv("LAB_TAGLINE", "Grow more peanuts")
    brand.reset_brand_cache()
    p = lab_brain.build_system_prompt()
    assert "PeanutLab" in p
    assert "Grow more peanuts" in p


def test_exclude_capabilities_shrinks_prompt():
    full = lab_brain.build_system_prompt(include_capabilities=True)
    tight = lab_brain.build_system_prompt(include_capabilities=False)
    assert "Model router" in full
    assert "Model router" not in tight
    assert len(tight) < len(full)


def test_exclude_state_shrinks_prompt():
    full = lab_brain.build_system_prompt(include_state=True)
    tight = lab_brain.build_system_prompt(include_state=False)
    assert "Current lab state" in full
    assert "Current lab state" not in tight


def test_extra_context_appended():
    p = lab_brain.build_system_prompt(extra_context="Respond in 2 sentences.")
    assert "Respond in 2 sentences." in p


def test_intent_switches_domain_context(monkeypatch):
    monkeypatch.setenv("LAB_INTENT", "farming")
    monkeypatch.setenv("LAB_INTENT_NAME", "Farmer")
    p = lab_brain.build_system_prompt()
    assert "agricultural research lab" in p
    assert "Farmer" in p


def test_build_chat_prompt_formats_conversation():
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi! How can I help?"},
    ]
    prompt = lab_brain.build_chat_prompt("What can you do?", history)
    assert "<system>" in prompt
    assert "</system>" in prompt
    assert "User: Hello" in prompt
    assert "Assistant: Hi! How can I help?" in prompt
    assert "User: What can you do?" in prompt
    assert prompt.rstrip().endswith("Assistant:")


def test_build_chat_prompt_handles_empty_history():
    prompt = lab_brain.build_chat_prompt("Just this", None)
    assert "User: Just this" in prompt
    assert prompt.rstrip().endswith("Assistant:")


def test_state_block_includes_backend(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "mlx")
    monkeypatch.setenv("MODEL_NAME", "mlx-community/Qwen3-8B-4bit")
    p = lab_brain.build_system_prompt()
    assert "mlx" in p
    assert "Qwen3-8B-4bit" in p
