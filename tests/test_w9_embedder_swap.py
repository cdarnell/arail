"""W9 — the production embedder swap (ARCHITECTURE.md, arail2-tier1-integration).

pkb.index_all now embeds via arail.dbspec.embed.embed_documents (LOUD,
propagates EmbeddingError, provenance written last); pkb._semantic_search
now embeds queries via embed_query and the lazy index_all() call on an
empty index is REMOVED (FM11). No Ollama required — the autouse
_stub_embedding_provider fixture in tests/conftest.py stands in.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from arail.dbspec import embed as embed_mod

# Captured at collection time, before any per-test monkeypatch runs, so
# FM15 can restore genuine network behaviour for one test.
_REAL_EMBED_DOCUMENTS = embed_mod.embed_documents
_REAL_EMBED_QUERY = embed_mod.embed_query


@pytest.fixture(autouse=True)
def pkb_index_reset():
    import arail.pkb_index as pki
    pki._reset_for_tests()
    yield
    pki._reset_for_tests()


@pytest.fixture
def isolated_pkb(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import arail.config
    import arail.pkb as pkb
    importlib.reload(arail.config)
    importlib.reload(pkb)
    pkb.scaffold(tmp_path)
    return tmp_path


def _rows_summary(idx) -> list[tuple]:
    """(path, name, mtime, source_kind) per row, sorted — a vector-free,
    numpy-array-free comparison key for "did the table change at all"."""
    table = idx._table()  # noqa: SLF001 — test-only direct read
    if table is None:
        return []
    df = table.to_pandas()
    rows = [
        (r["path"], r["name"], float(r["mtime"]), r["source_kind"])
        for r in df.to_dict("records")
    ]
    return sorted(rows)


# --------------------------------------------------------------------------
# index_all: vectors computed before write, provenance written last
# --------------------------------------------------------------------------

def test_index_all_writes_provenance_after_swap(isolated_pkb):
    import arail.pkb as pkb
    from arail import pkb_provenance
    from arail.dbspec.generated.models_registry import embedding_model, EMBEDDING_DIM

    notes = isolated_pkb / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "a.md").write_text("# a\n")

    result = pkb.index_all(pkb_root=isolated_pkb, include_docs=False)
    assert result["ok"] is True
    assert result["error"] is None
    assert result["skipped"] == 0

    db_path = pkb._vector_db_path(isolated_pkb)
    record = pkb_provenance.read(db_path)
    assert record is not None
    assert record["embedding_model"] == embedding_model().name
    assert record["embedding_dim"] == EMBEDDING_DIM


def test_index_all_embedding_error_writes_nothing_and_leaves_existing_table(
    isolated_pkb, monkeypatch
):
    import arail.pkb as pkb
    from arail.dbspec.embed import EmbeddingError
    from arail.vector_index import VectorIndex

    notes = isolated_pkb / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "a.md").write_text("# a\n")

    # First, a real (stubbed) successful index_all so there's an existing
    # table to protect.
    pkb.index_all(pkb_root=isolated_pkb, include_docs=False)
    db_path = pkb._vector_db_path(isolated_pkb)
    idx = VectorIndex(name="pkb_pages", db_path=db_path, dim=768)
    before = _rows_summary(idx)

    (notes / "b.md").write_text("# b\n")  # a new file the next call would add

    def raising_embed_documents(texts):
        raise EmbeddingError("simulated outage")

    monkeypatch.setattr(embed_mod, "embed_documents", raising_embed_documents)

    with pytest.raises(EmbeddingError):
        pkb.index_all(pkb_root=isolated_pkb, include_docs=False)

    after = _rows_summary(idx)
    assert after == before, (
        "an EmbeddingError must leave the existing table exactly as it "
        "was (replace() is mode='overwrite' -- vectors must be computed "
        "BEFORE any write)")


def test_index_all_empty_corpus_makes_no_embed_call(isolated_pkb, monkeypatch):
    import arail.pkb as pkb

    calls = []
    monkeypatch.setattr(embed_mod, "embed_documents",
                         lambda texts: calls.append(texts) or [])

    result = pkb.index_all(pkb_root=isolated_pkb, include_docs=False)
    assert result["ok"] is True
    assert calls == [], "an empty corpus must not call the embedder at all"


# --------------------------------------------------------------------------
# FM11 — empty index performs ZERO embed calls from inside a search
# --------------------------------------------------------------------------

def test_semantic_search_on_empty_index_makes_zero_embed_calls(isolated_pkb, monkeypatch):
    import arail.pkb as pkb
    import arail.pkb_index as pki

    query_calls = []
    doc_calls = []
    monkeypatch.setattr(embed_mod, "embed_query",
                         lambda q: query_calls.append(q) or [0.0] * 768)
    monkeypatch.setattr(embed_mod, "embed_documents",
                         lambda texts: doc_calls.append(texts) or [])

    # No index built at all -- idx.count() == 0.
    results = pkb._semantic_search("anything", isolated_pkb)

    assert results == []
    assert query_calls == [], "empty index must not trigger an embed_query call"
    assert doc_calls == [], "empty index must NOT trigger a lazy index_all (FM11)"

    ok, reason = pki.embedding_status()
    assert ok is False
    assert "pkb reembed" in reason


def test_semantic_search_never_calls_index_all_on_empty_index(isolated_pkb, monkeypatch):
    """The lazy `if idx.count() == 0: index_all(root)` call is REMOVED."""
    import arail.pkb as pkb

    index_all_calls = []
    monkeypatch.setattr(pkb, "index_all", lambda *a, **k: index_all_calls.append(1))

    pkb._semantic_search("anything", isolated_pkb)

    assert index_all_calls == [], "index_all must never be called from _semantic_search"


def test_semantic_search_query_embedding_error_degrades_and_falls_back(
    isolated_pkb, monkeypatch
):
    import arail.pkb as pkb
    import arail.pkb_index as pki
    from arail.dbspec.embed import EmbeddingError

    notes = isolated_pkb / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "a.md").write_text("# findme content\n")
    pkb.index_all(pkb_root=isolated_pkb, include_docs=False)

    def raising_embed_query(q):
        raise EmbeddingError("simulated outage")

    monkeypatch.setattr(embed_mod, "embed_query", raising_embed_query)

    results = pkb.search("findme", pkb_root=isolated_pkb)

    ok, reason = pki.embedding_status()
    assert ok is False
    assert "simulated outage" in reason

    # search() must fall back to the regex sweep and label results "keyword".
    assert results
    assert all(r["source"] == "keyword" for r in results)


def test_semantic_search_finds_a_real_hit_via_stubbed_embedder(isolated_pkb):
    """Sanity: the swapped query path still actually retrieves — this is a
    mechanics test (does the wiring work), not a quality test (that
    question is answered once, honestly, by scripts/eval/retrieval_ab.py)."""
    import arail.pkb as pkb

    notes = isolated_pkb / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "unique_target.md").write_text(
        "# unique_target\nThis file contains a very unusual marker token: "
        "zzqxflarp9000.\n")
    pkb.index_all(pkb_root=isolated_pkb, include_docs=False)

    results = pkb.search("zzqxflarp9000", pkb_root=isolated_pkb)
    assert results
    assert any(r["path"].endswith("unique_target.md") for r in results)


# --------------------------------------------------------------------------
# FM15 — closed-port MODEL_API_BASE: zero vectors written, index intact
# --------------------------------------------------------------------------

def test_closed_port_ingest_writes_zero_vectors_leaves_existing_index_intact(
    isolated_pkb, monkeypatch
):
    import arail.pkb as pkb
    from arail.dbspec.embed import EmbeddingUnavailable
    from arail.vector_index import VectorIndex

    notes = isolated_pkb / "notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "a.md").write_text("# a\n")

    # Build a real (stubbed) index first, so there's something to protect.
    pkb.index_all(pkb_root=isolated_pkb, include_docs=False)
    db_path = pkb._vector_db_path(isolated_pkb)
    idx = VectorIndex(name="pkb_pages", db_path=db_path, dim=768)
    before = _rows_summary(idx)

    (notes / "b.md").write_text("# b\n")

    # Restore the REAL embed_documents (undo the autouse stub for this one
    # test) and point at a closed port.
    monkeypatch.setattr(embed_mod, "embed_documents", _REAL_EMBED_DOCUMENTS)
    monkeypatch.setenv("MODEL_API_BASE", "http://127.0.0.1:1")

    with pytest.raises(EmbeddingUnavailable) as exc_info:
        pkb.index_all(pkb_root=isolated_pkb, include_docs=False)
    assert "ollama pull nomic-embed-text" in str(exc_info.value)

    after = _rows_summary(idx)
    assert after == before, "closed-port outage must leave the existing index untouched"
