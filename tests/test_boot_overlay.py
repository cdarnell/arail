"""Cold-start "warming up" overlay (_boot_overlay.html).

The ask: a fresh boot feels unresponsive — clicking around does nothing
until the lab is warm, with no visual cue that anything is happening.

An EARLIER implementation of this same idea already existed in
_nav.html: it polled /api/ready every 400ms for up to 30s. That's
exactly the kind of unsolicited post-boot check the operator explicitly
ruled out — and it had a real failure mode besides: its own /api/ready
fetch could stall behind the same server-side congestion that makes the
rest of the page unresponsive during a genuine cold start, so it could
silently fail to appear precisely when it was needed most. It's been
removed (see test_old_polling_overlay_is_gone below).

The replacement is purely time-based: the server stamps a wall-clock
timestamp into every page — set once at import as a safety default, then
RE-STAMPED at the end of the startup handler (app.py) once the app can
actually serve a request. A real cold boot was measured taking ~10s just
to reach that point (heavy imports — world_forge/dac_world, LanceDB), so
anchoring to raw import start would have left the whole ~10s budget
already spent before any browser could load the first page — the
opposite of what the operator asked for. The client compares the
(corrected) stamp against its own Date.now() once and either shows the
overlay for the remaining budget or does nothing. No fetch, no XHR, no
polling, no repeated timers of any kind, not even a local setInterval —
this suite exists specifically to keep that invariant from drifting,
since "add a readiness poll" is the obvious-but-wrong next edit for
anyone who revisits this file without reading the comments (it's
happened once already, see above).
"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient


def _client():
    from arail.portal import app as portal_app
    return TestClient(portal_app.app)


def test_boot_epoch_is_a_static_value_not_recomputed_per_request():
    """Not per-request: reading it twice between requests sees the same
    value — it's a plain global, never touched inside a route handler."""
    from arail.portal import app as portal_app
    first = portal_app.templates.env.globals["boot_epoch_ms"]
    second = portal_app.templates.env.globals["boot_epoch_ms"]
    assert first == second
    assert isinstance(first, int) and first > 0


def test_boot_epoch_is_re_stamped_at_the_end_of_startup_not_import():
    """The load-bearing fix: anchoring to raw import time would leave the
    overlay's whole budget spent before the app can serve anything (a
    real cold boot was measured at ~10s of import cost alone). Confirm
    the startup handler moves the stamp forward to close to "now" — not
    the (necessarily earlier) import-time value.

    Needs `with TestClient(...) as client:` — a bare TestClient(app).get()
    does NOT run the ASGI lifespan startup event in this stack (verified
    empirically), so _READY stays False and the stamp never advances;
    every other test in this repo's suite uses the bare form deliberately
    because it doesn't depend on startup side effects, but this one does.
    """
    import time
    from arail.portal import app as portal_app

    before_any_request = portal_app.templates.env.globals["boot_epoch_ms"]
    with TestClient(portal_app.app) as client:
        assert portal_app._READY is True
        res = client.get("/")
        assert res.status_code == 200
        after_startup = portal_app.templates.env.globals["boot_epoch_ms"]

    now_ms = int(time.time() * 1000)
    assert after_startup >= before_any_request, (
        "the startup handler must move the stamp FORWARD (to when the app "
        "can actually serve), never backward"
    )
    assert now_ms - after_startup < 5000, (
        "the re-stamped value should be close to 'now' in a fast test "
        f"process — got a gap of {now_ms - after_startup}ms, suggesting "
        "the startup re-stamp didn't fire"
    )


def test_boot_overlay_ms_defaults_to_ten_seconds():
    from arail.portal import app as portal_app
    assert portal_app.templates.env.globals["boot_overlay_ms"] == 10_000


def test_boot_overlay_ms_is_env_overridable(monkeypatch):
    """ARAIL_BOOT_OVERLAY_MS lets an operator tune the window — read once
    at import, matching every other boot-time constant in this module."""
    import importlib
    monkeypatch.setenv("ARAIL_BOOT_OVERLAY_MS", "4000")
    from arail.portal import app as portal_app
    importlib.reload(portal_app)
    try:
        assert portal_app.templates.env.globals["boot_overlay_ms"] == 4000
    finally:
        monkeypatch.delenv("ARAIL_BOOT_OVERLAY_MS", raising=False)
        importlib.reload(portal_app)  # restore the default for later tests


