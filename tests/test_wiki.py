"""Wiki compiler smoke tests — frontmatter, wikilinks, backlinks, graph."""

from __future__ import annotations

from pathlib import Path

import pytest

from oglab import wiki


# ── Frontmatter ──────────────────────────────────────────────────────────

def test_frontmatter_roundtrip():
    text = (
        "---\n"
        "title: My Page\n"
        "tags: [alpha, beta]\n"
        "aliases: [mp, my-pg]\n"
        "---\n"
        "# Body\n\nSome content.\n"
    )
    meta, body = wiki.parse_frontmatter(text)
    assert meta["title"] == "My Page"
    assert meta["tags"] == ["alpha", "beta"]
    assert meta["aliases"] == ["mp", "my-pg"]
    assert body.startswith("# Body")


def test_frontmatter_missing_block_is_noop():
    text = "# Just markdown\n\nNo frontmatter here.\n"
    meta, body = wiki.parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_frontmatter_malformed_does_not_crash():
    text = "---\nthis is not: valid:: yaml [garbage\n---\n# body\n"
    meta, body = wiki.parse_frontmatter(text)
    # We still split the block; the one key on that line parses minimally.
    # The important thing is that it doesn't raise and returns a usable body.
    assert body.startswith("# body")


def test_frontmatter_value_coercion():
    text = "---\ncount: 42\nflag: true\nname: \"quoted\"\n---\nbody"
    meta, _ = wiki.parse_frontmatter(text)
    assert meta["count"] == 42
    assert meta["flag"] is True
    assert meta["name"] == "quoted"


# ── Wikilink parsing ─────────────────────────────────────────────────────

def test_wikilink_simple():
    refs = wiki.parse_wikilinks("See [[scheduler]] for details.")
    assert len(refs) == 1
    assert refs[0].target == "scheduler"
    assert refs[0].alias is None
    assert refs[0].anchor is None


def test_wikilink_with_alias():
    refs = wiki.parse_wikilinks("See [[scheduler|work windows]] for details.")
    assert refs[0].target == "scheduler"
    assert refs[0].alias == "work windows"


def test_wikilink_with_anchor():
    refs = wiki.parse_wikilinks("See [[scheduler#heavy-hours]] for details.")
    assert refs[0].target == "scheduler"
    assert refs[0].anchor == "heavy-hours"


def test_wikilink_alias_plus_anchor():
    refs = wiki.parse_wikilinks("Check [[scheduler#heavy|after hours]] now.")
    assert refs[0].target == "scheduler"
    assert refs[0].anchor == "heavy"
    assert refs[0].alias == "after hours"


def test_wikilink_multiple_refs():
    body = "Link to [[one]], [[two|second]], and [[three#top]]."
    refs = wiki.parse_wikilinks(body)
    assert [r.target for r in refs] == ["one", "two", "three"]


def test_wikilink_no_match_empty_list():
    assert wiki.parse_wikilinks("just plain text with no links") == []


# ── Slug generation ─────────────────────────────────────────────────────

def test_slug_lowercases():
    assert wiki.slugify("My Page Title") == "my-page-title"


def test_slug_strips_unicode_accents():
    assert wiki.slugify("Café au lait") == "cafe-au-lait"


def test_slug_preserves_path_separators():
    assert wiki.slugify("agents/research/My Report") == "agents/research/my-report"


def test_slug_collapses_repeats():
    assert wiki.slugify("foo---bar__baz  qux") == "foo-bar-baz-qux"


def test_slug_strips_edges():
    assert wiki.slugify("---hello---") == "hello"


# ── Page index + backlinks ──────────────────────────────────────────────

def test_build_page_index_parses_frontmatter_and_body(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "alpha.md").write_text(
        "---\ntitle: Alpha\ntags: [x]\n---\n# Alpha\n\nLinks to [[beta]].\n"
    )
    (tmp_path / "notes" / "beta.md").write_text(
        "---\ntitle: Beta\n---\n# Beta\n\nNo links back.\n"
    )
    pages = wiki.build_page_index(tmp_path)
    assert len(pages) == 2
    alpha = next(p for p in pages.values() if p.title == "Alpha")
    assert alpha.tags == ["x"]
    assert alpha.outgoing == ["beta"]


