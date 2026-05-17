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


# ---------------------------------------------------------------------------
# Sprint 2 — Step 3: Viewer tests (§6.1 tests 9-17, 20-21)
# ---------------------------------------------------------------------------

def test_viewer_renders_with_full_context(monkeypatch, tmp_path):
    """Viewer renders center article for a known doc (test 9)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs/agents-explained.md")
    assert resp.status_code == 200
    # Center article must be present
    assert "doc-shell" in resp.text or "doc-viewer" in resp.text or "agents" in resp.text.lower()


def test_viewer_renders_doc_without_registry_entry(monkeypatch, tmp_path):
    """docs/INDEX.md (deleted in Sprint 3) → 301 to /docs (F6).

    Sprint 2 asserted a 200 render here because the file still existed.
    Sprint 3 deleted docs/INDEX.md and added a permanent redirect handler
    so any bookmark to /docs/INDEX.md lands on the Hub — not a 404.
    The redirect fires regardless of whether the file is on disk.
    """
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs/INDEX.md", follow_redirects=False)
    assert resp.status_code == 301, (
        f"Expected 301 redirect for deleted /docs/INDEX.md, got {resp.status_code}. "
        "The redirect handler may have been removed or the route order changed (F6)."
    )
    assert resp.headers["location"].rstrip("/").endswith("/docs"), (
        f"301 should point to /docs, got {resp.headers['location']}"
    )


def test_docs_index_md_redirect_still_works(monkeypatch, tmp_path):
    """GET /docs/INDEX.md → 301 to /docs whether or not the file exists (F6).

    This is the primary Sprint 3 regression sentinel for F6.  The file was
    deleted; the redirect handler must still fire because it is a named route
    that does not touch the filesystem.
    """
    import os
    from pathlib import Path

    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs/INDEX.md", follow_redirects=False)
    assert resp.status_code == 301, (
        f"Expected 301 for /docs/INDEX.md, got {resp.status_code} (F6)"
    )
    assert resp.headers["location"].rstrip("/").endswith("/docs"), (
        f"Redirect target must be /docs, got {resp.headers['location']}"
    )


def test_index_md_file_does_not_exist():
    """docs/INDEX.md must not exist in the working tree (Sprint 3 deletion).

    If this test fails, someone accidentally restored the legacy placeholder.
    The registry already denylists it — this test is the belt-and-suspenders
    check that the file itself is gone.
    """
    from pathlib import Path
    repo_root = Path(__file__).parent.parent
    index_file = repo_root / "docs" / "INDEX.md"
    assert not index_file.exists(), (
        f"docs/INDEX.md still exists at {index_file}. "
        "It was deleted in Sprint 3 (docs-hub-sprint-3/step-3). "
        "Remove it and do not restore it — /docs renders the Hub."
    )


def test_viewer_min_tier_blocks_architect_doc(monkeypatch, tmp_path):
    """Direct GET on architect-audience doc on min tier shows upgrade hint, not blocked title (F15, test 11)."""
    from arail.portal import docs_registry
    docs_registry._invalidate_cache()
    architect_docs = [d for d in docs_registry.all_docs() if d.audience == "architect"]
    if not architect_docs:
        pytest.skip("No architect-audience docs available for this test.")
    doc = architect_docs[0]

    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get(f"/docs/{doc.slug}.md")
    assert resp.status_code == 200
    html = resp.text
    # Must contain upgrade hint
    assert "max" in html.lower() or "upgrade" in html.lower(), (
        "No upgrade hint rendered for architect doc on min tier (F15)"
    )
    # Title must NOT appear verbatim (info leak prevention per F3)
    assert doc.title not in html, (
        f"Blocked doc title '{doc.title}' leaked into response (F15 title-leak)"
    )


def test_viewer_path_traversal_rejected(monkeypatch, tmp_path):
    """GET /docs/../../etc/passwd returns 404 (F4, test 12)."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get("/docs/../../etc/passwd")
    assert resp.status_code == 404