def test_dashboard_html_carries_the_boot_stamp():
    """The dashboard (any base.html page) embeds both values verbatim —
    this is the entire client-server contract, no endpoint involved."""
    from arail.portal import app as portal_app
    client = _client()
    res = client.get("/")
    assert res.status_code == 200
    assert f"var bootEpochMs = {portal_app.templates.env.globals['boot_epoch_ms']};" in res.text
    assert "var windowMs = 10000;" in res.text


def test_overlay_markup_defaults_hidden_for_no_js_safety():
    """Progressive enhancement: without JS, the overlay must never show
    or block the page — `hidden` in the raw HTML is what guarantees that."""
    client = _client()
    res = client.get("/")
    assert res.status_code == 200
    assert '<div id="arail-boot-overlay" class="arail-boot-overlay" hidden' in res.text


def test_overlay_present_on_every_base_html_page_not_just_dashboard():
    client = _client()
    for path in ("/", "/chat", "/autoresearch", "/agents"):
        res = client.get(path)
        assert res.status_code == 200, path
        assert 'id="arail-boot-overlay"' in res.text, f"{path} missing the boot overlay"


def test_old_polling_overlay_is_gone():
    """The pre-existing lab-warmup-overlay (400ms /api/ready polling,
    30s hard cap) must not still be rendered anywhere — a page showing
    BOTH overlays at once would be genuinely broken UX, and the old one's
    dependence on a live fetch is the exact failure mode this replaces."""
    client = _client()
    res = client.get("/")
    assert res.status_code == 200
    assert "lab-warmup-overlay" not in res.text
    assert "lab-warmup-elapsed" not in res.text
    nav_html = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "src" / "arail" / "portal" / "templates" / "_nav.html"
    ).read_text(encoding="utf-8")
    assert "lab-warmup-overlay" not in nav_html
    # A prose mention (explaining *why* the old poller was removed) is
    # fine and expected; an actual fetch call is not.
    assert "fetch('/api/ready'" not in nav_html
    assert 'fetch("/api/ready"' not in nav_html


def test_welcome_page_does_not_get_the_overlay():
    """welcome.html is deliberately not a base.html child (nav-less,
    bespoke first-run page) — it must not pick this up by accident."""
    import os
    client = _client()
    # welcome_page 302s to / once onboarded (autouse fixture sets a real
    # password), so read the template file directly for the no-overlay
    # assertion rather than fighting the redirect.
    welcome_html = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "src" / "arail" / "portal" / "templates" / "welcome.html"
    ).read_text(encoding="utf-8")
    assert "arail-boot-overlay" not in welcome_html


def test_overlay_script_never_makes_a_network_call():
    """The load-bearing invariant: this must stay a pure timer, forever.
    A future edit that adds fetch/XHR/WebSocket here would silently
    reintroduce a post-boot check the operator explicitly ruled out."""
    overlay_html = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "src" / "arail" / "portal" / "templates" / "_boot_overlay.html"
    ).read_text(encoding="utf-8")
    forbidden = ("fetch(", "XMLHttpRequest", "WebSocket(", "EventSource(", "setInterval(")
    for token in forbidden:
        assert token not in overlay_html, (
            f"_boot_overlay.html must never contain {token!r} — it's meant "
            "to be a one-shot, purely time-based UI cue, not a health check"
        )
    # Exactly one timer: the single dismiss-after-remaining-budget call.
    assert overlay_html.count("setTimeout(") == 2  # the dismiss() schedule + its own internal removal delay


def test_overlay_math_matches_the_documented_contract():
    """remaining = (bootEpochMs + windowMs) - Date.now(); <=0 → no-op.
    Pin the literal expression so a refactor can't quietly change the
    semantics (e.g. flipping to "always show for windowMs regardless of
    how late the page loaded", which would defeat the honesty of the cue)."""
    overlay_html = (
        __import__("pathlib").Path(__file__).resolve().parent.parent
        / "src" / "arail" / "portal" / "templates" / "_boot_overlay.html"
    ).read_text(encoding="utf-8")
    assert "(bootEpochMs + windowMs) - Date.now()" in overlay_html
    assert re.search(r"if\s*\(remaining\s*<=\s*0\)\s*return", overlay_html)
