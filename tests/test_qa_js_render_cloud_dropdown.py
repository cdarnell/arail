"""QA carryover #1 — JS-render assertion for the chat model picker (repointed 2026-07-21).

The re-review (REVIEW.md loop 2, carryover 1) flagged that B1 had a server-
contract test but no JS-EXECUTION assertion that rendering actually escapes a
malicious model id, and that the F-RACE seq-guard wasn't exercised by running
the real JS.

The portal has NO jsdom / jest / vitest harness (chat.html is a Jinja template
with an inline <script>; the only package.json is the separate knowledge-canvas
React app, and jsdom is not installed). Per the carryover instruction ("if the
repo has no JS test harness, document that and cover via the closest available
means"), we run a Node harness (tests/js/cloud_render_harness.mjs) that:

  - extracts the REAL escapeHtml() / fitClass() / makeOpt() from the live
    chat.html,
  - runs the real makeOpt() (the picker-row renderer shared by every local +
    deep model entry) against malicious ids/runtimes through a DOM shim,
  - asserts (XSS) the payload is escaped before it reaches the element's
    innerHTML, and that an ordinary id still renders normally.

Originally this harness modeled chat.legacy.html's per-provider "cloud card"
grid (fetched via GET /api/chat/models?provider=<p>) and its F-RACE seq-guard.
chat.legacy.html was deleted as dead code (no route) in c3c401a
(portal-design-v2, 2026-07-07); the live chat.html has no per-provider catalog
fetch/render path at all (the Compute Source pivot only flips
State.activeSource), so that grid and its seq-guard no longer have a live
counterpart — this harness now pins makeOpt() instead, which is the render
path that does still exist and carries the same escaping obligation.

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

    Covers carryover #1: XSS escaping of a malicious model id/runtime in the
    actual rendered DOM string, via the real makeOpt() extracted from the
    live chat.html (not a reimplementation).
    """
    assert os.path.exists(_HARNESS), f"harness missing: {_HARNESS}"
    proc = subprocess.run(
        ["node", _HARNESS],
        capture_output=True, text=True, timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"JS-render harness failed:\n{out}"
    assert "JS-render assertions passed" in out, f"unexpected harness output:\n{out}"
