"""Phase F regression tests + Knowledge cross-link regression.

Covers:
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
