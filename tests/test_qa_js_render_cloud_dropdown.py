"""QA carryover #1 — JS-render assertion for the cloud dropdown.

The re-review (REVIEW.md loop 2, carryover 1) flagged that B1 has a server-
contract test but no JS-EXECUTION assertion that cloud gallery.catalog entries
actually paint cards, and that the F-RACE seq-guard wasn't exercised by running
the real JS.

The portal has NO jsdom / jest / vitest harness (chat.legacy.html is a Jinja
template with an inline <script>; the only package.json is the separate
knowledge-canvas React app, and jsdom is not installed). Per the carryover
instruction ("if the repo has no JS test harness, document that and cover via
the closest available means"), we run a Node harness
(tests/js/cloud_render_harness.mjs) that:

  - extracts the REAL escapeHtml() from chat.legacy.html,
  - re-runs the cloud-render + seq-guard logic byte-faithfully against a DOM shim,
  - asserts (B1) catalog entries paint cards, (F-RACE) flip A->B with A resolving
    last shows B, and (XSS) a malicious model id is escaped before DOM insertion.

This test shells out to Node and self-skips if Node is unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HARNESS = os.path.join(_REPO_ROOT, "tests", "js", "cloud_render_harness.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available for JS-render test")
def test_js_render_cloud_dropdown_harness():
    """Run the Node JS-render harness. Exit 0 = all JS assertions passed.

    Covers carryover #1: B1 cards paint from gallery.catalog, F-RACE seq-guard,
    and XSS escaping in the actual rendered DOM string.
    """
    assert os.path.exists(_HARNESS), f"harness missing: {_HARNESS}"
    proc = subprocess.run(
        ["node", _HARNESS],
        capture_output=True, text=True, timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"JS-render harness failed:\n{out}"
    assert "JS-render assertions passed" in out, f"unexpected harness output:\n{out}"
