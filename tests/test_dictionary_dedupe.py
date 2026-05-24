"""DictionaryStore.add_terms — dedupe + persistence."""

from __future__ import annotations

import json

import pytest

from arail import dictionary
from arail.dictionary import DictionaryStore

# A non-default theme so the curated-glossary auto-seed (default theme only)
# never interferes with the dedupe/count assertions. slug -> "test-topic".
THEME = {"label": "Test Topic", "source": "override", "archetype": "general", "instruction": "x"}


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(dictionary, "DICT_DIR", tmp_path / "dictionary")
    return DictionaryStore()


def _entry(term, **kw):
    e = {"term": term, "short_def": kw.get("short_def", "d"),
         "examples": [], "origin": "", "related": []}
    return e


def test_add_terms_counts(store):
    added, skipped = store.add_terms(THEME, [_entry("LoRA"), _entry("RAG")])
    assert (added, skipped) == (2, 0)


def test_cross_batch_dedupe(store):
    store.add_terms(THEME, [_entry("LoRA")])
    added, skipped = store.add_terms(THEME, [_entry("lora"), _entry("RAG")])
    assert added == 1  # RAG only
    assert skipped == 1  # lora dupe


def test_case_whitespace_punctuation_variants(store):
    added, skipped = store.add_terms(THEME, [
        _entry("Token"),
        _entry("  token "),
        _entry("Token."),
    ])
    assert added == 1
    assert skipped == 2


def test_empty_term_skipped(store):
    added, skipped = store.add_terms(THEME, [_entry(""), _entry("Real")])
    assert added == 1
    assert skipped == 1


def test_persistence_round_trip(store):
    store.add_terms(THEME, [_entry("Embedding")])
    doc = store.load("test-topic")
    assert doc is not None
    assert doc["terms"][0]["term"] == "Embedding"
    assert doc["generating"] is False


def test_atomic_save_leaves_no_tmp(store, tmp_path):
    store.add_terms(THEME, [_entry("X")])
    leftovers = list((tmp_path / "dictionary").glob("*.tmp"))
    assert leftovers == []


def test_set_generating_flag(store):
    store.set_generating(THEME, True)
    assert store.load("test-topic")["generating"] is True
    store.set_generating(THEME, False, error="boom")
    doc = store.load("test-topic")
    assert doc["generating"] is False
    assert doc["last_error"] == "boom"


def test_load_missing_returns_none(store):
    assert store.load("does-not-exist") is None


def test_corrupt_file_returns_none(store, tmp_path):
    bad = tmp_path / "dictionary" / "broken.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text("{ this is not json ")
    assert store.load("broken") is None
