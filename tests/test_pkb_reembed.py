"""./arailctl pkb reembed (C2 in ARCHITECTURE.md, arail2-tier1-integration).

No Ollama required — tests/conftest.py's autouse _stub_embedding_provider
fixture stubs embed_documents/embed_query at the module boundary.
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path

import pytest

import arail.pkb_reembed as reembed


def _make_pkb(tmp_path: Path, n: int = 6) -> Path:
    pkb_root = tmp_path / "pkb"
    notes = pkb_root / "notes"
    notes.mkdir(parents=True)
    for i in range(n):
        (notes / f"doc{i}.md").write_text(f"# doc {i}\ncontent {i}\n")
    return pkb_root


# --------------------------------------------------------------------------
# happy path
# --------------------------------------------------------------------------

def test_full_run_writes_provenance_and_swaps_table(tmp_path):
    pkb_root = _make_pkb(tmp_path)
    result = reembed.run(pkb_root, include_docs=False)

    assert result["interrupted"] is False
    assert result["completed"] == result["total"] == 6

    live_table = pkb_root / ".cache" / "lancedb" / "pkb_pages.lance"
    assert live_table.exists()

    from arail import pkb_provenance
    record = pkb_provenance.read(pkb_root / ".cache" / "lancedb")
    assert record is not None
    assert record["schema"] == pkb_provenance.SCHEMA
    assert record["rows"] == 6

    # Shadow build and checkpoint are cleaned up after a successful swap.
    assert not (pkb_root / ".cache" / "lancedb.next").exists()
    assert not reembed._checkpoint_path(pkb_root).exists()


def test_second_run_backs_up_previous_live_table(tmp_path):
    pkb_root = _make_pkb(tmp_path)
    reembed.run(pkb_root, include_docs=False)
    result2 = reembed.run(pkb_root, include_docs=False)

    assert result2["backup"] is not None
    assert Path(result2["backup"]).exists()
    assert Path(result2["backup"]).name.startswith("pkb_pages.lance.bak-")


def test_dry_run_writes_nothing(tmp_path):
    pkb_root = _make_pkb(tmp_path)
    result = reembed.run(pkb_root, dry_run=True, include_docs=False)

    assert result["dry_run"] is True
    assert result["total"] == 6
    assert not (pkb_root / ".cache").exists()


def test_empty_corpus_writes_zero_rows(tmp_path):
    pkb_root = tmp_path / "pkb"
    pkb_root.mkdir()
    result = reembed.run(pkb_root, include_docs=False)
    assert result["completed"] == 0
    assert result["total"] == 0


# --------------------------------------------------------------------------
# FM13 — SIGINT mid-run: live table unchanged, checkpoint written, resume
# --------------------------------------------------------------------------

def test_sigint_mid_run_leaves_live_table_untouched_and_writes_checkpoint(tmp_path, monkeypatch):
    pkb_root = _make_pkb(tmp_path, n=12)

    from arail.dbspec import embed as embed_mod
    from arail.vector_index import hash_embedding

    call_count = {"n": 0}

    def flaky_embed_documents(texts):
        call_count["n"] += 1
        if call_count["n"] == 2:
            os.kill(os.getpid(), signal.SIGINT)
        return [hash_embedding(t, dim=768) for t in texts]

    monkeypatch.setattr(embed_mod, "embed_documents", flaky_embed_documents)

    result = reembed.run(pkb_root, batch_size=3, include_docs=False)

    assert result["interrupted"] is True
    assert 0 < result["completed"] < result["total"] == 12

    live_table = pkb_root / ".cache" / "lancedb" / "pkb_pages.lance"
    assert not live_table.exists(), "an interrupted run must never touch the live table"

    checkpoint = reembed._load_checkpoint(pkb_root)
    assert checkpoint is not None
    assert checkpoint["schema"] == reembed.SCHEMA
    assert len(checkpoint["completed_paths"]) == result["completed"]


def test_resume_after_sigint_completes_to_full_row_count(tmp_path, monkeypatch):
    pkb_root = _make_pkb(tmp_path, n=12)

    from arail.dbspec import embed as embed_mod
    from arail.vector_index import hash_embedding

    call_count = {"n": 0}

    def flaky_embed_documents(texts):
        call_count["n"] += 1
        if call_count["n"] == 2:
            os.kill(os.getpid(), signal.SIGINT)
        return [hash_embedding(t, dim=768) for t in texts]

    monkeypatch.setattr(embed_mod, "embed_documents", flaky_embed_documents)
    interrupted_result = reembed.run(pkb_root, batch_size=3, include_docs=False)
    assert interrupted_result["interrupted"] is True

    # Un-flake the embedder for the resume.
    monkeypatch.setattr(
        embed_mod, "embed_documents",
        lambda texts: [hash_embedding(t, dim=768) for t in texts])

    result = reembed.run(pkb_root, resume=True, batch_size=3, include_docs=False)

    assert result["interrupted"] is False
    assert result["completed"] == result["total"] == 12

    live_table = pkb_root / ".cache" / "lancedb" / "pkb_pages.lance"
    assert live_table.exists()
    assert not reembed._checkpoint_path(pkb_root).exists()

    import lancedb  # type: ignore[import-not-found]
    db = lancedb.connect(str(pkb_root / ".cache" / "lancedb"))
    table = db.open_table("pkb_pages")
    assert table.count_rows() == 12


def test_resume_refuses_on_checkpoint_spec_mismatch(tmp_path):
    pkb_root = _make_pkb(tmp_path, n=3)
    reembed._write_checkpoint(pkb_root, {
        "schema": reembed.SCHEMA, "model": "some-other-model", "dim": 999,
        "spec_sha256": "not-the-current-spec", "started_at": "x",
        "total": 3, "completed_paths": [], "batch": 32,
    })

    with pytest.raises(reembed.CheckpointSpecMismatch):
        reembed.run(pkb_root, resume=True, include_docs=False)

    # Refusing to mix spaces must not touch the live table.
    assert not (pkb_root / ".cache" / "lancedb" / "pkb_pages.lance").exists()


def test_resume_with_no_checkpoint_starts_fresh(tmp_path):
    pkb_root = _make_pkb(tmp_path, n=4)
    result = reembed.run(pkb_root, resume=True, include_docs=False)
    assert result["interrupted"] is False
    assert result["completed"] == 4


# --------------------------------------------------------------------------
# EmbeddingError propagates, writes no live/partial table
# --------------------------------------------------------------------------

def test_embedding_error_propagates_and_writes_nothing_live(tmp_path, monkeypatch):
    pkb_root = _make_pkb(tmp_path, n=3)
    from arail.dbspec import embed as embed_mod
    from arail.dbspec.embed import EmbeddingError

    def raising_embed_documents(texts):
        raise EmbeddingError("simulated outage")

    monkeypatch.setattr(embed_mod, "embed_documents", raising_embed_documents)

    with pytest.raises(EmbeddingError):
        reembed.run(pkb_root, include_docs=False)

    assert not (pkb_root / ".cache" / "lancedb" / "pkb_pages.lance").exists()


# --------------------------------------------------------------------------
# CLI (main()) exit codes
# --------------------------------------------------------------------------

def test_main_missing_pkb_root_exits_2(tmp_path, capsys):
    rc = reembed.main(["--pkb-root", str(tmp_path / "nope"), "--world-label", "x"])
    assert rc == 2


def test_main_dry_run_exits_0_and_prints_eta(tmp_path, capsys):
    pkb_root = _make_pkb(tmp_path, n=2)
    rc = reembed.main(["--pkb-root", str(pkb_root), "--world-label", "x", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "dry-run" in out


def test_main_happy_path_exits_0(tmp_path, capsys, monkeypatch):
    pkb_root = _make_pkb(tmp_path, n=2)
    # main() always calls run() with include_docs=True (default) via CLI;
    # keep this fast by stubbing docs_registry to empty.
    import arail.portal.docs_registry as reg
    monkeypatch.setattr(reg, "all_docs", lambda: ())
    rc = reembed.main(["--pkb-root", str(pkb_root), "--world-label", "x"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "done: 2/2" in out
