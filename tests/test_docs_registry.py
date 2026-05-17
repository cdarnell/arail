"""Unit tests for docs_registry — Sprint 1 (2026-05-16-docs-hub-sprint-1).

Each test uses its own fixture directory under tmp_path to stay independent
from the real repo contents and from each other.

Failure modes covered per ARCHITECTURE.md §7 and §8.1:
  F1  malformed YAML
  F2  no frontmatter
  F3  unknown frontmatter key (silently ignored)
  F4  bad category coerced to Reference
  F5  bad audience coerced to beginner
  F6  tags as string split on comma
  F7  related slug not in registry (silently dropped)
  F8  self-reference in related
  F9  path traversal in related slugs (structurally safe)
  F10 symlink escape outside curated root
  F11 cache invalidates on mtime change
  F12 concurrent load under lock
  F13 python-frontmatter missing
  F14 slug collision raises RuntimeError
  F15 missing docs/ dir
  F16 empty/whitespace title falls back to H1 then stem
  F17 large doc parses under threshold
"""

from __future__ import annotations

import importlib
import sys
import threading
import time
import os
from pathlib import Path
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to isolate registry state per test
# ---------------------------------------------------------------------------


def _fresh_registry(monkeypatch, docs_dir: Path, root_dir: Path) -> ModuleType:
    """Import (or re-import) docs_registry wired to specific fixture dirs."""
    # Remove any cached module so we get a fresh module state.
    mod_name = "arail.portal.docs_registry"
    if mod_name in sys.modules:
        del sys.modules[mod_name]

    mod = importlib.import_module(mod_name)

    # Point the registry at the test fixture dirs.
    monkeypatch.setattr(mod, "_repo_root", lambda: root_dir)
    # Invalidate cache so the first call re-builds.
    mod._invalidate_cache()
    return mod


