"""Client-behavior tests for welcome.html's Step-3 World picker (T13-T16).

sprints/2026-07-25-first-impression/ARCHITECTURE.md, Test strategy §"Client-
behavior tests" — following the same Node JS-render harness pattern as
test_qa_js_render_cloud_dropdown.py: the portal has no jsdom/jest/vitest
harness, so this shells out to Node against a real DOM shim + scripted
fetch(), running the ACTUAL showWorldStep()/renderConceptStrip()/
renderCatalogUnavailable()/renderNoWorldsFound() extracted out of the live
welcome.html — not a reimplementation.

Covers:
  T13 — catalog fetch 500 / empty worlds → honest failure state, no goHome() (F7)
  T14 — select 409 → message shown verbatim, grid re-enabled, no goHome() (F8)
  T15 — select 200 → exactly one goHome() call (F9's success path)
  T16 — World-supplied XSS payloads render as literal text, no <script> spawned (F13)

This test shells out to Node and self-skips if Node is unavailable.
"""

from __future__ import annotations

import os
import shutil
import subprocess

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_HARNESS = os.path.join(_REPO_ROOT, "tests", "js", "world_step_harness.mjs")


@pytest.mark.skipif(shutil.which("node") is None, reason="node not available for JS-render test")
def test_js_render_world_step_harness():
    """Run the Node JS-render harness for welcome.html's World-step (T13-T16)."""
    assert os.path.exists(_HARNESS), f"harness missing: {_HARNESS}"
    proc = subprocess.run(
        ["node", _HARNESS],
        capture_output=True, text=True, timeout=60,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    assert proc.returncode == 0, f"JS-render harness failed:\n{out}"
    assert "world-step JS-render assertions passed" in out, f"unexpected harness output:\n{out}"
