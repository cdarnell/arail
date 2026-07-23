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


def test_remove_pack_clears_seed_dir(tmp_path: Path):
    """Install then remove the model-building pack — only seed files
    should disappear; everything else under lab/pkb/ stays."""
    from arail import pkb_seed

    pkm.scaffold(tmp_path)

    # Drop a user note to confirm remove_pack doesn't touch it.
    user_note = tmp_path / "notes" / "my-thoughts.md"
    user_note.parent.mkdir(parents=True, exist_ok=True)
    user_note.write_text("My own writing.\n")

    install = pkb_seed.install_pack("model-building", pkb_root=tmp_path)
    assert install["ok"] is True
    seed_dir = tmp_path / "sources" / "seeds" / "model-building"
    assert seed_dir.exists()
    seeded_files_before = sum(1 for _ in seed_dir.glob("*.md"))
    assert seeded_files_before > 0

    result = pkb_seed.remove_pack("model-building", pkb_root=tmp_path)
    assert result["ok"] is True
    assert result["removed"] == seeded_files_before
    assert not seed_dir.exists() or not any(seed_dir.glob("*.md"))

    # The user's own note must survive.
    assert user_note.exists()
    assert user_note.read_text() == "My own writing.\n"

    # Idempotent — calling remove again on an already-empty pack is fine.
    again = pkb_seed.remove_pack("model-building", pkb_root=tmp_path)
    assert again["ok"] is True
    assert again["removed"] == 0


def test_remove_pack_rejects_unknown_pack(tmp_path: Path):
    from arail import pkb_seed
    pkm.scaffold(tmp_path)
    result = pkb_seed.remove_pack("not-a-real-pack", pkb_root=tmp_path)
    assert result["ok"] is False
    assert "unknown pack" in result["error"]


# ===========================================================================
# MODEL-BUILDING SEED PACK — base-model primer (MODEL-TIERS-V2 QA item 16)
# The 09-choosing-a-base-model.md primer ships in the model-building seed pack;
# the pack is now 10 files. Guards against the primer silently dropping out.
# OOM-safe: pure file I/O, no model load.
# ===========================================================================

def test_model_building_pack_has_ten_files_including_base_model_primer():
    """The model-building seed pack must declare exactly 10 primers, including
    09-choosing-a-base-model.md (added with the two-tier reframe)."""
    from arail import pkb_seed

    pack = pkb_seed._PACKS["model-building"]
    filenames = [fn for fn, _ in pack["files"]]
    assert len(filenames) == 10, (
        f"model-building pack must have 10 primers, got {len(filenames)}: {filenames}"
    )
    assert "09-choosing-a-base-model.md" in filenames, (
        "the base-model-choice primer must be in the model-building pack"
    )
    # No accidental duplicate filenames.
    assert len(set(filenames)) == len(filenames), "duplicate primer filenames"


def test_base_model_primer_installs_to_disk(tmp_path: Path):
    """Installing the pack writes 09-choosing-a-base-model.md to the seed dir
    with non-trivial content. OOM-safe: file write only, no model load."""
    from arail import pkb_seed

    pkm.scaffold(tmp_path)
    result = pkb_seed.install_pack("model-building", pkb_root=tmp_path)
    assert result["ok"] is True

    seed_dir = tmp_path / "sources" / "seeds" / "model-building"
    primer = seed_dir / "09-choosing-a-base-model.md"
    assert primer.exists(), "base-model primer must be installed to the seed dir"
    body = primer.read_text()
    assert len(body) > 200, "primer must be non-trivial"
    # The pack as a whole installs 10 markdown files.
    installed_md = sorted(p.name for p in seed_dir.glob("*.md"))
    assert len(installed_md) == 10, (
        f"expected 10 installed primers, got {len(installed_md)}: {installed_md}"
    )


def test_conversations_excluded_from_index(tmp_path: Path):
    """WP6: conversation memory (incl. meta.json titles) is never yielded by the
    searchable-file iterator — closes the meta.json title leak into /api/pkb/search."""
    root = tmp_path / "pkb"
    (root / "conversations" / "c1").mkdir(parents=True)
    (root / "conversations" / "c1" / "meta.json").write_text('{"title": "SECRET-XYZ"}')
    (root / "conversations" / "c1" / "transcript.jsonl").write_text('{"e": 1}\n')
    (root / "sources").mkdir(parents=True)
    (root / "sources" / "note.md").write_text("indexable knowledge")

    yielded = [p.name for p, _ in pkm._iter_pkb_files(root)]
    assert "note.md" in yielded              # real KB content still indexed
    assert "meta.json" not in yielded         # title leak closed
    assert "transcript.jsonl" not in yielded  # chat log never indexed
