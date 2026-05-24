"""Curated AI glossary seed — well-formed and reasonably complete."""

from __future__ import annotations

from arail.glossary_seed import seed_entries
from arail.dictionary import norm_key


def test_seed_is_substantial():
    entries = seed_entries()
    assert len(entries) >= 30


def test_every_entry_well_formed():
    for e in seed_entries():
        assert e["term"].strip()
        assert e["short_def"].strip()
        assert e["detail"].strip()
        assert e["category"].strip()
        assert e["detail_source"] == "curated"
        assert e["builtin"] is True
        assert e["key"] == norm_key(e["term"])
        assert isinstance(e["related"], list)


def test_keys_unique():
    keys = [e["key"] for e in seed_entries()]
    assert len(keys) == len(set(keys))


def test_core_terms_present():
    keys = {e["key"] for e in seed_entries()}
    for must in ("transformer", "lora", "embedding", "fine-tuning", "quantization", "rag"):
        assert must in keys, must


def test_categories_present():
    cats = {e["category"] for e in seed_entries()}
    # A few of the section headings should exist for the category filter to be useful.
    assert {"Architecture", "Training", "Fine-Tuning"} <= cats


def test_fresh_dicts_each_call():
    a = seed_entries()
    a[0]["term"] = "MUTATED"
    b = seed_entries()
    assert b[0]["term"] != "MUTATED"
