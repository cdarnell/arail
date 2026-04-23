"""PKB smoke tests — scaffold creates the expected tree, ingest moves files."""

from __future__ import annotations

from pathlib import Path

import pytest

from arail import pkb as pkm


EXPECTED_DIRS = [
    "inbox",
    "sources/papers", "sources/articles", "sources/datasets",
    "agents/research", "agents/experiments", "agents/synthesis",
    "agents/recommendations",
    "notes/scratch",
    "compiled/reports", "compiled/summaries", "compiled/exports",
    "inference/prompts", "inference/completions", "inference/chains",
]


def test_scaffold_creates_full_tree(tmp_path: Path):
    root = pkm.scaffold(tmp_path)
    for sub in EXPECTED_DIRS:
        assert (root / sub).is_dir(), f"missing: {sub}"


def test_scaffold_is_idempotent(tmp_path: Path):
    pkm.scaffold(tmp_path)
    root = pkm.scaffold(tmp_path)
    for sub in EXPECTED_DIRS:
        assert (root / sub).is_dir()


def test_ingest_routes_by_extension(tmp_path: Path):
    pkm.scaffold(tmp_path)
    (tmp_path / "inbox" / "paper.pdf").write_text("fake pdf")
    (tmp_path / "inbox" / "notes.md").write_text("# hello")
    (tmp_path / "inbox" / "data.csv").write_text("a,b\n1,2\n")

    result = pkm.ingest(tmp_path)
    assert result["moved"] == 3
    assert result["errors"] == []

    papers = list((tmp_path / "sources" / "papers").glob("*paper.pdf"))
    articles = list((tmp_path / "sources" / "articles").glob("*notes.md"))
    datasets = list((tmp_path / "sources" / "datasets").glob("*data.csv"))
    assert papers and articles and datasets


def test_ingest_empty_inbox_is_safe(tmp_path: Path):
    pkm.scaffold(tmp_path)
    result = pkm.ingest(tmp_path)
    assert result["moved"] == 0
    assert result["urls_fetched"] == 0


def test_compile_index_writes_index_md(tmp_path: Path):
    pkm.scaffold(tmp_path)
    (tmp_path / "notes" / "thought.md").write_text(
        "# Thought\n\nSome content with #tag1 and #tag2.\n"
    )
    result = pkm.compile_index(tmp_path)
    assert (tmp_path / "index.md").exists()
    assert result["total"] >= 1
    assert "tag1" in result["tags"]
    assert "tag2" in result["tags"]


def test_browse_returns_section_snapshot(tmp_path: Path):
    pkm.scaffold(tmp_path)
    (tmp_path / "notes" / "a.md").write_text("a")
    snapshot = pkm.browse(tmp_path)
    assert snapshot["exists"] is True
    assert snapshot["sections"]["notes"]["count"] == 1


def test_browse_hides_only_legacy_experiment_stubs(tmp_path: Path):
    pkm.scaffold(tmp_path)
    experiments = tmp_path / "agents" / "experiments"
    (experiments / "legacy.md").write_text(
        "# Experiment deadbeef\n\n"
        "**Hypothesis:** [Hypothesis 1]\n"
        "**Domain:** ml-research\n"
        "**Status:** completed\n"
    )
    (experiments / "short-note.md").write_text(
        "# Experiment livebeef\n\n"
        "Short user note about a failed run; revisit tomorrow.\n"
    )
    (experiments / "structured.md").write_text(
        "# Experiment goodbeef\n\n"
        "**Outcome:** supported\n"
        "**Hypothesis:** test idea\n\n"
        "## Conclusion\n\n"
        "Useful result.\n"
    )

    snapshot = pkm.browse(tmp_path)
    items = {item["name"] for item in snapshot["sections"]["agents"]["items"]}

    assert "legacy.md" not in items
    assert "short-note.md" in items
    assert "structured.md" in items
