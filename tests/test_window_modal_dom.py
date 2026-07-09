"""DOM assertions for _window_modal.html + the base.html global-UI hoist.

- The window modal fragment renders standalone with the expected ids and
  a three-button data-window segmented control (data-window, NOT
  data-target, so the airgap delegated listener can't cross-fire).
- base.html includes both modals + nav.js exactly once (global_ui block),
  and no child template includes them anymore (the pre-hoist duplication
  was why the airgapped pill was dead on chat and a dozen other pages).
"""

from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path

import jinja2

TEMPLATES = Path(__file__).parent.parent / "src" / "arail" / "portal" / "templates"


def _render_fragment(name: str) -> str:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATES)), autoescape=True
    )
    return env.get_template(name).render()


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.data_windows: list[str] = []
        self.data_targets: list[str] = []

    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if "id" in d:
            self.ids.add(d["id"])
        if tag == "button" and "data-window" in d:
            self.data_windows.append(d["data-window"])
        if tag == "button" and "data-target" in d:
            self.data_targets.append(d["data-target"])


def test_window_modal_structure():
    c = _Collector()
    c.feed(_render_fragment("_window_modal.html"))
    assert {"window-backdrop", "window-mode-pill", "window-hours-active",
            "window-hours-heavy", "window-override-status",
            "window-toggle-segmented", "window-toggle-error"} <= c.ids
    assert sorted(c.data_windows) == ["", "active", "heavy"]
    assert c.data_targets == []  # never data-target — airgap listener owns that


def test_base_html_hoists_global_ui_once():
    base = (TEMPLATES / "base.html").read_text()
    assert base.count('_airgap_modal.html') == 1
    assert base.count('_window_modal.html') == 1
    assert base.count('/static/nav.js') >= 1


def test_no_child_template_duplicates_global_ui():
    for path in TEMPLATES.rglob("*.html"):
        if path.name in ("base.html", "_airgap_modal.html", "_window_modal.html"):
            continue
        text = path.read_text()
        assert "_airgap_modal.html" not in text, f"{path.name} still includes the airgap modal"
        assert "_window_modal.html" not in text, f"{path.name} still includes the window modal"
        assert 'src="/static/nav.js"' not in text, f"{path.name} still loads nav.js"
