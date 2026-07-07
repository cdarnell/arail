"""Per-page UI-palette recolor tests (sprint 2026-06-14, recolor addendum §6).

The ``inject_ui_theme`` middleware injects ``<style id="ui-theme-vars">`` with
the live World palette before the first ``</head>`` on every text/html page —
not just ``welcome.html`` (which injects it inline). Mounting a World recolors
the whole lab; unmounting reverts. These tests assert that across a
representative spread of the portal pages, including routes that pass NO
``_identity_ctx()`` (``/skills``, ``/design``, ``/blueprints-overview``).

Mount pattern mirrors ``test_world_identity_flip``: re-``monkeypatch.setattr``
``world_mount._default_data_dir`` (same instance the autouse
``_no_ambient_world_mount`` fixture uses → our override wins).

arail weights: 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from arail import world_mount as wm
from arail.portal import app as portal_app

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"

MARK = 'id="ui-theme-vars"'

# Default (unmounted) palette = blue-cyan-lab.
DEFAULT_BG = "#0a0a0f"
DEFAULT_BLUE = "#00d4ff"
# Mounted physics palette = slate-violet (retargeted fixture).
PHYSICS_BG = "#0d1018"
PHYSICS_PURPLE = "#9e8cff"


def _client():
    return TestClient(portal_app.app)


def _theme_block(body: str) -> str:
    """Extract the injected <style id="ui-theme-vars"> block contents."""
    m = re.search(r'<style id="ui-theme-vars">(.*?)</style>', body, re.S)
    assert m, "no injected ui-theme-vars block found"
    return m.group(1)


@pytest.fixture
def mounted_physics(tmp_path, monkeypatch):
    """Mount PHYSICS (palette_hint=slate-violet) and make it the default mount."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    return data_dir


# ════════════════════════════ HAPPY (10%) ════════════════════════════

def test_dashboard_carries_default_palette_unmounted():
    """A page that does NOT inline the block still carries the injected default
    palette (blue-cyan-lab) when unmounted. Proves the middleware fires."""
    body = _client().get("/").text
    assert MARK in body
    block = _theme_block(body)
    assert f"--bg: {DEFAULT_BG};" in block
    assert f"--blue: {DEFAULT_BLUE};" in block


def test_nav_names_the_world_when_mounted(mounted_physics):
    """The nav shows a World badge so it's explicit the theme + knowledge are
    DEFINED BY the mounted World (not the default lab). Reinforces the flip."""
    body = _client().get("/").text
    assert "world-badge" in body
    assert "Physics World" in body
    # The badge is now the World-switcher trigger (sprint 2026-06-14-world-switcher):
    # its tooltip explains the load/unload action that swaps theme + knowledge.
    assert "swaps the lab's theme" in body


def test_nav_has_no_world_badge_when_unmounted():
    """No World mounted → the switcher shows the ◇ AI Lab affordance, not a
    World name. The badge element is now always present as the switcher trigger
    (sprint 2026-06-14-world-switcher), so we assert the unmounted label instead
    of the badge's absence."""
    body = _client().get("/").text
    assert "world-switcher" in body
    assert "◇ AI Lab" in body
    # The switcher summary shows the default affordance, not a "◆ <World> World".
    summary = body.split('class="world-badge"', 1)[1].split("</summary>", 1)[0]
    assert "◇ AI Lab" in summary
    assert "◆" not in summary  # no mounted-World diamond when unmounted


# ════════════════════════════ SETUP (30%) ════════════════════════════

# Representative spread crossing the "passes _identity_ctx()" boundary.
# /skills, /design, /blueprints-overview pass NO context — they prove the
# "can't be forgotten" property that the include-partial approach would miss.
RECOLOR_PAGES = [
    "/",                      # dashboard (has context)
    "/chat",
    "/admin",
    "/graph",
    "/agents",
    "/knowledge",
    "/tuning",
    "/skills",                # NO _identity_ctx()
    "/design",                # NO _identity_ctx()
    "/blueprints-overview",   # NO _identity_ctx()
]


@pytest.mark.parametrize("route", RECOLOR_PAGES)
def test_every_page_carries_injection(route):
    """Each representative page contains the injected <style id="ui-theme-vars">,
    including the no-context routes."""
    r = _client().get(route)
    assert r.status_code == 200, f"{route} -> {r.status_code}"
    assert MARK in r.text, f"{route} missing injection"


@pytest.mark.parametrize("route", RECOLOR_PAGES)
def test_mount_recolors_every_page(route, mounted_physics):
    """Core win condition: mounting physics recolors EVERY page (incl. no-context
    routes) to slate-violet; the default blue-cyan no longer appears in the
    injected block."""
    body = _client().get(route).text
    block = _theme_block(body)
    assert f"--bg: {PHYSICS_BG};" in block, f"{route} not recolored"
    assert f"--purple: {PHYSICS_PURPLE};" in block
    assert f"--bg: {DEFAULT_BG};" not in block, f"{route} still default bg"


# ════════════════════════════ REGRESSION (10%) ════════════════════════════

