"""Knowledge page layout — the restructured narrative page.

Covers the Phase-1 restructure guarantees:
- /knowledge renders (200) with and without a mounted World
- the graph canvas is embedded directly (no /wiki/graph iframe)
- the narrative sections are present in order: hero → brain graph →
  agent focus → review queue → library → docs footer
- the no-World fallback renders the "Mount a World" hero
- the standalone graph pages keep their scroll lock (body overflow moved
  out of the shared graph.css)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _get_client(monkeypatch, tmp_path, lab_tier: str = "min") -> TestClient:
    monkeypatch.setenv("LAB_TIER", lab_tier)
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    import arail.portal.app as _app_mod
    return TestClient(_app_mod.app)


def _get_knowledge_html(client: TestClient) -> str:
    response = client.get("/knowledge")
    assert response.status_code in (200, 302, 307), response.status_code
    if response.status_code in (302, 307):
        response = client.get(response.headers["location"])
    assert response.status_code == 200
    return response.text


def test_knowledge_page_renders_without_world(monkeypatch, tmp_path):
    """Fresh lab (no mount sidecar in tmp cwd) → 200 + mount-a-World hero."""
    client = _get_client(monkeypatch, tmp_path)
    html = _get_knowledge_html(client)
    assert "Mount a World" in html, (
        "No-World fallback hero missing — the page must degrade gracefully "
        "when nothing is mounted."
    )
    assert 'href="/worlds"' in html


def test_knowledge_page_has_embedded_canvas_no_iframe(monkeypatch, tmp_path):
    """The graph is one embedded canvas — the two iframes must stay dead."""
    client = _get_client(monkeypatch, tmp_path)
    html = _get_knowledge_html(client)
    assert 'id="graph-canvas"' in html, "Embedded graph canvas missing."
    assert 'id="graph-status"' in html, (
        "Graph loading affordance missing — a busy graph must never render "
        "as silently blank."
    )
    assert "/wiki/graph?embed=1" not in html, (
        "A /wiki/graph iframe crept back in — the restructure embeds "
        "_graph_canvas.html directly."
    )


def test_knowledge_page_section_order(monkeypatch, tmp_path):
    """Narrative order: hero → brain → focus → review queue → library."""
    client = _get_client(monkeypatch, tmp_path)
    html = _get_knowledge_html(client)
    anchors = [
        'id="kb-hero"',
        'id="brain-graph"',
        'id="kb-focus"',
        'id="compiled-kb-panel"',
        'id="kb-library"',
    ]
    positions = []
    for a in anchors:
        idx = html.find(a)
        assert idx != -1, f"Section anchor missing from /knowledge: {a}"
        positions.append(idx)
    assert positions == sorted(positions), (
        "Knowledge sections out of order: expected hero → brain graph → "
        f"agent focus → review queue → library, got offsets {positions}."
    )


def test_knowledge_page_keeps_library_machinery(monkeypatch, tmp_path):
    """The Files-view machinery (IDs the JS binds to) survived the split."""
    client = _get_client(monkeypatch, tmp_path)
    html = _get_knowledge_html(client)
    for element_id in (
        "kb-tree", "kb-viewer", "kb-editor", "kb-welcome",
        "world-terms-view", "wt-viewtoggle", "kb-reveal-toast",
        "kb-upload-input", "kb-rebuild-btn",
    ):
        assert f'id="{element_id}"' in html, (
            f"Load-bearing element #{element_id} missing — knowledge-files.js/"
            "world-terms.js/compiled-kb.js bind to it."
        )
    # The moved scripts are wired up.
    assert "/static/js/knowledge-files.js" in html
    assert "/static/js/knowledge-page.js" in html


def test_standalone_graph_pages_keep_scroll_lock(monkeypatch, tmp_path):
    """body{overflow:hidden} moved from graph.css into the standalone
    wrappers — both full-page graphs must still carry it, and the shared
    stylesheet must not (it now loads inside the scrolling knowledge page)."""
    client = _get_client(monkeypatch, tmp_path)
    for path in ("/wiki/graph", "/graph"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} → {r.status_code}"
        assert "overflow: hidden" in r.text, (
            f"{path} lost its scroll lock after the graph.css relocation."
        )
    css = client.get("/static/graph.css")
    assert css.status_code == 200
    assert "body { overflow: hidden; }" not in css.text, (
        "graph.css must not restyle the host page body — that freezes "
        "scrolling on /knowledge where the canvas is embedded."
    )
