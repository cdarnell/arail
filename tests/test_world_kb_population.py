"""WK-1: mounting a World must actually populate the Knowledge Base.

Root problem this locks: mounting used to stage one index-table md + raw
bundle JSON, so the wiki got 1 page, the graph got 1 node, and machinery
files polluted search. Now each term becomes its own wiki page (frontmatter
+ [[related]] wikilinks → graph edges), and bundle machinery is excluded
from every KB surface.
"""

from __future__ import annotations

import pytest

from arail import pkb, wiki, world_mount as wm
from tests.world_bundle_builder import make_bundle

# A tiny 3-term graph: snake-plant —related→ pothos, succulents.
TERMS = [
    {"slug": "snake-plant", "term": "Snake Plant", "category": "plants",
     "short": "A hardy succulent houseplant.",
     "definition": "Dracaena trifasciata; upright leaves, tolerates neglect.",
     "example": "A snake plant thrives in low light.",
     "aka": ["Sansevieria", "Mother-in-law's tongue"],
     "related": ["pothos", "succulents"], "source": "https://en.wikipedia.org/wiki/Sansevieria"},
    {"slug": "pothos", "term": "Pothos", "category": "plants",
     "short": "A trailing vine.", "definition": "Epipremnum aureum, near-indestructible.",
     "example": "Pothos trails from a shelf.", "related": ["snake-plant"],
     "source": "https://en.wikipedia.org/wiki/Pothos"},
    {"slug": "succulents", "term": "Succulents", "category": "care",
     "short": "Water-storing plants.", "definition": "Plants with thick tissues that store water.",
     "example": "Succulents need little water.", "related": ["snake-plant"],
     "source": "https://en.wikipedia.org/wiki/Succulent_plant"},
]
CATS = [{"id": "plants", "label": "Plants"}, {"id": "care", "label": "Care"}]


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    data = tmp_path / "data"; pkb_root = tmp_path / "pkb"
    worlds = tmp_path / "worlds"
    data.mkdir(); pkb_root.mkdir(); worlds.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb_root)
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    return tmp_path, data, pkb_root


def _mount(bundle, data, pkb_root):
    return wm.mount(bundle, data_dir=data, pkb_root=pkb_root)


def _staged(pkb_root, slug):
    return pkb_root / "sources" / f"world-{slug}"


# ── per-term pages ─────────────────────────────────────────────────────


def test_one_page_per_term_with_parseable_frontmatter(lab):
    tmp, data, pkb_root = lab
    b = make_bundle(tmp / "b", slug="plants", terms_list=TERMS, categories=CATS)
    _mount(b, data, pkb_root)
    terms_dir = _staged(pkb_root, "plants") / "terms"
    pages = sorted(p.name for p in terms_dir.glob("*.md"))
    assert pages == ["pothos.md", "snake-plant.md", "succulents.md"]
    fm, _body = wiki.parse_frontmatter((terms_dir / "snake-plant.md").read_text())
    assert fm.get("title") == "Snake Plant"
    assert "world-plants" in (fm.get("tags") or [])
    # the term's own slug is an alias so bare [[snake-plant]] resolves
    assert "snake-plant" in (fm.get("aliases") or [])


def test_related_edges_become_graph_edges(lab):
    tmp, data, pkb_root = lab
    b = make_bundle(tmp / "b", slug="plants", terms_list=TERMS, categories=CATS)
    _mount(b, data, pkb_root)
    pages = wiki.build_page_index(pkb_root)
    wiki.resolve_links(pages)
    graph = wiki.build_link_graph(pages)
    # edges = [{"source": <full-slug>, "target": <full-slug>}] from page.outgoing
    edges = {(e["source"].rsplit("/", 1)[-1], e["target"].rsplit("/", 1)[-1])
             for e in graph.edges}
    assert ("snake-plant", "pothos") in edges, (
        f"[[pothos]] wikilink should be a graph edge; got {sorted(edges)}"
    )