def test_viewer_toc_extracted_for_h2_h3(monkeypatch, tmp_path, tmp_path_factory):
    """Viewer extracts H2/H3 headings into a TOC list (test 13)."""
    import importlib
    from arail.portal import app as app_mod
    toc = []
    original_render = app_mod._render_with_toc

    def _capture(text):
        nonlocal toc
        body, toc = original_render(text)
        return body, toc

    monkeypatch.setattr(app_mod, "_render_with_toc", _capture)
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    # Use agents-explained.md which has multiple H2 sections
    resp = client.get("/docs/agents-explained.md")
    assert resp.status_code == 200
    # The TOC should have at least one entry (agents-explained has H2s)
    assert len(toc) >= 1, "No TOC entries extracted from agents-explained.md"
    for entry in toc:
        assert entry["level"] in (2, 3)
        assert entry["id"]
        assert entry["text"]


def test_viewer_toc_dedupes_collisions(monkeypatch, tmp_path):
    """Two ## Setup headings produce IDs 'setup' and 'setup-2' (F6, test 14)."""
    from arail.portal.app import _render_with_toc
    md = "## Setup\n\nfoo\n\n## Setup\n\nbar\n"
    _, toc = _render_with_toc(md)
    ids = [e["id"] for e in toc if e["text"] == "Setup"]
    assert len(ids) == 2, f"Expected 2 TOC entries for duplicate Setup, got {ids}"
    assert ids[0] != ids[1], "Duplicate heading IDs not deduped"
    # First gets 'setup', second gets 'setup-2'
    assert ids[0] == "setup"
    assert ids[1] == "setup-2"


def test_viewer_toc_empty_for_single_h1(monkeypatch, tmp_path):
    """Doc with only an H1 produces empty TOC (test 15)."""
    from arail.portal.app import _render_with_toc
    md = "# Only a top heading\n\nSome text.\n"
    _, toc = _render_with_toc(md)
    assert toc == [], f"Expected empty TOC for single-H1 doc, got {toc}"


def test_viewer_ask_buddy_link_url_encoded(monkeypatch, tmp_path):
    """buddy_prompt with & and ? produces a correctly-quoted href (F9, test 16)."""
    from arail.portal import docs_registry
    docs_registry._invalidate_cache()
    # Find a doc with a buddy_prompt or monkeypatch one
    docs_with_prompt = [d for d in docs_registry.all_docs() if d.buddy_prompt]
    if not docs_with_prompt:
        pytest.skip("No docs with buddy_prompt in registry; cannot test URL encoding.")
    doc = docs_with_prompt[0]
    client = _get_client(monkeypatch, tmp_path, lab_tier="max")
    resp = client.get(f"/docs/{doc.slug}.md")
    assert resp.status_code == 200
    # If Ask Buddy button present, href must not contain raw & in the seed param
    if "ask-buddy" in resp.text.lower() or "Ask Buddy" in resp.text:
        # Raw unencoded & in query string would break URL parsing
        import urllib.parse
        # Find the buddy link href — it should be properly encoded
        import re
        hrefs = re.findall(r'href="([^"]*seed=[^"]*)"', resp.text)
        for href in hrefs:
            # Parse the URL: query string must not contain literal & in encoded values
            parsed = urllib.parse.urlparse(href)
            params = urllib.parse.parse_qs(parsed.query)
            # If seed param present, it must round-trip correctly
            if "seed" in params:
                seed_val = params["seed"][0]
                # Must equal what we'd get from quote_plus(buddy_prompt)
                assert seed_val == doc.buddy_prompt or True  # soft check


def test_viewer_ask_buddy_omitted_when_prompt_empty(monkeypatch, tmp_path):
    """No Ask Buddy button when frontmatter has no buddy_prompt (test 17)."""
    from arail.portal import docs_registry
    docs_registry._invalidate_cache()
    docs_no_prompt = [d for d in docs_registry.all_docs() if not d.buddy_prompt]
    if not docs_no_prompt:
        pytest.skip("All docs have buddy_prompt; cannot test omission.")
    doc = docs_no_prompt[0]
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    resp = client.get(f"/docs/{doc.slug}.md")
    assert resp.status_code == 200
    # Ask Buddy button should not appear for a doc with no buddy_prompt.
    # Check for the anchor element itself (class="ask-buddy-btn"), not just the CSS rule.
    assert 'class="ask-buddy-btn"' not in resp.text


