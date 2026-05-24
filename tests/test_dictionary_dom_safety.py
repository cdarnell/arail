"""Static XSS guard: dictionary.js renders untrusted model output safely.

The dictionary renders model-generated term text. Per the F8 rule (see
docs_hub.html), all such text MUST be written with textContent /
createElement — never innerHTML. This test fails if a future edit
reintroduces an innerHTML assignment, which would open an XSS hole.
"""

from __future__ import annotations

import re
from pathlib import Path

JS = Path(__file__).resolve().parents[1] / "src/arail/portal/static/dictionary.js"


def test_dictionary_js_exists():
    assert JS.exists()


def test_no_innerhtml_assignment():
    src = JS.read_text()
    # Match `.innerHTML =` (with optional whitespace), the dangerous sink.
    assert not re.search(r"\.innerHTML\s*=", src), "dictionary.js must not assign innerHTML"
    assert "outerHTML" not in src
    assert "insertAdjacentHTML" not in src


def test_uses_textcontent():
    src = JS.read_text()
    assert "textContent" in src, "dictionary.js should render via textContent"
