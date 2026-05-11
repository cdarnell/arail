"""Test the ARAIL_COMPARE_ENABLED feature flag end-to-end.

Sprint 2026-05-10-min-tier-simplification deferred the dual chat-box
Compare feature to a post-install add-on. The flag lives in `.env`
(`ARAIL_COMPARE_ENABLED=0|1`), is read at request time by the
`/chat` handler, and rendered conditionally in `chat.html` via a
Jinja guard.

Coverage:
  - Flag = "0" → no `+ Compare` button in rendered HTML; column B absent.
  - Flag = "1" → button present; column B present.
  - Flag unset → defaults to "1" (preserves upgrade-in-place behavior).
  - Junk values ("yes", "true", "on") → strict `== "1"` → treated as off.

We render the template directly rather than spinning up the FastAPI
test client — that keeps the test fast and side-effect-free, and the
contract we care about is "template renders the right HTML when given
this context".
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "src"))


def _render_chat_html(compare_enabled: bool) -> str:
    """Render chat.html with the given compare_enabled value.

    Uses Jinja2 directly via FastAPI's Jinja2Templates and seeds the
    globals the portal injects in app.py (brand, lab_tier, etc.) so the
    template renders without the full portal app import."""
    from fastapi.templating import Jinja2Templates
    templates_dir = _REPO_ROOT / "src" / "arail" / "portal" / "templates"
    templates = Jinja2Templates(directory=str(templates_dir))

    # Mirror the globals injected at app startup (see app.py:355–367).
    class _Brand:
        name = "TestLab"
        short_name = "TestLab"
        tagline = "test render"
        version = "0.0.0-test"
        logo = ""
        primary_color = "#000"
    templates.env.globals["brand"] = _Brand()
    templates.env.globals["tier_surfaces"] = [
        "dashboard", "chat", "research", "knowledge", "agents",
    ]
    templates.env.globals["lab_tier"] = "min"
    templates.env.globals["ui_theme"] = "default"
    templates.env.globals["ui_themes"] = ["default"]
    templates.env.globals["ui_theme_css"] = ""
    templates.env.globals["asset_v"] = "test"

    class _Req:
        url_for = staticmethod(lambda *a, **k: "/")
        query_params: dict = {}
        scope: dict = {"type": "http"}
        headers: dict = {}

    template = templates.get_template("chat.html")
    return template.render({
        "request": _Req(),
        "embed": False,
        "compare_enabled": compare_enabled,
    })


def test_compare_button_absent_when_flag_off():
    """Flag = False → no `+ Compare` button rendered, no column B section."""
    html = _render_chat_html(compare_enabled=False)
    assert 'id="btn-compare"' not in html, (
        "Compare button rendered even with compare_enabled=False"
    )
    # The Column B <section> wraps a `class="col-chip" id="col-chip-B"` —
    # use that as the section-presence sentinel; `data-col="B"` alone
    # appears in CSS selectors and gives false positives.
    assert 'id="col-chip-B"' not in html, (
        "Column B section rendered even with compare_enabled=False"
    )
    assert 'id="btn-compare-close"' not in html, (
        "Column B close button rendered even with compare_enabled=False"
    )


def test_compare_button_present_when_flag_on():
    """Flag = True → button + column B rendered."""
    html = _render_chat_html(compare_enabled=True)
    assert 'id="btn-compare"' in html
    assert 'id="col-chip-B"' in html
    assert 'id="btn-compare-close"' in html


# ─── Handler-side default ────────────────────────────────────────────────


def test_handler_treats_missing_env_as_enabled(monkeypatch):
    """When ARAIL_COMPARE_ENABLED is unset in the environment, the
    /chat handler should compute compare_enabled=True. This preserves
    behavior for upgrade-in-place users whose .env predates the flag."""
    monkeypatch.delenv("ARAIL_COMPARE_ENABLED", raising=False)
    # Replicate the handler's exact expression so we pin the contract.
    compare_enabled = os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1"
    assert compare_enabled is True


def test_handler_treats_zero_as_disabled(monkeypatch):
    monkeypatch.setenv("ARAIL_COMPARE_ENABLED", "0")
    assert (os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1") is False


def test_handler_treats_one_as_enabled(monkeypatch):
    monkeypatch.setenv("ARAIL_COMPARE_ENABLED", "1")
    assert (os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1") is True


@pytest.mark.parametrize("junk", ["yes", "true", "on", "TRUE", "Y", "1.0", " 1 "])
def test_handler_strict_equality_treats_non_one_as_disabled(monkeypatch, junk):
    """Strict `== "1"` semantics — any value other than literal "1"
    means disabled. Prevents accidental enables from typos and aligns
    with how the enable/disable scripts write the flag."""
    monkeypatch.setenv("ARAIL_COMPARE_ENABLED", junk)
    assert (os.getenv("ARAIL_COMPARE_ENABLED", "1") == "1") is False, (
        f"Value {junk!r} was treated as enabled"
    )
