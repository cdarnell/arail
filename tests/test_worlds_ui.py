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
# worlds.html — static instances hint replaces the dismissible deprecation
# notice (worlds-select-removal: the transitional banner comes down).
# ---------------------------------------------------------------------------

def test_worlds_page_has_static_instances_hint():
    client = _client()
    body = client.get("/worlds").text
    assert "./arailctl start --world" in body
    # The old dismissible banner + its localStorage key are gone.
    assert "worlds-deprecation-dismiss" not in body
    assert "arail.worlds.deprecation-dismissed" not in body


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
# nav.js — no mutation (worlds-select-removal): no POST to /api/worlds/select,
# no change-world row/route. Roster fetches survive.
# ---------------------------------------------------------------------------

def test_nav_js_never_posts_to_worlds_select():
    src = NAV_JS.read_text(encoding="utf-8")
    assert "/api/worlds/select" not in src
    assert "change-world" not in src
    assert "?step=world" not in src


def test_nav_js_still_fetches_instances_and_renders_open_link():
    src = NAV_JS.read_text(encoding="utf-8")
    assert "/api/instances" in src
    assert "action === 'open'" in src
    assert "window.open(url" in src


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
