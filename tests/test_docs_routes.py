"""Docs route tests — Sprint 1 regressions + Sprint 2 hub/viewer tests.

Sprint 1 covers:
- F18: 'docs' in _TIER_SURFACES['min'] — canary test
- F19: Docs link renders in a min-tier nav response
- F20 (max variant): Docs link renders in a max-tier nav response
- Knowledge cross-link: GET /knowledge contains href="/docs" and "Official Docs"
"""

from __future__ import annotations

import importlib
import os

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_client(monkeypatch, tmp_path, lab_tier: str = "min") -> TestClient:
    monkeypatch.setenv("LAB_TIER", lab_tier)
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    # Import app fresh per call so LAB_TIER env var is picked up.
    import arail.portal.app as _app_mod
    return TestClient(_app_mod.app)


# ---------------------------------------------------------------------------
# F18 — canary: 'docs' must be in _TIER_SURFACES['min']
# ---------------------------------------------------------------------------

def test_docs_in_min_tier_surfaces():
    """Regression sentinel: if a future PR trims 'docs' from min, CI breaks."""
    from arail.portal.app import _TIER_SURFACES
    assert "docs" in _TIER_SURFACES["min"], (
        "'docs' was removed from _TIER_SURFACES['min']. "
        "This is a regression of the fix in docs-hub-sprint-1. "
        "Restore it before merging."
    )


def test_docs_in_max_tier_surfaces():
    """'docs' must also remain in max tier."""
    from arail.portal.app import _TIER_SURFACES
    assert "docs" in _TIER_SURFACES["max"]


# ---------------------------------------------------------------------------
# F19 — Docs link renders in min-tier nav HTML
# ---------------------------------------------------------------------------

def test_docs_link_renders_in_min_nav(monkeypatch, tmp_path):
    """GET / with LAB_TIER=min must return HTML containing href="/docs"."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    response = client.get("/")
    assert response.status_code in (200, 302, 307), response.status_code
    # Follow redirect if needed
    if response.status_code in (302, 307):
        response = client.get(response.headers["location"])
    assert 'href="/docs"' in response.text, (
        "Docs link missing from min-tier nav. Phase F regression."
    )


def test_docs_link_renders_in_max_nav(monkeypatch, tmp_path):
    """GET / with LAB_TIER=max must also contain href="/docs"."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="max")
    response = client.get("/")
    assert response.status_code in (200, 302, 307), response.status_code
    if response.status_code in (302, 307):
        response = client.get(response.headers["location"])
    assert 'href="/docs"' in response.text, (
        "Docs link missing from max-tier nav."
    )


# ---------------------------------------------------------------------------
# Knowledge cross-link regression
# ---------------------------------------------------------------------------

def test_knowledge_page_contains_docs_link(monkeypatch, tmp_path):
    """GET /knowledge must contain both href="/docs" and the banner text."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    response = client.get("/knowledge")
    assert response.status_code in (200, 302, 307), response.status_code
    if response.status_code in (302, 307):
        response = client.get(response.headers["location"])
    html = response.text
    assert 'href="/docs"' in html, (
        "Knowledge page is missing a link to /docs. "
        "The Official Docs banner was either removed or not rendered."
    )
    assert "Official Docs" in html, (
        "Knowledge page is missing 'Official Docs' banner text."
    )


# ---------------------------------------------------------------------------
# Sprint 2 — Step 1: rename + redirect (F10, F11)
# ---------------------------------------------------------------------------

def test_legacy_design_redirect(monkeypatch, tmp_path):
    """GET /docs/design.md returns 301 → /docs/portal-design.md (F10)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs/design.md", follow_redirects=False)
    assert resp.status_code == 301, f"Expected 301 got {resp.status_code}"
    assert resp.headers["location"].endswith("/docs/portal-design.md"), (
        f"301 target wrong: {resp.headers['location']}"
    )


