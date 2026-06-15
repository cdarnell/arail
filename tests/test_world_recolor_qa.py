"""QA adversarial probes for the UI-recolor middleware (sprint 2026-06-14).

Focus, in priority order:
  1. SSE / streaming is NOT broken by the body-buffering middleware
     (gate-before-drain; live incremental flush preserved; ndjson untouched).
  2. FileResponse / download integrity (not buffered into one blob, not
     corrupted, content-type preserved).
  3. Re-seal integrity: edited bundles still mount AND a tampered face still
     fails verify_seal (the re-seal did not disable the check).
  4. Content-Length correctness after rewrite (no truncation).

These ADD coverage; they do not weaken existing tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse, Response

from arail import world_mount as wm
from arail.portal import app as portal_app
from arail.portal.app import inject_ui_theme

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
MARK = 'id="ui-theme-vars"'


def _client():
    return TestClient(portal_app.app)


# ════════════ 1. SSE / STREAMING — THE KEY SCRUTINY ════════════

class _FakeRequest:
    pass


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_sse_response_is_gated_before_drain():
    """An SSE (text/event-stream) StreamingResponse must be returned BY THE SAME
    object — never drained/buffered. We prove the middleware returns the *exact*
    StreamingResponse instance it received, so the body_iterator is still live
    and flushes incrementally. If the middleware drained first, the returned
    object would be a plain buffered Response (BLOCKER)."""
    flushed = []

    async def gen():
        for i in range(3):
            flushed.append(i)
            yield f"data: {i}\n\n".encode()

    sse = StreamingResponse(gen(), media_type="text/event-stream")

    async def call_next(_req):
        return sse

    out = _run(inject_ui_theme(_FakeRequest(), call_next))
    # Same object → iterator untouched → live streaming preserved.
    assert out is sse, "SSE response was replaced/buffered by the middleware"
    # The generator must not have been consumed yet (nothing flushed at gate time).
    assert flushed == [], "middleware drained the SSE generator (live flush broken)"


def test_ndjson_stream_not_buffered():
    """application/x-ndjson StreamingResponse is likewise passed through untouched."""
    async def gen():
        yield b'{"a":1}\n'
        yield b'{"a":2}\n'

    sr = StreamingResponse(gen(), media_type="application/x-ndjson")

    async def call_next(_req):
        return sr

    out = _run(inject_ui_theme(_FakeRequest(), call_next))
    assert out is sr


def test_real_sse_route_streams_live():
    """End-to-end: the real /api/activity/stream SSE route still works through the
    full middleware stack and is not collected into one buffer at the end."""
    from arail.portal import app as pa
    # Publish one event, then read the stream with a timeout so we don't block
    # on the infinite subscribe loop.
    with _client() as c:
        # stream=True so we read incrementally rather than waiting for EOF.
        with c.stream("GET", "/api/activity/stream") as r:
            assert r.status_code == 200
            assert "text/event-stream" in r.headers.get("content-type", "")
            assert MARK not in (r.headers.get("content-type", ""))
            # Emit an event from another thread and confirm we receive it live.
            import threading, time
            def _emit():
                time.sleep(0.05)
                try:
                    pa.activity_log.emit("qa_probe", "live")
                except Exception:
                    pass
            threading.Thread(target=_emit, daemon=True).start()
            got = None
            for line in r.iter_lines():
                if "qa_probe" in line:
                    got = line
                    break
            assert got is not None, "did not receive a live SSE event incrementally"


# ════════════ 2. FILE / DOWNLOAD INTEGRITY ════════════

def test_static_binary_not_corrupted():
    """Static assets are served by a separate StaticFiles mount; confirm bytes are
    byte-identical to source and not rewritten."""
    src = pathlib.Path(portal_app.__file__).parent / "static" / "style.css"
    r = _client().get("/static/style.css")
    assert r.status_code == 200
    assert r.content == src.read_bytes(), "static asset corrupted in transit"
    assert MARK not in r.text


def test_html_rewrite_content_length_consistent():
    """After injection, Content-Length (if present) must equal the actual body
    length — a stale length truncates the page. TestClient/httpx would itself
    error on a mismatch, but assert explicitly."""
    r = _client().get("/")
    cl = r.headers.get("content-length")
    assert MARK in r.text  # injection happened
    if cl is not None:
        assert int(cl) == len(r.content), "Content-Length != body length after rewrite"


# ════════════ 3. RE-SEAL INTEGRITY ════════════

EDITED = ["physics", "world-caps-both", "world-caps-stt"]


@pytest.mark.parametrize("bundle", EDITED)
def test_edited_bundle_reseal_matches(bundle):
    """Each re-sealed bundle's manifest.files['face.json'] == sha256(face.json)."""
    bdir = FIXTURES / bundle
    manifest = json.loads((bdir / "manifest.json").read_text())
    expected = manifest["files"]["face.json"]
    actual = hashlib.sha256((bdir / "face.json").read_bytes()).hexdigest()
    assert actual == expected, f"{bundle} face.json not re-sealed"


@pytest.mark.parametrize("bundle", EDITED)
def test_edited_bundle_verifies_clean(bundle):
    """verify_seal passes on each edited bundle (no SealMismatch)."""
    from arail.world_mount import load_bundle, verify_seal
    b = load_bundle(FIXTURES / bundle)
    res = verify_seal(b)
    assert res.ok, f"{bundle} failed seal: {res.user_message}"


@pytest.mark.parametrize("bundle", EDITED)
def test_tampered_face_still_fails(bundle, tmp_path):
    """The re-seal did NOT disable the check: corrupting face.json (without
    re-sealing) must make verify_seal FAIL. Proves integrity still enforced."""
    import shutil
    from arail.world_mount import load_bundle, verify_seal
    work = tmp_path / bundle
    shutil.copytree(FIXTURES / bundle, work)
    face = work / "face.json"
    data = json.loads(face.read_text())
    data["palette_hint"] = "TAMPERED-no-reseal"
    face.write_text(json.dumps(data))
    b = load_bundle(work)
    res = verify_seal(b)
    assert not res.ok, f"{bundle}: tampered face.json was NOT caught by verify_seal"
    assert "face.json" in res.user_message