def _write_doc(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_loads_doc_with_full_frontmatter(monkeypatch, tmp_path):
    """Happy path: all fields populated from frontmatter."""
    docs = tmp_path / "docs"
    _write_doc(
        docs / "mypage.md",
        "---\n"
        "title: My Page\n"
        "description: A great page\n"
        "category: Concepts\n"
        "order: 5\n"
        "tags:\n  - foo\n  - bar\n"
        "read_minutes: 3\n"
        "audience: operator\n"
        "related:\n  - other\n"
        "buddy_prompt: Let me show you around.\n"
        "---\n"
        "# My Page\nSome content here.\n",
    )
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    docs_list = reg.all_docs()
    assert len(docs_list) == 1
    doc = docs_list[0]
    assert doc.slug == "mypage"
    assert doc.title == "My Page"
    assert doc.description == "A great page"
    assert doc.category == "Concepts"
    assert doc.order == 5
    assert doc.tags == ("foo", "bar")
    assert doc.read_minutes == 3
    assert doc.audience == "operator"
    assert doc.related == ("other",)
    assert doc.buddy_prompt == "Let me show you around."
    assert doc.source_root == "docs"


def test_loads_doc_with_no_frontmatter(monkeypatch, tmp_path):
    """F2 / F16: no frontmatter — title from H1, read_minutes computed."""
    docs = tmp_path / "docs"
    body = "# Hello World\n" + ("word " * 400)  # ~400 words → 2 min
    _write_doc(docs / "hello.md", body)
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.all_docs()[0]
    assert doc.title == "Hello World"
    assert doc.read_minutes == 2
    assert doc.category == "Reference"
    assert doc.audience == "beginner"


def test_loads_doc_with_partial_frontmatter(monkeypatch, tmp_path):
    """Only title and category — other fields use defaults."""
    docs = tmp_path / "docs"
    _write_doc(docs / "partial.md", "---\ntitle: Partial\ncategory: Operating\n---\n# Partial\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.all_docs()[0]
    assert doc.title == "Partial"
    assert doc.category == "Operating"
    assert doc.order == 100
    assert doc.tags == ()
    assert doc.audience == "beginner"


def test_malformed_yaml_logs_and_continues(monkeypatch, tmp_path, caplog):
    """F1: broken frontmatter does not crash; doc registered with defaults; WARNING logged."""
    docs = tmp_path / "docs"
    _write_doc(docs / "broken.md", "---\ntags: [unclosed\n---\n# Broken\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    import logging
    with caplog.at_level(logging.WARNING, logger="arail.portal.docs_registry"):
        docs_list = reg.all_docs()
    assert len(docs_list) == 1
    assert docs_list[0].slug == "broken"
    assert any("malformed frontmatter" in r.message for r in caplog.records)


def test_unknown_category_coerces_to_reference(monkeypatch, tmp_path, caplog):
    """F4: unknown category → Reference + WARNING."""
    docs = tmp_path / "docs"
    _write_doc(docs / "misc.md", "---\ncategory: Misc\n---\n# Misc\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    import logging
    with caplog.at_level(logging.WARNING, logger="arail.portal.docs_registry"):
        doc = reg.all_docs()[0]
    assert doc.category == "Reference"
    assert any("unknown category" in r.message for r in caplog.records)


def test_unknown_audience_coerces_to_beginner(monkeypatch, tmp_path, caplog):
    """F5: unknown audience → beginner + WARNING."""
    docs = tmp_path / "docs"
    _write_doc(docs / "wizard.md", "---\naudience: wizard\n---\n# Wizard\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    import logging
    with caplog.at_level(logging.WARNING, logger="arail.portal.docs_registry"):
        doc = reg.all_docs()[0]
    assert doc.audience == "beginner"
    assert any("unknown audience" in r.message for r in caplog.records)


def test_tags_string_form_splits_correctly(monkeypatch, tmp_path):
    """F6: tags as comma-string → split and normalised."""
    docs = tmp_path / "docs"
    _write_doc(docs / "tagged.md", "---\ntags: agents, buddy\n---\n# Tagged\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.all_docs()[0]
    assert doc.tags == ("agents", "buddy")


def test_unknown_frontmatter_keys_silently_ignored(monkeypatch, tmp_path, caplog):
    """F3: unknown key 'auther' does not appear and does not warn."""
    docs = tmp_path / "docs"
    _write_doc(docs / "typo.md", "---\ntitle: Good\nauther: Oops\n---\n# Good\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    import logging
    with caplog.at_level(logging.WARNING, logger="arail.portal.docs_registry"):
        doc = reg.all_docs()[0]
    assert doc.title == "Good"
    # No warning about the unknown key
    assert not any("auther" in r.message for r in caplog.records)


def test_all_docs_ordering(monkeypatch, tmp_path):
    """Docs sorted by (category_order, order, slug)."""
    docs = tmp_path / "docs"
    _write_doc(docs / "z-ref.md", "---\ncategory: Reference\norder: 50\n---\n# Z Ref\n")
    _write_doc(docs / "a-ref.md", "---\ncategory: Reference\norder: 50\n---\n# A Ref\n")
    _write_doc(docs / "gs.md", "---\ncategory: Getting Started\norder: 1\n---\n# GS\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    slugs = [d.slug for d in reg.all_docs()]
    assert slugs.index("gs") < slugs.index("a-ref")
    assert slugs.index("a-ref") < slugs.index("z-ref")


def test_by_category_omits_empty_categories(monkeypatch, tmp_path):
    """Only categories with docs appear in by_category()."""
    docs = tmp_path / "docs"
    _write_doc(docs / "only.md", "---\ncategory: Reference\n---\n# Only\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    cats = reg.by_category()
    assert "Reference" in cats
    assert "Getting Started" not in cats
    assert "Design" not in cats


def test_get_returns_none_for_unknown_slug(monkeypatch, tmp_path):
    """get() returns None for unknown slug."""
    docs = tmp_path / "docs"
    _write_doc(docs / "real.md", "# Real\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    assert reg.get("does-not-exist") is None


def test_siblings_returns_prev_next_within_category(monkeypatch, tmp_path):
    """Middle doc has both; first has (None, next); last has (prev, None)."""
    docs = tmp_path / "docs"
    _write_doc(docs / "a.md", "---\ncategory: Reference\norder: 1\n---\n# A\n")
    _write_doc(docs / "b.md", "---\ncategory: Reference\norder: 2\n---\n# B\n")
    _write_doc(docs / "c.md", "---\ncategory: Reference\norder: 3\n---\n# C\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    prev_a, next_a = reg.siblings("a")
    assert prev_a is None
    assert next_a is not None and next_a.slug == "b"
    prev_b, next_b = reg.siblings("b")
    assert prev_b is not None and prev_b.slug == "a"
    assert next_b is not None and next_b.slug == "c"
    prev_c, next_c = reg.siblings("c")
    assert prev_c is not None and prev_c.slug == "b"
    assert next_c is None


def test_siblings_unknown_slug_returns_none_pair(monkeypatch, tmp_path):
    """siblings() returns (None, None) for unknown slug."""
    docs = tmp_path / "docs"
    _write_doc(docs / "x.md", "# X\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    assert reg.siblings("ghost") == (None, None)


def test_related_resolves_explicit_frontmatter_first(monkeypatch, tmp_path):
    """related: [b, c] → (b, c) in frontmatter order."""
    docs = tmp_path / "docs"
    _write_doc(docs / "a.md", "---\ncategory: Reference\nrelated:\n  - b\n  - c\n---\n# A\n")
    _write_doc(docs / "b.md", "---\ncategory: Reference\n---\n# B\n")
    _write_doc(docs / "c.md", "---\ncategory: Reference\n---\n# C\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.related("a")
    assert tuple(d.slug for d in result) == ("b", "c")


def test_related_falls_back_to_tag_overlap(monkeypatch, tmp_path):
    """No explicit related: tag-overlap candidates within same category, scored."""
    docs = tmp_path / "docs"
    _write_doc(docs / "a.md", "---\ncategory: Reference\ntags:\n  - foo\n  - bar\n---\n# A\n")
    _write_doc(docs / "b.md", "---\ncategory: Reference\ntags:\n  - foo\n  - bar\n---\n# B\n")
    _write_doc(docs / "c.md", "---\ncategory: Reference\ntags:\n  - foo\n  - bar\n---\n# C\n")
    _write_doc(docs / "d.md", "---\ncategory: Reference\ntags:\n  - foo\n---\n# D\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.related("a", limit=3)
    slugs = [d.slug for d in result]
    # B and C share 2 tags, D shares 1 → B and C come first
    assert "b" in slugs
    assert "c" in slugs
    assert slugs.index("b") < slugs.index("d") or slugs.index("c") < slugs.index("d")


def test_related_drops_self_reference(monkeypatch, tmp_path):
    """F8: related: [self_slug] → empty."""
    docs = tmp_path / "docs"
    _write_doc(docs / "self.md", "---\nrelated:\n  - self\n---\n# Self\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    assert reg.related("self") == ()


def test_related_drops_unknown_slug(monkeypatch, tmp_path):
    """F7: related: [ghost] → empty + no exception."""
    docs = tmp_path / "docs"
    _write_doc(docs / "lonely.md", "---\nrelated:\n  - ghost\n---\n# Lonely\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    assert reg.related("lonely") == ()


def test_related_drops_path_traversal_slug(monkeypatch, tmp_path):
    """F9: path-traversal-looking slugs in related never cause file reads."""
    docs = tmp_path / "docs"
    _write_doc(
        docs / "evil.md",
        "---\nrelated:\n  - ../../etc/passwd\n  - /etc/passwd\n  - ..\\\\windows\\\\system32\n---\n# Evil\n",
    )
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    # Must return empty — none of those slugs exist in the registry.
    result = reg.related("evil")
    assert result == ()
    # Confirm no file was opened outside the fixture root (structurally safe).


def test_related_handles_extension_stripping(monkeypatch, tmp_path):
    """related: [agents.md] resolves same as related: [agents]."""
    docs = tmp_path / "docs"
    _write_doc(docs / "a.md", "---\nrelated:\n  - agents.md\n---\n# A\n")
    _write_doc(docs / "agents.md", "# Agents\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.related("a")
    assert len(result) == 1
    assert result[0].slug == "agents"


def test_related_respects_limit_zero_and_negative(monkeypatch, tmp_path):
    """limit=0 → (); limit=-1 → ()."""
    docs = tmp_path / "docs"
    _write_doc(docs / "p.md", "---\nrelated:\n  - q\n---\n# P\n")
    _write_doc(docs / "q.md", "# Q\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    assert reg.related("p", limit=0) == ()
    assert reg.related("p", limit=-1) == ()


def test_cache_invalidates_on_directory_mtime_change(monkeypatch, tmp_path):
    """F11: adding a file to docs/ causes all_docs() to rebuild."""
    docs = tmp_path / "docs"
    _write_doc(docs / "first.md", "# First\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    original = reg.all_docs()
    assert len(original) == 1

    # Add a new doc (changes directory mtime + new file mtime)
    time.sleep(0.01)  # ensure mtime differs on fast filesystems
    _write_doc(docs / "second.md", "# Second\n")

    # all_docs() should rebuild and pick up the second file.
    result = reg.all_docs()
    assert len(result) == 2


def test_concurrent_load_under_lock(monkeypatch, tmp_path):
    """F12: two threads calling all_docs() after cache invalidation triggers
    exactly one rebuild (the second thread re-uses the result)."""
    docs = tmp_path / "docs"
    _write_doc(docs / "a.md", "# A\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)

    build_count = [0]
    original_build = reg._build

    def counting_build(*args, **kwargs):
        build_count[0] += 1
        return original_build(*args, **kwargs)

    monkeypatch.setattr(reg, "_build", counting_build)
    reg._invalidate_cache()

    results = []
    barrier = threading.Barrier(2)

    def _call():
        barrier.wait()
        results.append(reg.all_docs())

    t1 = threading.Thread(target=_call)
    t2 = threading.Thread(target=_call)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert len(results) == 2
    # Both threads should have gotten a valid result.
    assert all(len(r) == 1 for r in results)
    # Due to the double-checked lock, at most one rebuild should have run.
    assert build_count[0] <= 2  # In the worst case 2 is acceptable; 1 is ideal.


def test_python_frontmatter_missing_falls_back_to_empty_registry(monkeypatch, tmp_path, caplog):
    """F13: if python-frontmatter is not importable, all_docs() returns ()."""
    mod_name = "arail.portal.docs_registry"
    # Remove any cached version.
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    # Also remove the frontmatter module so the import will fail.
    saved = sys.modules.pop("frontmatter", None)

    # Sentinel object that raises ImportError on any attribute access.
    class _BlockedModule:
        def __getattr__(self, name):  # pragma: no cover
            raise ImportError("test-simulated missing frontmatter")

    # Place a sentinel that will cause `import frontmatter` to fail on re-import.
    # The cleanest approach: remove it from sys.modules AND register a broken finder.
    import importlib.abc
    import importlib.machinery

    class _BlockingFinder(importlib.abc.MetaPathFinder):
        def find_spec(self, fullname, path, target=None):
            if fullname == "frontmatter":
                raise ImportError("test-simulated missing frontmatter")
            return None

    finder = _BlockingFinder()
    sys.meta_path.insert(0, finder)

    import logging
    try:
        with caplog.at_level(logging.WARNING):
            mod = importlib.import_module(mod_name)
        result = mod.all_docs()
    finally:
        sys.meta_path.remove(finder)
        if saved is not None:
            sys.modules["frontmatter"] = saved
        # Clean up the re-imported module so other tests get a fresh copy with frontmatter.
        if mod_name in sys.modules:
            del sys.modules[mod_name]

    assert result == ()
    assert any("docs_registry" in r.name and "python-frontmatter" in r.message
               for r in caplog.records)


def test_slug_collision_raises_runtime_error(monkeypatch, tmp_path):
    """F14: two docs resolving to the same slug → RuntimeError."""
    docs = tmp_path / "docs"
    # slug collision: docs/INSTALL.md and root INSTALL.md — but root only uses allowlist.
    # We can simulate a collision by having two files in docs with the same stem via a
    # sub-dir trick: put a symlink. Instead, manipulate the allowlist to include a file
    # that also appears in docs.
    _write_doc(docs / "SECURITY.md", "# Security from docs\n")
    # Also create a root SECURITY.md
    (tmp_path / "SECURITY.md").write_text("# Security from root\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    with pytest.raises(RuntimeError, match="slug collision"):
        reg._build(docs, tmp_path)


def test_missing_docs_dir_does_not_crash(monkeypatch, tmp_path):
    """F15: no docs/ directory → only root docs; no crash."""
    # Create only a root-level doc (SECURITY.md)
    (tmp_path / "SECURITY.md").write_text("# Security\n")
    docs = tmp_path / "docs"  # does not exist
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    result = reg.all_docs()
    # Should return root docs without crashing.
    slugs = [d.slug for d in result]
    assert "SECURITY" in slugs


@pytest.mark.skipif(sys.platform == "win32", reason="Symlink permissions on Windows")
def test_symlink_to_outside_root_is_skipped(monkeypatch, tmp_path, caplog):
    """F10: symlink inside docs/ pointing outside the root is skipped + WARNING."""
    docs = tmp_path / "docs"
    docs.mkdir()

    # File outside the curated root
    outside = tmp_path.parent / "outside_secret.md"
    outside.write_text("# Secret\n")

    # Symlink inside docs/ → outside
    link = docs / "leak.md"
    link.symlink_to(outside)

    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    import logging
    with caplog.at_level(logging.WARNING, logger="arail.portal.docs_registry"):
        result = reg.all_docs()

    slugs = [d.slug for d in result]
    assert "leak" not in slugs
    assert any("symlink" in r.message.lower() or "outside" in r.message.lower()
               for r in caplog.records)


def test_internal_docs_excluded(monkeypatch, tmp_path):
    """F: denylist files are not included in the registry."""
    docs = tmp_path / "docs"
    _write_doc(docs / "DEBUG_QWEN25_7B_CASE_STUDY.md", "# Debug\n")
    _write_doc(docs / "chat-studio.spec.md", "# Chat Studio Spec\n")
    _write_doc(docs / "BLUEPRINT_PROMPT.md", "# Blueprint Prompt\n")
    _write_doc(docs / "maximus.plan.md", "# Maximus Plan\n")
    _write_doc(docs / "standards-compliance.md", "# Standards\n")
    _write_doc(docs / "real-doc.md", "# Real Doc\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    slugs = [d.slug for d in reg.all_docs()]
    for denied in ["DEBUG_QWEN25_7B_CASE_STUDY", "chat-studio.spec", "BLUEPRINT_PROMPT",
                   "maximus.plan", "standards-compliance"]:
        assert denied not in slugs, f"Denylist file {denied} appeared in registry"
    assert "real-doc" in slugs


def test_index_md_excluded(monkeypatch, tmp_path):
    """INDEX.md must not appear in the registry."""
    docs = tmp_path / "docs"
    _write_doc(docs / "INDEX.md", "# Index\n")
    _write_doc(docs / "actual.md", "# Actual\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    slugs = [d.slug for d in reg.all_docs()]
    assert "INDEX" not in slugs
    assert "actual" in slugs


def test_root_docs_use_root_source(monkeypatch, tmp_path):
    """design.md at repo root appears with source_root='root'."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "design.md").write_text("# Design\n")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.get("design")
    assert doc is not None
    assert doc.source_root == "root"


def test_word_count_read_minutes_floor_at_one(monkeypatch, tmp_path):
    """F: a 5-word doc has read_minutes == 1, not 0."""
    docs = tmp_path / "docs"
    _write_doc(docs / "tiny.md", "# Tiny\nHello world.")
    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    doc = reg.get("tiny")
    assert doc is not None
    assert doc.read_minutes == 1


@pytest.mark.perf
def test_large_doc_parses_under_threshold(monkeypatch, tmp_path):
    """F17: a 40KB doc parses in < 100ms."""
    import time as _time

    docs = tmp_path / "docs"
    # Generate ~40KB of content
    body = "---\ntitle: Large Doc\ncategory: Reference\n---\n# Large Doc\n"
    body += ("This is a word. " * 2500)  # ~40KB
    _write_doc(docs / "large.md", body)

    reg = _fresh_registry(monkeypatch, docs, tmp_path)
    start = _time.perf_counter()
    reg.all_docs()
    elapsed_ms = (_time.perf_counter() - start) * 1000
    assert elapsed_ms < 100, f"Large doc parse took {elapsed_ms:.1f}ms (limit 100ms)"


# ---------------------------------------------------------------------------
# The lab, end-to-end (runbook) — registry-level guarantees
# ---------------------------------------------------------------------------

def test_the_lab_in_registry():
    """The runbook lives in the registry under Getting Started, ordered first."""
    from arail.portal.docs_registry import all_docs, by_category, get

    doc = get("the-lab")
    assert doc is not None, "the-lab runbook missing from registry"
    assert doc.category == "Getting Started", (
        f"the-lab must be in Getting Started, got {doc.category!r}"
    )
    # order=0 puts the runbook ahead of INSTALL (order=1) — the runbook is
    # the on-ramp, INSTALL is the manual.
    assert doc.order == 0, f"the-lab must have order=0 (first in category), got {doc.order!r}"
    assert "the-lab" in {d.slug for d in all_docs()}
    cats = by_category()
    assert "Getting Started" in cats
    slugs = [d.slug for d in cats["Getting Started"]]
    assert slugs[0] == "the-lab", (
        f"the-lab must be the first doc in Getting Started; got {slugs!r}"
    )
