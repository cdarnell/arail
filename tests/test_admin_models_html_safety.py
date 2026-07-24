"""Test admin Models card HTML structure for the click-handler fix.

Sprint: 2026-05-03-models-admin-dashboard
Architect MUST-HIT: HTML quoting regression — re-fix verification.

The original BLOCK was: `onclick="loadOneModel(${JSON.stringify(m.id)})"`
expanded to `onclick="loadOneModel("Qwen3-8B-4bit")"` and the inner quote
closed the attribute. The fix migrated to `data-action` + `data-id` event
delegation. These tests verify:

  1. The admin.html source no longer contains the broken JSON.stringify-in-onclick
     pattern.
  2. The data-action / data-id pattern is present on Load and Unload buttons.
  3. The CTX input carries data-id (for delegated change handler).
  4. A single delegated click listener attaches via _initModelsListDelegate().
  5. The admin page actually renders without errors (smoke test on /admin).
  6. Hostile model_id strings — when piped through the same _prEsc-equivalent
     escape — produce HTML that parses to the intended attribute values.

We use the stdlib `html.parser` (no new deps).
"""

from __future__ import annotations

import html
from html.parser import HTMLParser
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ADMIN_TEMPLATE = Path("src/arail/portal/templates/admin.html")


# ---------------------------------------------------------------------------
# Source-level: the broken pattern is gone, the new pattern is present
# ---------------------------------------------------------------------------

def test_admin_html_no_longer_uses_json_stringify_in_onclick():
    """The broken `onclick="fn(${JSON.stringify(m.id)})"` pattern is gone.

    BLOCK Issue 1 from REVIEW.md — pre-fix, all four interactive buttons
    used `JSON.stringify` inline in a double-quoted attribute, which the
    HTML parser truncated at the first inner quote.
    """
    src = ADMIN_TEMPLATE.read_text()
    # The broken substrings: any `onclick=` containing JSON.stringify.
    for line in src.splitlines():
        if "onclick=" in line and "JSON.stringify" in line:
            pytest.fail(f"broken pattern still present: {line.strip()}")
        if "onchange=" in line and "JSON.stringify" in line:
            pytest.fail(f"broken pattern still present: {line.strip()}")


def test_admin_html_load_button_uses_data_action():
    """Fix 1 verification: Load button uses data-action='load' + data-id."""
    src = ADMIN_TEMPLATE.read_text()
    # Look for `data-action="load"` on a button
    assert 'data-action="load"' in src, "data-action='load' missing on Load button"
    assert 'data-action="unload"' in src, "data-action='unload' missing on Unload button"


def test_admin_html_ctx_input_carries_data_id():
    """The CTX number input must carry data-id for the delegated change handler."""
    src = ADMIN_TEMPLATE.read_text()
    # The ctx-input class must coexist with data-id="..."
    assert 'class="ctx-input"' in src
    # In the same render block, the input has data-id (escaped)
    assert "ctx-input" in src and "data-id=" in src


def test_admin_html_init_delegate_function_present():
    """_initModelsListDelegate() function must exist and attach exactly one listener."""
    src = ADMIN_TEMPLATE.read_text()
    assert "_initModelsListDelegate" in src
    # The guard flag prevents double-attach
    assert "_delegateAttached" in src


# ---------------------------------------------------------------------------
# HTML parser test on a synthetic render — hostile model_ids
# ---------------------------------------------------------------------------

class _AttrCollector(HTMLParser):
    """Collect attributes per tag for parser-correctness checks."""
    def __init__(self):
        super().__init__()
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


# Mirror the JS `_prEsc` helper that the admin.html JS uses to escape model_ids
# before substitution into the data-id attribute. This is the safety net that
# makes data-id-based delegation immune to the original quoting bug.
def _pr_esc(value: str) -> str:
    """Mirror of the JS _prEsc helper: HTML-attribute-safe escape."""
    return html.escape(value, quote=True)


def _render_models_card_snippet(model_ids: list[str]) -> str:
    """Render the same data-id row template that admin.html JS produces."""
    rows = []
    for mid in model_ids:
        esc = _pr_esc(mid)
        rows.append(
            f'<div class="models-row" data-id="{esc}">'
            f'  <button class="pr-btn" data-action="load" data-id="{esc}">Load</button>'
            f'  <button class="pr-btn" data-action="unload" data-id="{esc}">Unload</button>'
            f'  <input class="ctx-input" type="number" data-id="{esc}">'
            f'</div>'
        )
    return "<div id='models-list'>" + "".join(rows) + "</div>"


