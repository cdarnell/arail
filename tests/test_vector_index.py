"""Tests for the shared LanceDB vector index and its consumers.

Covers:
  - hash_embedding determinism + dimension contract
  - VectorIndex round-trip (replace → search → count)
  - PKB semantic search returns the most-related primer for a fuzzy query
  - PKB falls back to regex when LanceDB has nothing matching exactly
  - ExperimentTracker.search ranks the right experiment for a fuzzy query
  - /api/experiments/search endpoint shape
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── vector_index foundation ───────────────────────────────────────────────

def test_hash_embedding_is_deterministic():
    from arail.vector_index import hash_embedding
    a = hash_embedding("speculative decoding done right")
    b = hash_embedding("speculative decoding done right")
    assert a == b
    assert len(a) == 128


def test_hash_embedding_handles_empty_input():
    from arail.vector_index import hash_embedding
    v = hash_embedding("")
    assert len(v) == 128
    assert all(x == 0.0 for x in v)


def test_vector_index_round_trip(tmp_path: Path):
    from arail.vector_index import VectorIndex, hash_embedding
    idx = VectorIndex(name="t", db_path=tmp_path / "db")
    rows = [
        {"path": "a.md", "name": "a", "vector": hash_embedding("airllm layer streaming")},
        {"path": "b.md", "name": "b", "vector": hash_embedding("crop rotation soil")},
    ]
    written = idx.replace(rows)
    assert written == 2
    assert idx.count() == 2

    hits = idx.search("airllm streaming inference", k=2)
    assert hits, "expected at least one hit"
    assert hits[0]["path"] == "a.md"
    assert "score" in hits[0]
    assert 0.0 <= hits[0]["score"] <= 1.0


def test_vector_index_returns_empty_when_table_missing(tmp_path: Path):
    from arail.vector_index import VectorIndex
    idx = VectorIndex(name="never_written", db_path=tmp_path / "db")
    assert idx.count() == 0
    assert idx.search("anything") == []


def test_vector_index_replace_with_empty_drops_table(tmp_path: Path):
    """Calling replace([]) should leave the index in a clean empty state."""
    from arail.vector_index import VectorIndex, hash_embedding
    idx = VectorIndex(name="t", db_path=tmp_path / "db")
    idx.replace([{"path": "a.md", "vector": hash_embedding("x")}])
    assert idx.count() == 1
    idx.replace([])
    assert idx.count() == 0


# ── PKB semantic search ────────────────────────────────────────────────────

def test_pkb_search_finds_semantic_match_without_keyword_overlap(tmp_path: Path, monkeypatch):
    """The whole point of the upgrade: a goal worded one way should
    surface a primer worded another way."""
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib
    import arail.config
    import arail.pkb as pkb
    importlib.reload(arail.config)
    importlib.reload(pkb)

    pkb.scaffold(tmp_path)
    (tmp_path / "sources" / "articles").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources" / "articles" / "airllm-primer.md").write_text(
        "# AirLLM layer streaming\n\nLoad layers from disk and stream the residual stream.\n"
    )
    (tmp_path / "sources" / "articles" / "crops.md").write_text(
        "# Crop rotation\n\nPlanting cycles to maintain nitrogen levels in soil.\n"
    )

    pkb.index_all(tmp_path)
    hits = pkb.search("how do I tune AirLLM throughput")
    assert hits, "semantic search should find AirLLM primer"
    assert hits[0]["path"].endswith("airllm-primer.md")
    assert hits[0].get("source") == "semantic"


def test_pkb_search_falls_back_to_regex_when_index_cold(tmp_path: Path, monkeypatch):
    """Exact-substring queries still work even before index_all is called.

    When the LanceDB cache is missing the auto-rebuild fires; if that
    finds matching content semantic returns it, else regex catches the
    exact term."""
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib, arail.config, arail.pkb as pkb
    importlib.reload(arail.config)
    importlib.reload(pkb)

    pkb.scaffold(tmp_path)
    (tmp_path / "sources" / "articles" / "errors.md").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "sources" / "articles" / "errors.md").write_text(
        "# Error log\n\nSeen: ECONNREFUSED on port 8443 during code-server boot.\n"
    )

    hits = pkb.search("ECONNREFUSED")
    assert hits, "expected regex fallback to find the literal token"
    assert hits[0]["name"] == "errors.md"


# ── Experiment tracker search ──────────────────────────────────────────────

def test_experiment_tracker_search_ranks_relevant_first(tmp_path: Path):
    from arail.skills.experiment_tracker import ExperimentTracker
    tr = ExperimentTracker(experiments_dir=tmp_path)
    e_kv = tr.create(
        "KV-cache 4-bit quantization improves Llama 70B decode rate",
        "A/B benchmark", {"bits": 4}, domain="inference",
    )
    e_spec = tr.create(
        "Speculative decoding with a 7B draft halves time-to-first-token",
        "wall-clock measurements", {"draft": "7B"}, domain="inference",
    )
    e_farm = tr.create(
        "Crop rotation increases soil nitrogen retention in zone 7",
        "soil sampling", {"cycles": 3}, domain="farming",
    )

    hits = tr.search("kv cache quantization speedups", k=3)
    assert hits, "expected at least one hit"
    assert hits[0]["id"] == e_kv["id"]
    assert hits[0].get("match_source") == "semantic"

    hits = tr.search("draft model decoding", k=3)
    assert hits and hits[0]["id"] == e_spec["id"]

    hits = tr.search("nitrogen levels in farmland", k=3)
    assert hits and hits[0]["id"] == e_farm["id"]


def test_experiment_tracker_search_status_filter(tmp_path: Path):
    from arail.skills.experiment_tracker import ExperimentTracker
    tr = ExperimentTracker(experiments_dir=tmp_path)
    planning = tr.create("draft hypothesis", "method", {})
    tr.start(planning["id"])  # → in_progress

    hits = tr.search("draft", status="planning", k=5)
    # The only "draft" experiment is now in_progress, so planning filter
    # should return zero matches even though the corpus contains it.
    assert all(h["status"] == "planning" for h in hits)


# ── /api/experiments/search endpoint ───────────────────────────────────────

def test_api_experiments_search_returns_ranked_hits(monkeypatch, tmp_path):
    """End-to-end: portal endpoint hands back ranked semantic results.

    We swap the live ``tracker`` singleton for one rooted at ``tmp_path``
    so this test never writes into the real ``lab/data/experiments``.
    Reload-based isolation isn't reliable here because the tracker is
    instantiated at import time and module caching keeps the original
    instance alive across importlib.reload.
    """
    from arail.skills.experiment_tracker import ExperimentTracker
    import arail.portal.app as app_mod

    test_tracker = ExperimentTracker(experiments_dir=tmp_path)
    monkeypatch.setattr(app_mod, "tracker", test_tracker)

    e1 = test_tracker.create(
        "Lower KV cache bits to speed up decode",
        "benchmark", {"bits": 4}, domain="inference",
    )
    test_tracker.create(
        "Optimize disk-stream layer prefetch for AirLLM",
        "tracing", {}, domain="inference",
    )

    client = TestClient(app_mod.app)
    r = client.get("/api/experiments/search", params={"q": "kv cache speedups"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "kv cache speedups"
    assert body["hits"], "expected at least one hit"
    assert body["hits"][0]["id"] == e1["id"]


def test_api_experiments_search_empty_query_is_safe(monkeypatch, tmp_path):
    from arail.skills.experiment_tracker import ExperimentTracker
    import arail.portal.app as app_mod

    monkeypatch.setattr(app_mod, "tracker", ExperimentTracker(experiments_dir=tmp_path))

    client = TestClient(app_mod.app)
    r = client.get("/api/experiments/search", params={"q": ""})
    assert r.status_code == 200
    assert r.json()["hits"] == []