def test_no_slug_collision_after_rename():
    """all_docs() must load without RuntimeError and portal-design slug present (F11)."""
    from arail.portal import docs_registry
    docs_registry._invalidate_cache()
    docs = docs_registry.all_docs()
    slugs = {d.slug for d in docs}
    assert "portal-design" in slugs, (
        "portal-design slug not found — did the rename land?"
    )
    # The root design.md (slug='design') may still exist; what must NOT happen
    # is a RuntimeError — all_docs() above would have raised if there were a
    # collision.  Reaching this line means no collision.


# ---------------------------------------------------------------------------
# Sprint 2 — Step 2: Hub handler tests (§6.1 tests 1-8)
# ---------------------------------------------------------------------------

def test_hub_renders_200_min_tier(monkeypatch, tmp_path):
    """GET /docs returns 200 HTML with at least one doc card (test 1)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs", follow_redirects=False)
    assert resp.status_code == 200, f"Expected 200 got {resp.status_code}"
    assert "text/html" in resp.headers["content-type"]
    # At least one category section must be present
    assert "doc-card" in resp.text or "docs-category" in resp.text or "Getting Started" in resp.text


def test_hub_renders_200_max_tier(monkeypatch, tmp_path):
    """GET /docs on max tier returns 200 (test 2)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="max")
    resp = client.get("/docs", follow_redirects=False)
    assert resp.status_code == 200


def test_hub_min_tier_hides_architect_audience_docs(monkeypatch, tmp_path):
    """architect-audience docs must not appear in min-tier Hub HTML (F3, test 3)."""
    from arail.portal import docs_registry
    docs_registry._invalidate_cache()
    # Collect all architect-audience slugs
    architect_slugs = [d.slug for d in docs_registry.all_docs() if d.audience == "architect"]
    if not architect_slugs:
        pytest.skip("No architect-audience docs in registry; test requires at least one.")

    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs")
    assert resp.status_code == 200
    html = resp.text
    for slug in architect_slugs:
        assert f'data-slug="{slug}"' not in html, (
            f"architect-audience slug '{slug}' leaked into min-tier Hub (F3)"
        )


def test_hub_empty_registry_renders_fallback(monkeypatch, tmp_path):
    """When by_category() returns {}, Hub returns 200 with fallback panel (F1, test 4)."""
    from arail.portal import docs_registry
    monkeypatch.setattr(docs_registry, "by_category", lambda: {})

    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "unavailable" in resp.text.lower() or "INDEX.md" in resp.text


def test_hub_featured_strip_contains_slugs(monkeypatch, tmp_path):
    """Hub renders a featured strip with expected slugs when they exist (test 5)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs")
    assert resp.status_code == 200
    # At least one of the three featured slugs must appear
    featured_slugs = ["agents-explained", "BUDDY", "api-conventions"]
    found = any(slug in resp.text for slug in featured_slugs)
    assert found, "None of the featured slugs appear in Hub HTML"


def test_hub_search_filter_input_present(monkeypatch, tmp_path):
    """Hub hero must contain a search input (test 7)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert 'type="search"' in resp.text or 'id="docs-search"' in resp.text


def test_hub_card_title_is_escaped(monkeypatch, tmp_path):
    """Doc card titles with HTML special chars render as text, not markup (F8, test 8)."""
    from arail.portal import docs_registry
    from dataclasses import replace as _replace

    # Inject a fixture doc with a dangerous title
    original_by_category = docs_registry.by_category

    def _patched_by_category():
        cats = original_by_category()
        danger_doc = docs_registry.Doc(
            slug="xss-test",
            path=next(iter(cats.values()))[0].path if cats else __file__,
            title='<script>alert(1)</script>',
            description="XSS test fixture",
            category="Reference",
        )
        result = dict(cats)
        result.setdefault("Reference", ())
        result["Reference"] = result["Reference"] + (danger_doc,)
        return result

    monkeypatch.setattr(docs_registry, "by_category", _patched_by_category)

    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs")
    assert resp.status_code == 200
    assert "<script>alert(1)</script>" not in resp.text, (
        "Raw <script> tag leaked into Hub HTML — Jinja autoescape failed (F8)"
    )
