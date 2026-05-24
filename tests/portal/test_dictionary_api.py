"""AI Dictionary API — endpoint wiring + background generation."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from arail import dictionary
from arail.portal import app as portal_app


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    # Redirect persistence to a tmp dir and pretend there is no active goal so
    # the default AI / model-tuning theme applies deterministically.
    monkeypatch.setattr(dictionary, "DICT_DIR", tmp_path / "dictionary")
    monkeypatch.setattr(portal_app.goal_store, "get_current", lambda: None)
    dictionary.clear_override()
    yield
    dictionary.clear_override()


@pytest.fixture
def client():
    return TestClient(portal_app.app)


def test_get_returns_seeded_default(client):
    # The default AI theme ships pre-populated from the curated glossary —
    # no model call, never an empty box.
    r = client.get("/api/dictionary")
    assert r.status_code == 200
    data = r.json()
    assert data["theme"]["slug"] == "ai-model-tuning"
    assert data["theme"]["source"] == "default"
    assert data["count"] > 20
    assert data["generating"] is False
    assert data["can_generate"] is True
    keys = {t["key"] for t in data["terms"]}
    assert "transformer" in keys and "lora" in keys
    # Curated entries carry an instant detail + category (the "fun" payload).
    tx = next(t for t in data["terms"] if t["key"] == "transformer")
    assert tx["detail"]
    assert tx["category"] == "Architecture"
    assert tx["detail_source"] == "curated"


def test_custom_theme_starts_empty(client):
    r = client.post("/api/dictionary/theme", json={"label": "underwater basket weaving"})
    data = r.json()
    assert data["theme"]["source"] == "override"
    assert data["terms"] == []  # no curated seed for custom themes
    assert data["count"] == 0


def test_theme_override_and_clear(client):
    r = client.post("/api/dictionary/theme", json={"label": "trip to Japan"})
    assert r.status_code == 200
    data = r.json()
    assert data["theme"]["source"] == "override"
    assert data["theme"]["label"] == "trip to Japan"
    assert data["theme"]["archetype"] == "travel"

    r2 = client.post("/api/dictionary/theme", json={"clear": True})
    assert r2.json()["theme"]["source"] == "default"


def test_goal_surfaced_as_suggestion_not_theme(client, monkeypatch):
    # An active goal does NOT change the theme; it's offered as a one-click
    # "build a glossary for your goal" suggestion instead.
    monkeypatch.setattr(portal_app.goal_store, "get_current",
                        lambda: {"id": "g1", "goal_text": "trip to Japan", "parsed": {}})
    r = client.get("/api/dictionary")
    data = r.json()
    assert data["theme"]["source"] == "default"        # still the AI glossary
    assert data["theme"]["slug"] == "ai-model-tuning"
    assert data["count"] > 20
    assert data["goal_suggestion"] == "trip to Japan"


def test_no_goal_suggestion_when_theme_matches_goal(client, monkeypatch):
    monkeypatch.setattr(portal_app.goal_store, "get_current",
                        lambda: {"id": "g1", "goal_text": "trip to Japan", "parsed": {}})
    # Switch to the goal as the theme → suggestion should disappear.
    r = client.post("/api/dictionary/theme", json={"label": "trip to Japan"})
    data = r.json()
    assert data["theme"]["source"] == "override"
    assert "goal_suggestion" not in data


def test_theme_requires_label(client):
    r = client.post("/api/dictionary/theme", json={})
    assert r.status_code == 400


def test_full_page_route_renders(client):
    # Must resolve BEFORE the /docs/{path:path} catch-all (which serves *.md).
    r = client.get("/docs/dictionary")
    assert r.status_code == 200
    assert "dict-list" in r.text
    assert "/static/dictionary.js" in r.text


def test_generate_more_rejected_when_generating(client, monkeypatch):
    theme = dictionary.resolve_theme(None)
    portal_app.dictionary_store.set_generating(theme, True)

    calls = {"n": 0}

    def _fake(*a, **k):
        calls["n"] += 1
        return ([], 0)

    monkeypatch.setattr(dictionary, "generate_terms", _fake)

    r = client.post("/api/dictionary/generate-more", json={"count": 5})
    data = r.json()
    assert data["generating"] is True
    assert calls["n"] == 0  # no new job while one is in flight


def test_seed_starts_background_job(client, monkeypatch):
    # Default theme is pre-seeded, so seed only fires for a fresh custom theme.
    dictionary.set_override("a fresh custom topic")
    monkeypatch.setattr(
        dictionary, "generate_terms",
        lambda *a, **k: ([{"term": "Widget", "short_def": "x",
                           "examples": [], "origin": "", "related": []}], 0),
    )
    r = client.post("/api/dictionary/seed", json={})
    assert r.status_code == 202
    assert r.json()["started"] is True


def test_seed_idempotent_on_seeded_default(client):
    # Default already has curated terms → seed returns current state, no 202.
    r = client.post("/api/dictionary/seed", json={})
    assert r.status_code == 200
    assert r.json()["count"] > 0


# A custom theme so generation lands in an empty file (no curated auto-seed).
_CUSTOM = {"label": "custom topic", "source": "override", "archetype": "general", "instruction": "x"}


def test_run_generation_populates(monkeypatch, tmp_path):
    monkeypatch.setattr(dictionary, "DICT_DIR", tmp_path / "dictionary")
    store = dictionary.DictionaryStore()
    monkeypatch.setattr(portal_app, "dictionary_store", store)
    canned = [
        {"term": "LoRA", "short_def": "Low-rank", "examples": [], "origin": "", "related": []},
        {"term": "RAG", "short_def": "Retrieval", "examples": [], "origin": "", "related": []},
    ]
    monkeypatch.setattr(dictionary, "generate_terms", lambda *a, **k: (canned, 0))

    asyncio.run(portal_app._dict_run_generation(_CUSTOM, count=24, avoid_terms=[], label="test"))

    doc = store.load("custom-topic")
    assert {t["term"] for t in doc["terms"]} == {"LoRA", "RAG"}
    assert doc["generating"] is False
    assert doc["last_error"] is None


def test_run_generation_records_error_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(dictionary, "DICT_DIR", tmp_path / "dictionary")
    store = dictionary.DictionaryStore()
    monkeypatch.setattr(portal_app, "dictionary_store", store)

    def _boom(*a, **k):
        raise RuntimeError("model down")

    monkeypatch.setattr(dictionary, "generate_terms", _boom)

    asyncio.run(portal_app._dict_run_generation(_CUSTOM, count=24, avoid_terms=[], label="test"))

    doc = store.load("custom-topic")
    assert doc["terms"] == []
    assert doc["generating"] is False
    assert doc["last_error"]  # an error string was recorded


def test_run_generation_empty_result_records_error(monkeypatch, tmp_path):
    monkeypatch.setattr(dictionary, "DICT_DIR", tmp_path / "dictionary")
    store = dictionary.DictionaryStore()
    monkeypatch.setattr(portal_app, "dictionary_store", store)
    monkeypatch.setattr(dictionary, "generate_terms", lambda *a, **k: ([], -1))

    asyncio.run(portal_app._dict_run_generation(_CUSTOM, count=24, avoid_terms=[], label="test"))

    doc = store.load("custom-topic")
    assert doc["terms"] == []
    assert doc["last_error"] == "generation_failed"


def test_expand_enriches_curated_term(client, monkeypatch):
    monkeypatch.setattr(dictionary, "expand_term",
                        lambda *a, **k: "A transformer reads a whole sentence at once.")
    r = client.post("/api/dictionary/expand", json={"term": "Transformer"})
    data = r.json()
    assert data["ok"] is True
    assert data["cached"] is False
    assert "transformer" in data["detail"].lower()

    # Persisted on the term with detail_source=buddy → second call is cached.
    theme = dictionary.resolve_theme(None)
    term = portal_app.dictionary_store.find_term(theme, "transformer")
    assert term["detail_source"] == "buddy"
    r2 = client.post("/api/dictionary/expand", json={"term": "Transformer"})
    assert r2.json()["cached"] is True


def test_expand_requires_term(client):
    r = client.post("/api/dictionary/expand", json={})
    assert r.status_code == 400


def test_expand_graceful_when_model_fails(client, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("model down")
    monkeypatch.setattr(dictionary, "expand_term", _boom)
    r = client.post("/api/dictionary/expand", json={"term": "Attention"})
    data = r.json()
    assert data["ok"] is False
    assert "couldn't" in data["message"].lower() or "could not" in data["message"].lower()


def test_expand_empty_reply_is_graceful(client, monkeypatch):
    monkeypatch.setattr(dictionary, "expand_term", lambda *a, **k: "")
    r = client.post("/api/dictionary/expand", json={"term": "Quantization"})
    assert r.json()["ok"] is False
