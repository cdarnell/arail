"""DOM assertions for _airgap_modal.html — segmented control structure.

Sprint 2026-05-14-airgap-onetap-toggle — ARCHITECTURE.md §test strategy
"Happy / UX (10%)".

Renders the Jinja2 template with html.parser and asserts:
  - #airgap-toggle-segmented exists with two data-target buttons.
  - Removed elements no longer exist: #airgap-toggle-confirm,
    #airgap-toggle-confirm-btn, #airgap-toggle-cancel-btn.
  - #airgap-toggle-bind-warning still exists (kept per spec).
  - #airgap-toggle-error still exists (kept per spec).
  - Subprocess staleness note is present in the template text.

Note: _airgap_modal.html is a standalone fragment (no {% extends %});
      it renders cleanly with Jinja2 directly.
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import jinja2
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEMPLATE_PATH = (
    Path(__file__).parent.parent
    / "src" / "arail" / "portal" / "templates" / "_airgap_modal.html"
)


def _render() -> str:
    """Render _airgap_modal.html with an empty context (no variables needed)."""
    loader = jinja2.FileSystemLoader(str(TEMPLATE_PATH.parent))
    env = jinja2.Environment(loader=loader, autoescape=True)
    tmpl = env.get_template(TEMPLATE_PATH.name)
    return tmpl.render()


class _IDCollector(HTMLParser):
    """Collect all id= attributes and button text into a searchable structure."""

    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.data_targets: list[str] = []   # data-target= values
        self.text_chunks: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if "id" in attrs_dict:
            self.ids.add(attrs_dict["id"])
        if "data-target" in attrs_dict:
            self.data_targets.append(attrs_dict["data-target"])

    def handle_data(self, data):
        stripped = data.strip()
        if stripped:
            self.text_chunks.append(stripped)


def _parse(html: str) -> _IDCollector:
    collector = _IDCollector()
    collector.feed(html)
    return collector


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAirgapModalDOM:
    def test_modal_renders_segmented_control(self):
        """#airgap-toggle-segmented exists with two data-target buttons."""
        html = _render()
        doc = _parse(html)

        assert "airgap-toggle-segmented" in doc.ids, (
            "#airgap-toggle-segmented not found in rendered template"
        )
        # Two halves: airgapped and hybrid.
        assert "airgapped" in doc.data_targets, (
            "data-target='airgapped' button not found"
        )
        assert "hybrid" in doc.data_targets, (
            "data-target='hybrid' button not found"
        )

    def test_modal_no_confirm_panel(self):
        """Removed elements are absent: #airgap-toggle-confirm,
        #airgap-toggle-confirm-btn, #airgap-toggle-cancel-btn."""
        html = _render()
        doc = _parse(html)

        assert "airgap-toggle-confirm" not in doc.ids, (
            "#airgap-toggle-confirm still present (should be removed)"
        )
        assert "airgap-toggle-confirm-btn" not in doc.ids, (
            "#airgap-toggle-confirm-btn still present (should be removed)"
        )
        assert "airgap-toggle-cancel-btn" not in doc.ids, (
            "#airgap-toggle-cancel-btn still present (should be removed)"
        )

    def test_modal_no_old_toggle_btn(self):
        """#airgap-toggle-btn (the old single-button) is absent."""
        html = _render()
        doc = _parse(html)
        assert "airgap-toggle-btn" not in doc.ids, (
            "#airgap-toggle-btn still present (should be removed)"
        )

    def test_modal_keeps_bind_warning_and_error(self):
        """#airgap-toggle-bind-warning and #airgap-toggle-error are preserved."""
        html = _render()
        doc = _parse(html)

        assert "airgap-toggle-bind-warning" in doc.ids, (
            "#airgap-toggle-bind-warning missing — it must be kept"
        )
        assert "airgap-toggle-error" in doc.ids, (
            "#airgap-toggle-error missing — it must be kept"
        )

    def test_modal_subprocess_staleness_note_present(self):
        """Subprocess staleness note is in the rendered HTML."""
        html = _render()
        # Check for key phrases from the spec note.
        assert "LAB_MODE" in html, "LAB_MODE not found in template"
        assert "restart" in html.lower(), (
            "Subprocess restart note not found in template"
        )

    def test_modal_no_countdown_text(self):
        """No countdown copy ('Confirm (3)') remains in the template."""
        html = _render()
        assert "Confirm (3)" not in html, (
            "'Confirm (3)' countdown text still present in template"
        )
