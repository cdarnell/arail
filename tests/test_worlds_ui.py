"""WP7 — nav.js/worlds.js liveness roster, worlds.html deprecation notice,
base.html page title (ARCHITECTURE.md §5.4, §5.5).

The manual "two tabs are visually unmistakable" check is deferred to QA
(headless template/source assertions here, per the builder task's explicit
note); everything verifiable without a browser is covered.
"""
from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from arail.portal import app as portal_app

REPO_ROOT = Path(__file__).resolve().parent.parent
NAV_JS = REPO_ROOT / "src" / "arail" / "portal" / "static" / "nav.js"
WORLDS_JS = REPO_ROOT / "src" / "arail" / "portal" / "static" / "js" / "worlds.js"


def _client():
    return TestClient(portal_app.app)


# ---------------------------------------------------------------------------
# base.html — page title always carries "· :<port>" (§5.5)
# ---------------------------------------------------------------------------

def test_page_title_includes_bound_port(monkeypatch):
    monkeypatch.setitem(portal_app.templates.env.globals, "portal_port", 8090)
    client = _client()
    body = client.get("/worlds").text
    assert "· :8090" in body
    assert "<title>" in body


def test_page_title_two_different_ports_render_differently(monkeypatch):
    client = _client()
    monkeypatch.setitem(portal_app.templates.env.globals, "portal_port", 8080)
    root_title = client.get("/worlds").text.split("<title>")[1].split("</title>")[0]
    monkeypatch.setitem(portal_app.templates.env.globals, "portal_port", 8090)
    instance_title = client.get("/worlds").text.split("<title>")[1].split("</title>")[0]
    assert root_title != instance_title


# ---------------------------------------------------------------------------
# worlds.html — deprecation notice (§5.5), dismissible, above the grid
# ---------------------------------------------------------------------------

def test_worlds_page_has_dismissible_deprecation_notice():
    client = _client()
    body = client.get("/worlds").text
    assert "worlds-deprecation-notice" in body
    assert "./arailctl start --world" in body
    assert "worlds-deprecation-dismiss" in body
    # Not a modal — the notice's own markup is a plain card div, not a
    # <dialog>/overlay wrapper (other unrelated modals elsewhere on the
    # page, e.g. the model-switcher, are not this notice's concern).
    notice_start = body.index("worlds-deprecation-notice")
    notice_end = body.index("Catalog", notice_start)
    notice_html = body[notice_start:notice_end]
    assert "<dialog" not in notice_html


# ---------------------------------------------------------------------------
# nav.js — roster viewer: fetches /api/instances, routes live rows to Open
# (§5.4). Source-level assertions (no headless browser available here).
# ---------------------------------------------------------------------------

def test_nav_js_fetches_instances_roster():
    src = NAV_JS.read_text(encoding="utf-8")
    assert "/api/instances" in src
    assert "action === 'open'" in src
    assert "data-url" in src


def test_nav_js_launch_command_not_a_process_spawn():
    """The dropdown never spawns a process for a not-live World that would
    remount elsewhere — it disables the row and shows the CLI command."""
    src = NAV_JS.read_text(encoding="utf-8")
    assert "./arailctl start --world" in src
    for banned in ("child_process", "exec(", "spawn("):
        assert banned not in src


# ---------------------------------------------------------------------------
# worlds.js — Mount/Launch/Open/Unmount button matrix (§5.3)
# ---------------------------------------------------------------------------

def test_worlds_js_has_all_four_button_states():
    src = WORLDS_JS.read_text(encoding="utf-8")
    assert "'Mount'" in src
    assert "'Launch'" in src
    assert "'Open'" in src
    assert "'Unmount'" in src


def test_worlds_js_launch_copies_command_never_spawns():
    src = WORLDS_JS.read_text(encoding="utf-8")
    assert "showLaunchCommand" in src
    assert "./arailctl start --world" in src
    for banned in ("child_process", "exec(", "spawn("):
        assert banned not in src


def test_worlds_js_fetches_instances_for_button_state():
    src = WORLDS_JS.read_text(encoding="utf-8")
    assert "/api/instances" in src
