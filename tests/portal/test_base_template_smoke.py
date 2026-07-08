"""Base-template smoke suite (design system v2).

Every HTML page extends templates/base.html (welcome.html is the one bespoke
exception). This suite locks the shell contract across ALL page routes:

- the route renders (200),
- exactly one middleware-injected ui-theme-vars block,
- the shared nav is present (except welcome),
- the document is complete (closing </html>),
- no external font fetch (self-hosted fonts only — the lab is airgapped
  by default and must paint identically offline).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from arail.portal import app as portal_app

MARK = 'id="ui-theme-vars"'

# Every GET route that renders a full portal page. Kept explicit (rather than
# scraped from app.routes) so a route accidentally dropping its template shows
# up here as a hard failure, not silent shrinkage.
PAGE_ROUTES = [
    "/",
    "/mission",
    "/chat",
    "/tuning",
    "/teacher",
    "/research",
    "/knowledge",
    "/graph",
    "/agents",
    "/skills",
    "/admin",
    "/plugins",
    "/notebooks",
    "/notebook",
    "/opencode",
    "/open-notebook",
    "/marimo",
    "/terminal",
    "/docs",
    "/docs/dictionary",
    "/design",
    "/integrations/knowledge-canvas",
    "/wiki",
    "/wiki/graph",
    "/welcome",
]

NAV_EXEMPT = {"/welcome"}


@pytest.fixture(scope="module")
def client():
    # /opencode (and other maximus surfaces) are tier-gated to 404 on the
    # default minimalist tier — the smoke suite covers the full surface set.
    import os

    prior = os.environ.get("LAB_TIER")
    os.environ["LAB_TIER"] = "maximus"
    try:
        yield TestClient(portal_app.app)
    finally:
        if prior is None:
            os.environ.pop("LAB_TIER", None)
        else:
            os.environ["LAB_TIER"] = prior


@pytest.mark.parametrize("route", PAGE_ROUTES)
def test_page_renders_complete_with_one_theme_block(client, route):
    r = client.get(route)
    assert r.status_code == 200, f"{route} -> {r.status_code}"
    body = r.text
    assert body.count(MARK) == 1, (
        f"{route}: expected exactly one injected theme block, got {body.count(MARK)}"
    )
    assert body.rstrip().endswith("</html>"), f"{route}: truncated document"
    assert "<title>" in body, f"{route}: missing <title>"


@pytest.mark.parametrize("route", [r for r in PAGE_ROUTES if r not in NAV_EXEMPT])
def test_page_has_shared_nav(client, route):
    body = client.get(route).text
    assert "<nav" in body, f"{route}: shared nav chrome missing"


@pytest.mark.parametrize("route", PAGE_ROUTES)
def test_no_external_font_fetch(client, route):
    body = client.get(route).text
    assert "fonts.googleapis.com" not in body, f"{route}: external font fetch"
    assert "fonts.gstatic.com" not in body, f"{route}: external font fetch"


def test_stylesheet_has_no_external_imports(client):
    css = client.get("/static/style.css").text
    assert "@import url('https" not in css and '@import url("https' not in css, (
        "style.css must not fetch external resources (airgapped default)"
    )
    assert "/static/fonts/" in css, "self-hosted @font-face rules missing"
