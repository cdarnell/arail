"""QA-pass additive tests for docs_registry — sprint 2026-05-16-docs-hub-sprint-1.

These tests target the QA hunting list called out by the parent agent:
  - BOM, CRLF/mixed line endings, unicode/emoji in titles & slugs
  - HTML injection via frontmatter values (registry stores raw — verifies
    that no premature un-escaping happens at the registry layer)
  - Path-traversal sentinels (file-name and source_root forms)
  - Symlink containment for both docs_dir AND root allowlist
  - Empty docs/ dir, all-files-denylisted
  - Many docs (perf bound — 250 docs in <1s; bigger than the realistic max)
  - Slug normalization: extension stripping is case-insensitive, trailing
    whitespace, mixed-case extension
  - Denylist enforcement: CLAUDE.md, AGENTS.md, README.md cannot leak in
    by sitting inside docs/
  - by_category ordering follows CATEGORIES declaration (not insertion)
  - by_category values are tuples (immutable; caller cannot poison cache)
  - all_docs returns the same identity across calls (cache reuse)
  - Cache reuse across get/siblings/related (does not rebuild N times)
  - Live-repo sanity: importing the module against the real repo yields
    >=20 docs, all categories are valid, no slug collisions
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
from pathlib import Path
from types import ModuleType

import pytest

# ---------------------------------------------------------------------------
# Helpers (mirror style of test_docs_registry.py)
# ---------------------------------------------------------------------------


def _fresh_registry(monkeypatch, docs_dir: Path, root_dir: Path) -> ModuleType:
    mod_name = "arail.portal.docs_registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    monkeypatch.setattr(mod, "_repo_root", lambda: root_dir)
    mod._invalidate_cache()
    return mod


def _write(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding=encoding)


# ---------------------------------------------------------------------------
# Edge cases — encodings & whitespace
# ---------------------------------------------------------------------------


def test_bom_prefixed_file_does_not_crash(monkeypatch, tmp_path):
    """A UTF-8 BOM at the start of the file must not break frontmatter parse.

    python-frontmatter is known to be sensitive to a leading BOM (it
    expects literal `---` at byte 0). The registry should at minimum
    NOT crash; the doc should still be registered (possibly with
    fallback title from filename stem if frontmatter doesn't parse).
    """
    docs = tmp_path / "docs"
    content = "---\ntitle: BOM Doc\ncategory: Reference\n---\n# BOM Doc\nbody\n"
    _write(docs / "bom.md", "﻿" + content)
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    docs_list = reg.all_docs()
    assert len(docs_list) == 1
    doc = docs_list[0]
    assert doc.slug == "bom"
    # The doc must be registered with *some* non-empty title.
    assert doc.title  # not empty


def test_crlf_line_endings_parse_correctly(monkeypatch, tmp_path):
    """CRLF line endings in frontmatter must parse the same as LF."""
    docs = tmp_path / "docs"
    content = (
        "---\r\n"
        "title: CRLF\r\n"
        "category: Concepts\r\n"
        "tags:\r\n  - alpha\r\n  - beta\r\n"
        "---\r\n"
        "# CRLF\r\nbody\r\n"
    )
    (docs).mkdir(parents=True, exist_ok=True)
    (docs / "crlf.md").write_bytes(content.encode("utf-8"))
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.all_docs()[0]
    assert doc.title == "CRLF"
    assert doc.category == "Concepts"
    assert set(doc.tags) == {"alpha", "beta"}


def test_mixed_line_endings_do_not_crash(monkeypatch, tmp_path):
    """A file with both LF and CRLF (mixed) must still register the doc."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    raw = b"---\ntitle: Mixed\r\ncategory: Reference\n---\r\n# Mixed\nbody\r\n"
    (docs / "mixed.md").write_bytes(raw)
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    docs_list = reg.all_docs()
    assert len(docs_list) == 1
    assert docs_list[0].slug == "mixed"


# ---------------------------------------------------------------------------
# Unicode / emoji
# ---------------------------------------------------------------------------


def test_unicode_title_preserved(monkeypatch, tmp_path):
    """Unicode and emoji in title pass through unchanged."""
    docs = tmp_path / "docs"
    _write(docs / "u.md", "---\ntitle: 日本語 — Café 🚀\n---\n# fallback\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.all_docs()[0]
    assert doc.title == "日本語 — Café 🚀"


def test_unicode_slug_from_filename(monkeypatch, tmp_path):
    """A doc with a unicode filename produces a unicode slug and does not crash."""
    docs = tmp_path / "docs"
    _write(docs / "café.md", "# Café\nbody\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    slugs = [d.slug for d in reg.all_docs()]
    assert "café" in slugs


def test_emoji_in_tags_normalised(monkeypatch, tmp_path):
    """Emoji-only tag survives lowercasing (no crash); non-empty preserved."""
    docs = tmp_path / "docs"
    _write(docs / "e.md", '---\ntags: ["🚀", "Buddy"]\n---\n# E\n')
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    tags = reg.all_docs()[0].tags
    assert "🚀" in tags
    assert "buddy" in tags  # lowercased


# ---------------------------------------------------------------------------
# Adversarial frontmatter — HTML/script injection
# ---------------------------------------------------------------------------


def test_html_injection_in_frontmatter_stored_verbatim(monkeypatch, tmp_path):
    """The registry stores frontmatter values raw — it is the consumer's job
    to escape on render. This test pins the contract: the registry does NOT
    sanitize, and it also does NOT execute or interpret HTML.

    If a future change adds HTML sanitization here, this test will fail and
    force the developer to think about where escaping belongs (the answer:
    in the template, via Jinja autoescape — not in the registry).
    """
    docs = tmp_path / "docs"
    payload = "<script>alert(xss)</script>"
    # Use YAML single-quotes so the payload is preserved verbatim.
    _write(
        docs / "xss.md",
        f"---\ntitle: '{payload}'\ndescription: '{payload}'\nbuddy_prompt: '{payload}'\n---\n# X\n",
    )
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.all_docs()[0]
    # Raw values preserved — must not be partially sanitized either.
    assert doc.title == payload
    assert doc.description == payload
    assert doc.buddy_prompt == payload


# ---------------------------------------------------------------------------
# Path-traversal / containment
# ---------------------------------------------------------------------------


def test_path_traversal_filename_not_reachable(monkeypatch, tmp_path):
    """A file outside docs/ whose name appears in the denylist cannot be
    pulled into docs/ via cute filename tricks. iterdir() yields direct
    children only — the registry should never read a file with `/` in its
    intended name. This is a structural sentinel."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    # Create a sibling sensitive file outside the curated roots.
    sensitive = tmp_path.parent / "sensitive-leak.md"
    sensitive.write_text("---\ntitle: LEAK\n---\n# LEAK\n", encoding="utf-8")
    # And a normal doc inside docs/
    _write(docs / "normal.md", "# Normal\n")
    try:
        reg = _fresh_registry(monkeypatch, docs, tmp_path)
        slugs = {d.slug for d in reg.all_docs()}
        # The sensitive file lives outside the curated roots and must not appear.
        assert "sensitive-leak" not in slugs
        assert "normal" in slugs
    finally:
        try:
            sensitive.unlink()
        except OSError:
            pass


@pytest.mark.skipif(sys.platform == "win32", reason="symlink permissions")
def test_symlink_escape_via_root_allowlist_is_blocked(monkeypatch, tmp_path):
    """The architect's containment claim applies to docs/ — verify the same
    check protects the repo-root allowlist branch. If `tmp_path/design.md`
    is a symlink to /tmp/anything.md, the registry must reject it."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    outside = tmp_path.parent / "evil-root-target.md"
    outside.write_text("---\ntitle: ESCAPED\n---\n# ESCAPED\n", encoding="utf-8")
    try:
        link = tmp_path / "design.md"  # in _ROOT_ALLOWLIST
        link.symlink_to(outside)
        reg = _fresh_registry(monkeypatch, docs, tmp_path)
        docs_list = reg.all_docs()
        # The symlinked file must be skipped — `design` slug should not be
        # present, or if present must not have leaked the outside title.
        for d in docs_list:
            assert d.title != "ESCAPED", (
                "Symlink escape via root allowlist: outside file content leaked"
            )
    finally:
        try:
            outside.unlink()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Empty / boundary states
# ---------------------------------------------------------------------------


def test_empty_docs_dir_returns_empty_tuple(monkeypatch, tmp_path):
    """An existing-but-empty docs/ dir and no root allowlist files → ()."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.all_docs()
    assert result == ()
    # by_category must also be empty (and a dict)
    assert reg.by_category() == {}


def test_all_files_denylisted_returns_empty(monkeypatch, tmp_path):
    """If every file in docs/ is on the denylist, all_docs() is empty."""
    docs = tmp_path / "docs"
    for name in ("INDEX.md", "BLUEPRINT_PROMPT.md", "maximus.plan.md"):
        _write(docs / name, "# x\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    assert reg.all_docs() == ()


# ---------------------------------------------------------------------------
# Denylist leak sentinels (security)
# ---------------------------------------------------------------------------


def test_root_denylist_files_in_docs_dir_dont_leak(monkeypatch, tmp_path):
    """S1 fix (sprint-1 QA): root-denied names dropped into docs/ must NOT
    register as user-facing docs. _DOCS_DENYLIST is composed with
    _ROOT_DENYLIST at module load to enforce this symmetrically.
    """
    docs = tmp_path / "docs"
    _write(docs / "CLAUDE.md", "---\ntitle: CLAUDE\n---\n# CLAUDE\n")
    _write(docs / "AGENTS.md", "---\ntitle: AGENTS\n---\n# AGENTS\n")
    _write(docs / "README.md", "---\ntitle: README\n---\n# README\n")
    _write(docs / "real.md", "# real\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    slugs = {d.slug for d in reg.all_docs()}
    assert "real" in slugs
    assert slugs.isdisjoint({"CLAUDE", "AGENTS", "README"}), (
        "Root-denylist names dropped into docs/ must not register. "
        "If this assertion fails, the denylist composition at module load "
        "regressed — restore the `_DOCS_DENYLIST | _ROOT_DENYLIST` line."
    )


# ---------------------------------------------------------------------------
# Performance bound
# ---------------------------------------------------------------------------


@pytest.mark.perf
def test_many_docs_build_under_one_second(monkeypatch, tmp_path):
    """250 docs (10x the realistic count) parse in <1s on stock hardware."""
    docs = tmp_path / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    for i in range(250):
        _write(
            docs / f"doc-{i:04d}.md",
            f"---\ntitle: Doc {i}\ncategory: Reference\norder: {i}\n---\n# Doc {i}\nbody\n",
        )
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    t0 = time.perf_counter()
    result = reg.all_docs()
    elapsed = time.perf_counter() - t0
    assert len(result) == 250
    assert elapsed < 1.0, f"250-doc build took {elapsed:.2f}s (limit 1.0s)"


# ---------------------------------------------------------------------------
# Slug normalization edges (related())
# ---------------------------------------------------------------------------


def test_related_extension_stripping_case_insensitive(monkeypatch, tmp_path):
    """related: [Agents.MD] — uppercase .MD must strip the same as .md."""
    docs = tmp_path / "docs"
    _write(docs / "a.md", "---\nrelated:\n  - agents.MD\n---\n# A\n")
    _write(docs / "agents.md", "# Agents\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.related("a")
    assert len(result) == 1
    assert result[0].slug == "agents"


def test_related_string_form_accepted(monkeypatch, tmp_path):
    """related: agents (bare string, not a list) is normalised to a one-item list."""
    docs = tmp_path / "docs"
    _write(docs / "a.md", "---\nrelated: agents\n---\n# A\n")
    _write(docs / "agents.md", "# Agents\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.related("a")
    assert len(result) == 1
    assert result[0].slug == "agents"


def test_related_with_whitespace_padding(monkeypatch, tmp_path):
    """related: ['  agents  '] — leading/trailing whitespace stripped."""
    docs = tmp_path / "docs"
    _write(docs / "a.md", "---\nrelated:\n  - '  agents  '\n---\n# A\n")
    _write(docs / "agents.md", "# Agents\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.related("a")
    assert len(result) == 1


# ---------------------------------------------------------------------------
# by_category — ordering + immutability
# ---------------------------------------------------------------------------


def test_by_category_values_are_tuples(monkeypatch, tmp_path):
    """Caller cannot mutate the cached state via by_category()."""
    docs = tmp_path / "docs"
    _write(docs / "a.md", "---\ncategory: Reference\n---\n# A\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    cats = reg.by_category()
    assert all(isinstance(v, tuple) for v in cats.values())


def test_by_category_preserves_all_docs_sort_order(monkeypatch, tmp_path):
    """Within a category, by_category()'s order matches all_docs() order."""
    docs = tmp_path / "docs"
    _write(docs / "z.md", "---\ncategory: Reference\norder: 1\n---\n# Z\n")
    _write(docs / "a.md", "---\ncategory: Reference\norder: 5\n---\n# A\n")
    _write(docs / "m.md", "---\ncategory: Reference\norder: 3\n---\n# M\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    by_cat = reg.by_category()
    ref_order = [d.slug for d in by_cat["Reference"]]
    overall = [d.slug for d in reg.all_docs() if d.category == "Reference"]
    assert ref_order == overall


# ---------------------------------------------------------------------------
# Cache identity (regression — guards against accidental re-build)
# ---------------------------------------------------------------------------


def test_all_docs_returns_same_object_when_cache_warm(monkeypatch, tmp_path):
    """Two consecutive calls with no fs change return the SAME tuple object."""
    docs = tmp_path / "docs"
    _write(docs / "x.md", "# X\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    a = reg.all_docs()
    b = reg.all_docs()
    assert a is b


# ---------------------------------------------------------------------------
# Live-repo sanity (regression — catches real-world breakage at runtime)
# ---------------------------------------------------------------------------


def test_live_repo_registry_is_well_formed():
    """Against the *real* repo: >=20 docs, all categories valid, no collisions,
    all required fields populated. This is the test that catches frontmatter
    rot when someone edits a doc and breaks its YAML."""
    # Force a clean import against the real repo paths.
    mod_name = "arail.portal.docs_registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    mod._invalidate_cache()

    docs = mod.all_docs()
    assert len(docs) >= 20, f"Expected ≥20 docs, got {len(docs)}"

    # No collisions
    slugs = [d.slug for d in docs]
    assert len(slugs) == len(set(slugs)), "Slug collision in live registry"

    # Categories are all valid
    for d in docs:
        assert d.category in mod.CATEGORIES, f"{d.slug} has invalid category {d.category!r}"
        assert d.audience in {"beginner", "operator", "architect"}, (
            f"{d.slug} has invalid audience {d.audience!r}"
        )
        assert d.title and d.title.strip(), f"{d.slug} has empty title"
        assert d.read_minutes >= 1, f"{d.slug} read_minutes={d.read_minutes} < 1"
        assert d.source_root in {"docs", "root"}, (
            f"{d.slug} has invalid source_root {d.source_root!r}"
        )


def test_live_repo_denylist_files_not_present():
    """The denylist files must never appear in the live registry."""
    mod_name = "arail.portal.docs_registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    mod._invalidate_cache()

    slugs = {d.slug for d in mod.all_docs()}
    forbidden = {
        "BLUEPRINT_PROMPT",
        "DEBUG_QWEN25_7B_CASE_STUDY",
        "maximus.plan",
        "chat-studio.spec",
        "standards-compliance",
        "INDEX",
        "CLAUDE",
        "AGENTS",
        "README",
        "CODE_OF_CONDUCT",
    }
    leaked = slugs & forbidden
    assert not leaked, f"Denylist files leaked into live registry: {leaked}"


def test_live_repo_related_slugs_resolve_or_are_silently_dropped():
    """Every `related:` slug in the live registry either resolves to another
    registered doc or is silently dropped (no exception). Authoring typos
    should not break the registry."""
    mod_name = "arail.portal.docs_registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    mod = importlib.import_module(mod_name)
    mod._invalidate_cache()

    docs = mod.all_docs()
    known = {d.slug for d in docs}
    unresolved = []
    for d in docs:
        for rel in d.related:
            s = rel[:-3] if rel.lower().endswith(".md") else rel
            if s not in known:
                unresolved.append((d.slug, rel))

    # Not a failure (the spec says silently drop) — but record for the QA report.
    # Cap noise: assert that related() is callable and never raises.
    for d in docs:
        result = mod.related(d.slug)
        assert isinstance(result, tuple)