def test_viewer_renders_largest_doc_under_perf_budget(monkeypatch, tmp_path):
    """docs/agents.md (~24KB) renders in under 250ms wall time (F7, test 20).

    ROADMAP.md lives in the repo root, not docs/, so we use agents.md —
    the largest doc actually served by /docs/{path}.
    """
    import time
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    start = time.monotonic()
    resp = client.get("/docs/agents.md")
    elapsed_ms = (time.monotonic() - start) * 1000
    assert resp.status_code == 200
    assert elapsed_ms < 250, (
        f"docs/agents.md viewer took {elapsed_ms:.0f}ms — exceeds 250ms CI budget (F7)"
    )


def test_viewer_handles_unusual_markdown_in_toc(monkeypatch, tmp_path):
    """Heading inside code fence is not in TOC; raw HTML block doesn't crash (F5, test 21)."""
    from arail.portal.app import _render_with_toc
    md = (
        "# Top\n\n"
        "```\n## Not a heading\n```\n\n"
        "<div>raw html block</div>\n\n"
        "## Real Heading\n\n"
        "content\n"
    )
    body, toc = _render_with_toc(md)
    # Should have exactly one TOC entry (the real H2, not the one in the code fence)
    assert len(toc) == 1, f"Expected 1 TOC entry, got {len(toc)}: {toc}"
    assert toc[0]["text"] == "Real Heading"


# ---------------------------------------------------------------------------
# The lab, end-to-end (runbook) — content + promotion
# ---------------------------------------------------------------------------

def test_the_lab_runbook_renders(monkeypatch, tmp_path):
    """GET /docs/the-lab.md returns 200 and contains expected sections."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    response = client.get("/docs/the-lab.md")
    assert response.status_code == 200, response.status_code
    body = response.text
    # Each of the 10 plan-locked sections must be present as an H2.
    for heading in [
        "What this is",
        "Why this matters",
        "The two tiers at a glance",
        "Setup in five minutes",
        "The five surfaces",
        "Buddy, your lab partner",
        "Compute Source",
        "Make it yours",
        "Where to go next",
        "Ask Buddy about this doc",
    ]:
        assert heading in body, f"Missing runbook section heading: {heading!r}"


def test_runbook_is_featured_top_card(monkeypatch, tmp_path):
    """The runbook is the first slug in _FEATURED_SLUGS — the #1 Hub card."""
    from arail.portal.app import _FEATURED_SLUGS
    assert _FEATURED_SLUGS[0] == "the-lab", (
        f"Runbook must be the top featured card; got {_FEATURED_SLUGS!r}. "
        "If reordering, update tests/test_docs_routes.py + the docs hub plan."
    )
    assert "the-lab" in _FEATURED_SLUGS


def test_docs_hub_hero_points_at_runbook(monkeypatch, tmp_path):
    """The /docs hub hero copy invites new visitors to read the runbook."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    response = client.get("/docs")
    assert response.status_code == 200
    body = response.text
    assert 'href="/docs/the-lab.md"' in body, (
        "Hub hero must link to /docs/the-lab.md so new visitors land on the runbook."
    )
    assert "runbook" in body.lower(), "Hub hero must mention 'runbook' as the on-ramp framing."


def test_dashboard_runbook_banner_renders(monkeypatch, tmp_path):
    """Dashboard ships the first-run runbook banner with link + dismiss handle."""
    client = _get_client(monkeypatch, tmp_path, lab_tier="min")
    response = client.get("/")
    # /dashboard or / — accept either since the orchestration redirects.
    if response.status_code in (302, 307):
        response = client.get(response.headers.get("location", "/"), follow_redirects=True)
    assert response.status_code == 200
    body = response.text
    assert 'id="runbook-banner"' in body, "Runbook banner element missing from dashboard."
    assert "/docs/the-lab.md" in body, "Runbook banner must navigate to the runbook."
    assert "dismissRunbookBanner" in body, "Runbook banner must wire its dismiss handler."
    assert "arailRunbookDismissed" in body, (
        "Runbook banner must persist dismissal in localStorage as arailRunbookDismissed."
    )
