"""Chat mic affordance gating (WC-A surface). DOM-level; no real mic.

The mic button is gated on a mounted World resolving speech-to-text=available.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from arail import world_mount as wm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
CAPS_STT = FIXTURES / "world-caps-stt"


def _client():
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False)


def test_mic_disabled_when_no_world(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    html = _client().get("/chat").text
    assert 'id="mic-btn"' in html
    assert 'data-stt-available="false"' in html
    # disabled attribute present on the button
    assert "disabled" in html.split('id="mic-btn"', 1)[1].split(">", 1)[0]


def test_mic_enabled_when_stt_available(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb_root)
    from arail.capabilities import registry
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    # ensure stt is_available: needs xcrun; force the macOS adapter available.
    import arail.capabilities.backends.macos.stt_backend as stt
    monkeypatch.setattr(stt.MacOSSpeechToText, "is_available", lambda self: True)
    wm.mount(CAPS_STT, data_dir=data_dir, pkb_root=pkb_root, env_path=tmp_path / ".env")

    html = _client().get("/chat").text
    assert 'data-stt-available="true"' in html
    # the mic button is NOT disabled
    seg = html.split('id="mic-btn"', 1)[1].split(">", 1)[0]
    assert "disabled" not in seg