def test_backlink_resolution(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("---\ntitle: A\n---\nLinks to [[B]].\n")
    (tmp_path / "notes" / "b.md").write_text("---\ntitle: B\n---\nNo refs.\n")
    (tmp_path / "notes" / "c.md").write_text("---\ntitle: C\n---\nAlso to [[B]] here.\n")
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    b = next(p for p in pages.values() if p.title == "B")
    assert sorted(b.backlinks) == [pages_slug(pages, "A"), pages_slug(pages, "C")]


def test_backlink_handles_alias(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "target.md").write_text(
        "---\ntitle: Scheduler\naliases: [work-windows, hours]\n---\n# Scheduler\n"
    )
    (tmp_path / "notes" / "src.md").write_text(
        "---\ntitle: Src\n---\nSee [[work-windows]] for when to run heavy jobs.\n"
    )
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    target = next(p for p in pages.values() if p.title == "Scheduler")
    src = next(p for p in pages.values() if p.title == "Src")
    # The src page should resolve work-windows to the scheduler slug.
    assert target.slug in src.outgoing
    assert src.slug in target.backlinks


def test_self_link_ignored(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "x.md").write_text("---\ntitle: X\n---\nI link to [[X]].\n")
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    x = next(iter(pages.values()))
    assert x.slug not in x.outgoing
    assert x.slug not in x.backlinks


def test_dangling_link_ignored(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "x.md").write_text("---\ntitle: X\n---\nLinks to [[nowhere]].\n")
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    x = next(iter(pages.values()))
    assert x.outgoing == []


# ── Graph builder ───────────────────────────────────────────────────────

def test_graph_chain(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("---\ntitle: A\n---\nLinks to [[B]].\n")
    (tmp_path / "notes" / "b.md").write_text("---\ntitle: B\n---\nLinks to [[C]].\n")
    (tmp_path / "notes" / "c.md").write_text("---\ntitle: C\n---\nNo refs.\n")
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    graph = wiki.build_link_graph(pages)
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2
    sources = {e["source"] for e in graph.edges}
    targets = {e["target"] for e in graph.edges}
    assert {"source", "target", "type", "label"} <= set(graph.edges[0].keys())
    assert all({"id", "label", "group"} <= set(n.keys()) for n in graph.nodes)


# ── End-to-end compile ──────────────────────────────────────────────────

def test_compile_wiki_writes_manifest(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("---\ntitle: A\n---\nLinks [[B]].\n")
    (tmp_path / "notes" / "b.md").write_text("---\ntitle: B\n---\nBody\n")
    result = wiki.compile_wiki(tmp_path)
    assert result.page_count == 2
    assert result.link_count == 1
    assert result.manifest_path.exists()
    import json
    m = json.loads(result.manifest_path.read_text())
    assert "pages" in m and "graph" in m
    assert len(m["pages"]) == 2


def test_compile_wiki_skips_wiki_cache(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "keep.md").write_text("---\ntitle: Keep\n---\nBody\n")
    # Run compile once to create .wiki-cache.
    wiki.compile_wiki(tmp_path)
    # Second run must still find exactly one page — not count files
    # from the cache we just wrote.
    result = wiki.compile_wiki(tmp_path)
    assert result.page_count == 1


def test_load_manifest_creates_if_missing(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "x.md").write_text("---\ntitle: X\n---\nbody\n")
    m = wiki.load_manifest(tmp_path)
    assert "pages" in m


# ── Markdown rendering ──────────────────────────────────────────────────

def test_render_page_resolves_wikilinks(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("---\ntitle: A\n---\n# A\n\nSee [[B]].\n")
    (tmp_path / "notes" / "b.md").write_text("---\ntitle: B\n---\n# B\n")
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    a = next(p for p in pages.values() if p.title == "A")
    html = wiki.render_page(a, pages)
    assert 'class="wikilink"' in html
    assert 'href="/wiki/' in html


def test_render_page_marks_missing_link(tmp_path: Path):
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "a.md").write_text("---\ntitle: A\n---\nGone [[nowhere]].\n")
    pages = wiki.build_page_index(tmp_path)
    wiki.resolve_links(pages)
    a = next(iter(pages.values()))
    html = wiki.render_page(a, pages)
    assert "missing" in html


# ── helpers ──────────────────────────────────────────────────────────────

def pages_slug(pages: dict, title: str) -> str:
    return next(p.slug for p in pages.values() if p.title == title)
