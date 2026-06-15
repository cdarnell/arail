"""Chat OCR affordance gating (WC-A surface). DOM-level; no real Vision.

The 📷 button is gated on a mounted World resolving equation-ocr=available,
exactly like the mic is gated on speech-to-text.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from arail import world_mount as wm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
CAPS_BOTH = FIXTURES / "world-caps-both"


def _client():
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False)


def test_ocr_disabled_when_no_world(monkeypatch, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    html = _client().get("/chat").text
    assert 'id="ocr-btn"' in html
    assert 'data-ocr-available="false"' in html
    assert "disabled" in html.split('id="ocr-btn"', 1)[1].split(">", 1)[0]


def test_ocr_enabled_when_available(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb_root)
    from arail.capabilities import registry
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "darwin")
    import arail.capabilities.backends.macos.ocr_backend as ob
    monkeypatch.setattr(ob.MacOSImageOCR, "is_available", lambda self: True)
    wm.mount(CAPS_BOTH, data_dir=data_dir, pkb_root=pkb_root)

    html = _client().get("/chat").text
    assert 'data-ocr-available="true"' in html
    seg = html.split('id="ocr-btn"', 1)[1].split(">", 1)[0]
    assert "disabled" not in seg
    # the upload/paste/drop handler is wired to the OCR endpoint.
    assert "/api/ocr/extract" in html