def test_hostile_term_fields_are_contained(lab):
    tmp, data, pkb_root = lab
    evil = {"slug": "evil", "term": "Evil\n---\ntitle: pwned", "category": "plants",
            "short": "line1\n## Injected Heading\n- forged bullet",
            "definition": "`--- pwned ---`", "example": "", "related": [],
            "source": "https://x"}
    b = make_bundle(tmp / "b", slug="hostile",
                    terms_list=[evil], categories=[{"id": "plants", "label": "P"}])
    _mount(b, data, pkb_root)
    page = (_staged(pkb_root, "hostile") / "terms" / "evil.md").read_text()
    fm, body = wiki.parse_frontmatter(page)
    # Containment worked iff: the injected newline was collapsed (title is ONE
    # line — the `\n---\ntitle: pwned` never terminated the frontmatter block
    # nor created a second real key), and no forged heading/bullet survived at
    # column 0 in the body. "pwned" appearing INSIDE the single title value is
    # harmless text, not an injection.
    assert "\n" not in str(fm.get("title", "")), "newline injection broke the title scalar"
    assert str(fm.get("title", "")).startswith("Evil")
    for line in body.splitlines():
        assert not line.lstrip("‌").startswith("## Injected"), "forged heading leaked"
        assert not line.lstrip("‌").startswith("- forged"), "forged bullet leaked"


# ── machinery hygiene ──────────────────────────────────────────────────


def test_machinery_excluded_from_search_but_terms_included(lab):
    tmp, data, pkb_root = lab
    b = make_bundle(tmp / "b", slug="plants", terms_list=TERMS, categories=CATS)
    _mount(b, data, pkb_root)
    # search finds the term page…
    hits = pkb.search("Dracaena", pkb_root=pkb_root)
    paths = " ".join(h.get("path", "") for h in hits)
    assert "terms/snake-plant" in paths
    # …but the raw bundle machinery never appears in any search
    for junk in ("agenda.json", "drift-report.json", "roster.json", "spec.json"):
        j = pkb.search(junk.split(".")[0], pkb_root=pkb_root)
        assert not any(junk in h.get("path", "") for h in j), f"{junk} leaked into search"


def test_machinery_predicate_direct():
    assert wm.is_world_machinery_path("lab/pkb/sources/world-x/terms.json")
    assert wm.is_world_machinery_path("lab/pkb/sources/world-x/spec.json")
    # a term page is NOT machinery
    assert not wm.is_world_machinery_path("lab/pkb/sources/world-x/terms/snake-plant.md")
    # face/skill/index page are NOT machinery (they carry knowledge)
    assert not wm.is_world_machinery_path("lab/pkb/sources/world-x/face.json")
    assert not wm.is_world_machinery_path("lab/pkb/sources/world-x/world-x.md")
    # spec.json outside a world dir is a normal file
    assert not wm.is_world_machinery_path("lab/pkb/sources/notes/spec.json")


def test_browse_hides_machinery(lab):
    tmp, data, pkb_root = lab
    b = make_bundle(tmp / "b", slug="plants", terms_list=TERMS, categories=CATS)
    _mount(b, data, pkb_root)
    tree = pkb.browse(pkb_root=pkb_root)
    src_paths = [i["path"] for i in tree["sections"]["sources"]["items"]]
    assert any("terms/snake-plant.md" in p for p in src_paths)
    for junk in ("agenda.json", "drift-report.json", "roster.json", "spec.json", "terms.json"):
        assert not any(p.endswith(f"world-plants/{junk}") for p in src_paths), f"{junk} shown in browse"


# ── unmount clears pages ───────────────────────────────────────────────


def test_unmount_removes_pages(lab):
    tmp, data, pkb_root = lab
    b = make_bundle(tmp / "b", slug="plants", terms_list=TERMS, categories=CATS)
    _mount(b, data, pkb_root)
    assert _staged(pkb_root, "plants").exists()
    wm.unmount(data_dir=data, pkb_root=pkb_root, remove_staged=True)
    assert not _staged(pkb_root, "plants").exists()


# ── LanceDB-unavailable is surfaced, not silently swallowed ────────────


def test_index_status_unavailable_when_lancedb_missing(lab, monkeypatch):
    tmp, data, pkb_root = lab
    import arail.vector_index as vi
    monkeypatch.setattr(vi, "available", lambda: False)
    b = make_bundle(tmp / "b", slug="plants", terms_list=TERMS, categories=CATS)
    _mount(b, data, pkb_root)  # must not raise
    status = wm._index_staged(_staged(pkb_root, "plants"), pkb_root)
    assert status in ("unavailable", "indexed", "error") and status == "unavailable"
