"""DOM/structure + escaping assertions for _model_boot_banner.html.

The template is a standalone fragment (no {% extends %}, no Jinja
variables) so it renders cleanly with an empty context, same as
_airgap_modal.html's test convention (test_airgap_modal_dom.py).

Covers:
  - Required ids exist (strip, panel, both slot lists, confirm/not-now/
    fix/dismiss buttons, error box).
  - Every place the script writes model-derived text via innerHTML routes
    through the esc() helper first (source-level check — this is plain
    JS with no server round-trip, same convention
    test_aerollm_model_ready.py already uses for chat.html).
  - hf links always carry rel="noopener noreferrer" and target="_blank".
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

import jinja2

TEMPLATE_PATH = (
    Path(__file__).resolve().parent.parent
    / "src" / "arail" / "portal" / "templates" / "_model_boot_banner.html"
)


def _render() -> str:
    loader = jinja2.FileSystemLoader(str(TEMPLATE_PATH.parent))
    env = jinja2.Environment(loader=loader, autoescape=True)
    tmpl = env.get_template(TEMPLATE_PATH.name)
    return tmpl.render()


class _IDCollector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if "id" in attrs_dict:
            self.ids.add(attrs_dict["id"])


def test_template_renders_with_empty_context():
    html = _render()
    assert "<script>" in html


def test_required_ids_present():
    parser = _IDCollector()
    parser.feed(_render())
    required = {
        "model-boot-banner", "mbb-strip", "mbb-strip-text", "mbb-fix",
        "mbb-dismiss", "mbb-panel", "mbb-a-list", "mbb-b-list",
        "mbb-error", "mbb-not-now", "mbb-confirm",
    }
    missing = required - parser.ids
    assert not missing, f"missing required ids: {missing}"


def test_banner_and_panel_start_hidden():
    html = _render()
    banner_tag = re.search(r'<div id="model-boot-banner"[^>]*>', html).group(0)
    panel_tag = re.search(r'<div id="mbb-panel"[^>]*>', html).group(0)
    strip_tag = re.search(r'<div id="mbb-strip"[^>]*>', html).group(0)
    assert "hidden" in banner_tag
    assert "hidden" in panel_tag
    assert "hidden" in strip_tag


def test_source_uses_esc_helper_before_every_innerhtml_write():
    """Every `.innerHTML =` assignment in the script must build its string
    through esc() somewhere in the same statement, OR assign a value that
    is itself entirely composed of esc()-wrapped pieces plus static
    markup. We check the weaker, robust invariant: every innerHTML target
    line (or the statement it's part of) contains at least one esc(...)
    call, for every server/user-derived write. main.textContent (used for
    names) is exempt — textContent is inherently safe."""
    html = _render()
    script = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    # Grab each `.innerHTML = ...;` assignment (may span multiple source
    # lines — join and match up to the terminating semicolon).
    assignments = re.findall(r"\.innerHTML\s*=\s*(.+?);", script, re.DOTALL)
    assert assignments, "expected at least one .innerHTML assignment to check"
    for stmt in assignments:
        # Assignments that are pure static/reset strings (e.g. clearing to
        # '') carry no interpolation and don't need esc().
        if "esc(" not in stmt and "+" not in stmt:
            continue
        assert "esc(" in stmt, (
            f"innerHTML assignment concatenates data without esc(): {stmt!r}")


def test_hf_link_carries_safe_rel_and_target():
    html = _render()
    script = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert 'rel = \'noopener noreferrer\'' in script or 'rel="noopener noreferrer"' in script
    assert "target = '_blank'" in script or 'target="_blank"' in script


def test_fetch_boot_called_exactly_once_unconditionally_on_load():
    """No polling, no setInterval, no EventSource — the fetch-once
    contract this file's docstring commits to."""
    html = _render()
    script = html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
    assert "setInterval" not in script
    assert "EventSource" not in script
    # The unconditional bootstrap call at the end of the IIFE.
    assert re.search(r"fetchBoot\(false\);\s*\}\)\(\);", script)