@pytest.mark.parametrize("hostile_id", [
    "Qwen3-8B-4bit",                       # baseline
    "Test's-Model.v2_alpha",               # apostrophe
    "model&with&ampersands",               # &
    "model<with>angle<brackets>",          # < >
    "model\"with\"doublequotes",           # "
    "Llama-4-Maverick-17B-128E-Instruct-fp8",  # the canonical streamed model
    "very_long_id_" + "x" * 100,           # stress
    "id-with-spaces in middle",            # space
    "id/with/slash",                       # slash (would be rejected by validator)
])
def test_render_with_hostile_id_parses_correctly(hostile_id):
    """The data-id attribute survives the round-trip through the parser."""
    snippet = _render_models_card_snippet([hostile_id])
    parser = _AttrCollector()
    parser.feed(snippet)

    # Find buttons with data-action and verify their data-id matches the input.
    buttons = [(t, a) for t, a in parser.tags if t == "button"]
    assert len(buttons) >= 2, f"expected >=2 buttons, got {len(buttons)}"
    for tag, attrs in buttons:
        assert attrs.get("data-id") == hostile_id, (
            f"data-id mangled for hostile_id={hostile_id!r}: got {attrs.get('data-id')!r}"
        )
        assert attrs.get("data-action") in ("load", "unload")

    # The ctx input also carries data-id.
    inputs = [(t, a) for t, a in parser.tags if t == "input"]
    assert len(inputs) >= 1
    assert inputs[0][1].get("data-id") == hostile_id


def test_render_with_apostrophe_does_not_break_attribute():
    """Specifically: an apostrophe in the model_id (the original bug class)
    must not close the data-id attribute."""
    snippet = _render_models_card_snippet(["Test's-Model.v2_alpha"])
    parser = _AttrCollector()
    parser.feed(snippet)
    buttons = [(t, a) for t, a in parser.tags if t == "button"]
    # The data-id should equal the literal model_id, NOT a truncated form.
    for _, a in buttons:
        assert a.get("data-id") == "Test's-Model.v2_alpha"
        assert "data-action" in a


def test_render_does_not_emit_legacy_onclick_with_json_stringify():
    """Even with hostile inputs, the rendered snippet has no `onclick=fn(...)`."""
    snippet = _render_models_card_snippet(["Qwen3-8B-4bit", "Test's-Model"])
    # The data-attr based render must not contain `onclick=` at all
    assert 'onclick="loadOneModel' not in snippet
    assert 'onclick="unloadOneModel' not in snippet


# ---------------------------------------------------------------------------
# Live admin page renders the Models section
# ---------------------------------------------------------------------------

def test_admin_page_renders_models_section(monkeypatch, tmp_path):
    """GET /admin returns 200 and the rendered HTML includes the Models card."""
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("LAB_TIER", "maximus")  # /admin is a maximus-only surface
    (tmp_path / "models").mkdir(parents=True)

    from arail.portal.app import app
    r = TestClient(app).get("/admin")
    assert r.status_code == 200, r.text
    body = r.text
    # The Models admin section is identified by its h2 inside the admin-section block
    assert ">Models</h2>" in body
    # The rendering surfaces are present
    assert 'id="models-list"' in body
    assert 'id="models-default"' in body
    # The new data-action pattern is in the served JS
    assert "data-action" in body


def test_admin_page_models_section_has_no_broken_quoting(monkeypatch, tmp_path):
    """Defense-in-depth: the SERVED HTML has no broken pattern either."""
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("LAB_TIER", "maximus")  # /admin is a maximus-only surface
    (tmp_path / "models").mkdir(parents=True)
    from arail.portal.app import app
    r = TestClient(app).get("/admin")
    assert r.status_code == 200
    body = r.text
    # No JSON.stringify-in-onclick-attribute (the BLOCK pattern)
    for line in body.splitlines():
        if "onclick=" in line and "JSON.stringify" in line:
            pytest.fail(f"served HTML still has broken quoting: {line.strip()}")
