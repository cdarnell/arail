"""Lab brain smoke tests — system prompt composition."""

from __future__ import annotations

import pytest

from arail import brand, lab_brain


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
    # Brand layer — default is "Autoresearch AI Lab"
    assert "Autoresearch AI Lab" in p
    assert "A learn-by-doing AI research lab" in p
    # Capabilities reference is included by default
    assert "Model router" in p
    assert "Scheduler" in p
    assert "Personal Knowledge Base" in p
    assert "./arail" in p
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


def test_build_chat_messages_includes_system_and_user(monkeypatch):
    monkeypatch.setattr(lab_brain, "retrieve_chat_context", lambda *_args, **_kwargs: [])
    messages = lab_brain.build_chat_messages("What can you do?", [{"role": "assistant", "content": "Hi"}])
    assert messages[0]["role"] == "system"
    assert messages[1] == {"role": "assistant", "content": "Hi"}
    assert messages[-1] == {"role": "user", "content": "What can you do?"}


def test_build_chat_messages_appends_pkb_context(monkeypatch):
    monkeypatch.setattr(
        lab_brain,
        "retrieve_chat_context",
        lambda *_args, **_kwargs: [{
            "path": "notes/test.md",
            "snippets": ["Important local fact"],
            "match_count": 2,
        }],
    )
    messages = lab_brain.build_chat_messages("Use local knowledge", None)
    assert "Retrieved knowledge base context" in messages[0]["content"]
    assert "notes/test.md" in messages[0]["content"]
    assert "Important local fact" in messages[0]["content"]


def test_retrieve_chat_context_prefers_exact_phrase(monkeypatch):
    import arail.pkb as pkb

    def fake_search(term):
        if term == "vector index":
            return [{
                "path": "notes/vector-index.md",
                "name": "vector-index.md",
                "match_count": 1,
                "snippets": ["Vector index design notes"],
            }]
        if term == "vector":
            return [{
                "path": "notes/vector.md",
                "name": "vector.md",
                "match_count": 3,
                "snippets": ["Generic vector notes"],
            }]
        if term == "index":
            return [{
                "path": "notes/index.md",
                "name": "index.md",
                "match_count": 3,
                "snippets": ["Generic index notes"],
            }]
        return []

    monkeypatch.setattr(pkb, "search", fake_search)
    results = lab_brain.retrieve_chat_context("vector index", max_results=3)
    assert results[0]["path"] == "notes/vector-index.md"


def test_retrieve_chat_context_reorders_snippets_by_token_coverage(monkeypatch):
    import arail.pkb as pkb

    def fake_search(_term):
        return [{
            "path": "notes/retrieval.md",
            "name": "retrieval.md",
            "match_count": 1,
            "snippets": [
                "This line is generic.",
                "Retriever cache invalidation and ranking behavior.",
            ],
        }]

    monkeypatch.setattr(pkb, "search", fake_search)
    results = lab_brain.retrieve_chat_context("retriever ranking", max_results=1)
    assert results[0]["snippets"][0] == "Retriever cache invalidation and ranking behavior."


def test_state_block_includes_backend(monkeypatch):
    monkeypatch.setenv("MODEL_BACKEND", "mlx")
    monkeypatch.setenv("MODEL_NAME", "mlx-community/Qwen3-8B-4bit")
    p = lab_brain.build_system_prompt()
    assert "mlx" in p
    assert "Qwen3-8B-4bit" in p


def test_state_block_includes_agent_workflow_memory(monkeypatch):
    import arail.agent_workflows as agent_workflows

    monkeypatch.setattr(
        agent_workflows,
        "list_agent_workflows",
        lambda: [{
            "agent_id": "researcher",
            "status": "running",
            "objective": "Write a better retrieval plan",
            "current_task": "Designing experiments",
            "next_step": "Run experiments",
            "completed_steps": ["Planned hypotheses"],
            "pause_reason": "",
            "chatter": {"too_chatty": False, "global_cooldown_sec": 300},
        }],
    )
    prompt = lab_brain.build_system_prompt()
    assert "Agent workflow memory" in prompt
    assert "Write a better retrieval plan" in prompt
    assert "Designing experiments" in prompt