def test_unmount_reverts(tmp_path, monkeypatch):
    """Mount → recolor, then unmount → revert to default. Proves liveness and
    no sticky state (instant-flip preserved)."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    empty = tmp_path / "empty"
    data_dir.mkdir()
    empty.mkdir()

    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    block = _theme_block(_client().get("/skills").text)
    assert f"--bg: {PHYSICS_BG};" in block

    # Unmount: point the default at an empty (no-mount) dir.
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    block = _theme_block(_client().get("/skills").text)
    assert f"--bg: {DEFAULT_BG};" in block
    assert f"--bg: {PHYSICS_BG};" not in block


def test_welcome_not_double_injected():
    """welcome.html already injects id="ui-theme-vars" inline; the idempotency
    gate must NOT inject a second block."""
    body = _client().get("/welcome").text
    assert body.count(MARK) == 1


def test_non_html_response_untouched():
    """A JSON API route is not text/html → never rewritten; no <style injected,
    content-type preserved."""
    r = _client().get("/api/ready")
    assert "application/json" in r.headers.get("content-type", "")
    assert MARK not in r.text
    assert "<style" not in r.text
    # Body is valid JSON (not corrupted by any rewrite).
    json.loads(r.text)


def test_static_asset_untouched():
    """A static CSS asset is not rewritten."""
    r = _client().get("/static/style.css")
    assert r.status_code == 200
    assert MARK not in r.text
    assert "text/css" in r.headers.get("content-type", "")


# ════════════════════════════ SECURITY (20%) ════════════════════════════

def test_injection_is_xss_safe_by_construction(tmp_path, monkeypatch):
    """A hostile palette_hint can only SELECT a preset id — it can never carry
    markup into the page. The resolver reads the staged face.json; overwrite its
    palette_hint with a markup-laden value and confirm the resolver's id-match
    guard rejects it (falls back to the default preset) so the injected block
    contains ONLY closed-preset variable values, never the raw face text.
    """
    from arail.identity import effective_identity

    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)

    # The resolver reads record.staged_dir / "face.json" (mounted_face). Inject
    # a hostile palette_hint there post-mount.
    attack = '</style><script>alert(1)</script>'
    rec = wm.current_mount(data_dir)
    face_path = pathlib.Path(rec.staged_dir) / "face.json"
    assert face_path.exists(), "staged face.json not found"
    face = json.loads(face_path.read_text())
    face["palette_hint"] = attack
    face_path.write_text(json.dumps(face))

    ident = effective_identity(data_dir)
    # Hostile hint did NOT resolve to a preset → fell back to default.
    assert ident.ui_theme.id == "blue-cyan-lab"

    body = _client().get("/skills").text
    block = _theme_block(body)
    # The injected block is a real preset's :root — no attacker markup.
    assert "<script" not in block
    assert "alert(1)" not in block
    assert ":root {" in block
    assert f"--bg: {DEFAULT_BG};" in block


# ═══════════════════ RECOLOR COMPLETENESS (var-ified accents) ═══════════════════

def test_root_defaults_agree_with_default_theme_and_components_stay_var_driven():
    """Design system v2: style.css :root carries REAL default-theme values (a
    page renders correctly even if the middleware injection fails) and the
    injected ui-theme-vars block overrides them per World. Two invariants
    replace the old blanket no-literals rule:

    1. Every default accent in the :root block equals the default theme's
       value — style.css can never disagree with ui_theme.py.
    2. Component rules (everything after the :root block) stay var(--…)-driven
       — no hard-coded accent literal that would refuse to repaint on mount.
    """
    import re

    from arail.ui_theme import default_ui_theme

    css = (pathlib.Path(__file__).parents[1]
           / "src/arail/portal/static/style.css").read_text()
    root_start = css.index(":root {")
    root_end = css.index("}", root_start)
    root_block = css[root_start:root_end]
    rest = css[root_end:]

    colors = default_ui_theme().dark
    for token, value in (
        ("--bg", colors.bg), ("--surface", colors.surface), ("--text", colors.text),
        ("--accent", colors.accent), ("--accent2", colors.accent2),
        ("--positive", colors.positive), ("--warn", colors.warn),
        ("--danger", colors.danger), ("--info", colors.info),
    ):
        assert re.search(rf"{token}:\s*{value};", root_block), (
            f"style.css :root default for {token} must be {value} "
            "(the default theme's value from ui_theme.py)"
        )

    for lit in ("#00d4ff", "#00ff41", "#ffb000", "#ff3355", "#b48eff",
                "rgba(0,212,255", "rgba(0, 212, 255",
                "rgba(0,255,65", "rgba(0, 255, 65",
                "rgba(255,176,0", "rgba(255, 176, 0",
                "rgba(255,51,85", "rgba(255, 51, 85"):
        assert lit not in rest, (
            f"hard-coded accent {lit!r} outside :root should be var(--…)-driven"
        )


def test_theme_css_emits_rgb_channel_vars():
    """theme_css() derives an RGB-channel companion for each hex token so
    rgba(var(--blue-rgb), a) repaints; the default stays identical and a
    different World palette yields different channels."""
    from arail.ui_theme import theme_css, load_ui_theme
    default_css = theme_css(load_ui_theme("blue-cyan-lab"))
    assert "--blue-rgb: 0, 212, 255;" in default_css       # unchanged default
    assert "--green-rgb:" in default_css and "--red-rgb:" in default_css
    violet_css = theme_css(load_ui_theme("slate-violet"))
    assert "--blue-rgb:" in violet_css
    assert "--blue-rgb: 0, 212, 255;" not in violet_css    # repaints
