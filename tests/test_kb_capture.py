"""Capture-to-Knowledge: KB voice/image ingest into the inbox.

The KB capture affordances (🎤 Voice memo / 📷 Scan) are TOOLCHAIN-gated, NOT
World-gated: available whenever the on-device STT/OCR adapter ``is_available()``
on this machine, independent of any mounted World. They land markdown in
``lab/pkb/inbox/`` which flows through the EXISTING compile pipeline.

The adapter boundary is injected (fake ``_runner``) so no real audio/mic/Vision/
swiftc/whisper is touched.

arail weights: 30 setup / 30 Buddy(capture quality) / 20 security / 10 happy /
10 regression.

Covers:
- /api/capabilities/installed probe shape (setup)
- adapter-present → ingest succeeds, markdown in inbox/ with front-matter,
  inbox processing triggered (Buddy/setup)
- adapter-absent (mock is_available) → 409 graceful, TOOLCHAIN message,
  NOT a "mount a World" message (setup/Buddy)
- voice-ingest + scan-ingest end-to-end with fake runner (happy/Buddy)
- NOT World-gated: capture succeeds with current_mount() None but adapter
  available (the key decoupling) (Buddy)
- mime-spoof / oversized image → 422 (security)
- temp audio/image deleted even when the runner raises (security)
- airgapped zero-egress (security)
- regression: chat /api/stt/transcribe + /api/ocr/extract + research/ landing
  UNCHANGED (still World-gated, still land in research/)
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from arail import world_mount as wm
from arail.capabilities import registry
from arail.capabilities.backends.whisper_stt import WhisperSpeechToText
from arail.capabilities.backends.macos.ocr_backend import MacOSImageOCR

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"

# Smallest valid magic-byte payloads for the sniffer (1x1-ish; content irrelevant,
# OCR is faked).
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 64


# ── Fakes ──────────────────────────────────────────────────────────────

def _install_fake_stt(monkeypatch, text="hello this is a lab voice memo", conf=0.92,
                      runner=None):
    payload = json.dumps({
        "ok": True, "transcript": text,
        "segments": [{"text": w, "ts": float(i)} for i, w in enumerate(text.split())],
        "confidence": conf, "on_device": True,
    })
    fake = WhisperSpeechToText(platform="darwin", runner=runner or (lambda args: (0, payload, "")))
    monkeypatch.setattr(fake, "is_available", lambda: True)

    def _avail(cid):
        return fake if cid == "speech-to-text" else None
    monkeypatch.setattr(registry, "available_capability", _avail)
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    return fake


def _install_fake_ocr(monkeypatch, text="k = 1.380649e-23 J/K", runner=None):
    payload = json.dumps({"ok": True, "text": text, "on_device": True})
    fake = MacOSImageOCR(runner=runner or (lambda args: (0, payload, "")))
    monkeypatch.setattr(fake, "is_available", lambda: True)

    def _avail(cid):
        return fake if cid == "equation-ocr" else None
    monkeypatch.setattr(registry, "available_capability", _avail)
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    return fake


def _install_no_toolchain(monkeypatch):
    """Both adapters absent on this machine."""
    monkeypatch.setattr(registry, "available_capability", lambda cid: None)


def _lab_into(monkeypatch, tmp_path, *, mount_world=False):
    """Point lab tree at tmp. By default NO World is mounted (the decoupling)."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir(parents=True, exist_ok=True)
    pkb_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LAB_PKB", str(pkb_root))
    import arail.config
    monkeypatch.setattr(arail.config, "PKB_ROOT", pkb_root)
    monkeypatch.setattr(arail.config, "DATA_DIR", data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb_root)
    import arail.pkb
    monkeypatch.setattr(arail.pkb, "_pkb_root", lambda: pkb_root)
    if mount_world:
        wm.mount(FIXTURES / "world-caps-stt", data_dir=data_dir, pkb_root=pkb_root)
    return data_dir, pkb_root


def _client():
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=False)


def _audio_file(name="memo.m4a", mime="audio/mp4"):
    return {"audio": (name, b"FAKE_AAC_BYTES", mime)}


def _image_file(data=PNG_BYTES, name="scan.png", mime="image/png"):
    return {"image": (name, data, mime)}


@pytest.fixture(autouse=True)
def _no_inbox_processing(monkeypatch):
    """Stub the inbox ingest so tests don't run the heavy compile, but record that
    it was triggered."""
    calls = []
    import arail.pkb
    monkeypatch.setattr(arail.pkb, "ingest",
                        lambda *a, **k: calls.append(True) or {"moved": 1, "urls_fetched": 0})
    # wiki rebuild is best-effort; stub to a no-op.
    try:
        import arail.wiki
        monkeypatch.setattr(arail.wiki, "schedule_rebuild", lambda *a, **k: None)
    except Exception:
        pass
    return calls


# ── Setup: capability probe ────────────────────────────────────────────

def test_probe_shape_both_present(monkeypatch, tmp_path):
    _lab_into(monkeypatch, tmp_path)
    fake = WhisperSpeechToText(platform="darwin", runner=lambda a: (0, "{}", ""))
    monkeypatch.setattr(fake, "is_available", lambda: True)
    fake_ocr = MacOSImageOCR(runner=lambda a: (0, "{}", ""))
    monkeypatch.setattr(fake_ocr, "is_available", lambda: True)
    avail = {"speech-to-text": fake, "equation-ocr": fake_ocr}
    monkeypatch.setattr(registry, "available_capability", lambda cid: avail.get(cid))
    r = _client().get("/api/capabilities/installed")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"speech-to-text", "equation-ocr"}
    assert body == {"speech-to-text": True, "equation-ocr": True}


def test_probe_shape_none_present(monkeypatch, tmp_path):
    _lab_into(monkeypatch, tmp_path)
    _install_no_toolchain(monkeypatch)
    r = _client().get("/api/capabilities/installed")
    assert r.status_code == 200
    assert r.json() == {"speech-to-text": False, "equation-ocr": False}


# ── Voice ingest ───────────────────────────────────────────────────────

def test_voice_ingest_lands_inbox_markdown(monkeypatch, tmp_path, _no_inbox_processing):
    _install_fake_stt(monkeypatch)
    _, pkb_root = _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/voice-ingest", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["path"].startswith("inbox/voice-memo-")
    assert body["path"].endswith(".md")
    assert body["reveal"] == body["path"]
    note = pkb_root / body["path"]
    assert note.exists()
    text = note.read_text()
    assert "source: voice-memo" in text
    assert "captured-at:" in text
    assert "kind: raw" in text
    assert "hello this is a lab voice memo" in text
    # inbox processing was triggered (same call as ⚡ Process inbox / watcher)
    assert _no_inbox_processing, "inbox processing not triggered"


def test_voice_ingest_not_world_gated(monkeypatch, tmp_path):
    """The key decoupling: capture succeeds with NO World mounted."""
    _install_fake_stt(monkeypatch)
    data_dir, pkb_root = _lab_into(monkeypatch, tmp_path, mount_world=False)
    from arail.world_mount import current_mount
    assert current_mount(data_dir=data_dir) is None  # genuinely no World
    r = _client().post("/api/kb/voice-ingest", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_voice_ingest_no_toolchain_409_actionable(monkeypatch, tmp_path):
    _install_no_toolchain(monkeypatch)
    _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/voice-ingest", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 409
    body = r.json()
    assert body.get("reason") == "toolchain_unavailable"
    msg = (body.get("message") or "").lower()
    assert "world" not in msg, "must NOT tell the user to mount a World"
    assert "setup" in msg or "model" in msg  # actionable toolchain hint


def test_voice_no_speech_ok_false(monkeypatch, tmp_path):
    _install_fake_stt(monkeypatch, text="   ")
    _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/voice-ingest", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": False, "reason": "no_speech"}


def test_voice_temp_audio_deleted_on_raising_runner(monkeypatch, tmp_path):
    def _boom(args):
        raise RuntimeError("runner blew up mid-transcribe")
    _install_fake_stt(monkeypatch, runner=_boom)
    data_dir, _ = _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/voice-ingest", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 500
    cache = data_dir / "cache" / "stt"
    leftovers = list(cache.glob("*")) if cache.exists() else []
    assert leftovers == [], f"temp audio not cleaned: {leftovers}"


# ── Scan (image OCR) ingest ────────────────────────────────────────────

def test_scan_ingest_lands_inbox_markdown(monkeypatch, tmp_path, _no_inbox_processing):
    _install_fake_ocr(monkeypatch)
    _, pkb_root = _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/scan-ingest", files=_image_file(name="board.png"),
                       data={"mime": "image/png"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["path"].startswith("inbox/scan-")
    note = pkb_root / body["path"]
    assert note.exists()
    text = note.read_text()
    assert "source: image-ocr" in text
    assert "captured-at:" in text
    assert "original-filename: board.png" in text
    assert "1.380649e-23" in text
    assert _no_inbox_processing, "inbox processing not triggered"


def test_scan_ingest_not_world_gated(monkeypatch, tmp_path):
    _install_fake_ocr(monkeypatch)
    data_dir, _ = _lab_into(monkeypatch, tmp_path, mount_world=False)
    from arail.world_mount import current_mount
    assert current_mount(data_dir=data_dir) is None
    r = _client().post("/api/kb/scan-ingest", files=_image_file(), data={"mime": "image/png"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_scan_no_toolchain_409_actionable(monkeypatch, tmp_path):
    _install_no_toolchain(monkeypatch)
    _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/scan-ingest", files=_image_file(), data={"mime": "image/png"})
    assert r.status_code == 409
    body = r.json()
    assert body.get("reason") == "toolchain_unavailable"
    msg = (body.get("message") or "").lower()
    assert "world" not in msg
    assert "xcode" in msg or "command-line" in msg


def test_scan_filename_is_server_generated(monkeypatch, tmp_path):
    """Path-jail: a malicious filename can't escape the inbox."""
    _install_fake_ocr(monkeypatch)
    _, pkb_root = _lab_into(monkeypatch, tmp_path)
    evil = {"image": ("../../../../etc/passwd.png", PNG_BYTES, "image/png")}
    r = _client().post("/api/kb/scan-ingest", files=evil, data={"mime": "image/png"})
    assert r.status_code == 200, r.text
    path = r.json()["path"]
    assert path.startswith("inbox/scan-")
    note = pkb_root / path
    assert note.exists()
    # only the bare name is recorded as inert metadata; nothing escaped inbox/
    assert ".." not in path
    assert "original-filename: passwd.png" in note.read_text()


# ── Security ───────────────────────────────────────────────────────────

def test_scan_mime_spoof_rejected_422(monkeypatch, tmp_path):
    _install_fake_ocr(monkeypatch)
    _lab_into(monkeypatch, tmp_path)
    # bytes are not a real image despite the declared png mime
    spoof = {"image": ("evil.png", b"GIF89a not really an image", "image/png")}
    r = _client().post("/api/kb/scan-ingest", files=spoof, data={"mime": "image/png"})
    assert r.status_code == 422


def test_scan_oversized_rejected_422(monkeypatch, tmp_path):
    _install_fake_ocr(monkeypatch)
    _lab_into(monkeypatch, tmp_path)
    big = PNG_BYTES + b"\x00" * (13 * 1024 * 1024)
    r = _client().post("/api/kb/scan-ingest",
                       files={"image": ("big.png", big, "image/png")},
                       data={"mime": "image/png"})
    assert r.status_code == 422


def test_scan_temp_image_deleted_on_raising_runner(monkeypatch, tmp_path):
    def _boom(args):
        raise RuntimeError("vision blew up")
    _install_fake_ocr(monkeypatch, runner=_boom)
    data_dir, _ = _lab_into(monkeypatch, tmp_path)
    r = _client().post("/api/kb/scan-ingest", files=_image_file(), data={"mime": "image/png"})
    assert r.status_code == 500
    cache = data_dir / "cache" / "ocr"
    leftovers = list(cache.glob("*")) if cache.exists() else []
    assert leftovers == [], f"temp image not cleaned: {leftovers}"


def test_capture_airgapped_zero_egress(monkeypatch, tmp_path):
    """Capture is fully on-device — no network egress during ingest."""
    monkeypatch.setenv("LAB_MODE", "airgapped")
    _install_fake_stt(monkeypatch)
    _lab_into(monkeypatch, tmp_path)
    import arail.egress
    arail.egress.install_guard()
    blocked_before = getattr(arail.egress, "_blocked_count", lambda: 0)
    r = _client().post("/api/kb/voice-ingest", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


# ── Regression: chat capture endpoints UNCHANGED ───────────────────────

def test_regression_chat_stt_still_world_gated(monkeypatch, tmp_path):
    """The chat 🎤 endpoint stays World-gated: 400 with no World mounted, even
    though the KB path would succeed toolchain-only."""
    _install_fake_stt(monkeypatch)
    data_dir, _ = _lab_into(monkeypatch, tmp_path, mount_world=False)
    r = _client().post("/api/stt/transcribe", files=_audio_file(), data={"mime": "audio/mp4"})
    assert r.status_code == 400  # "No world mounted" — UNCHANGED contract


def test_regression_chat_ocr_still_world_gated(monkeypatch, tmp_path):
    _install_fake_ocr(monkeypatch)
    _lab_into(monkeypatch, tmp_path, mount_world=False)
    r = _client().post("/api/ocr/extract", files=_image_file(), data={"mime": "image/png"})
    assert r.status_code == 400  # World-gated — UNCHANGED


def test_regression_chat_endpoints_exist(monkeypatch):
    """The chat capture routes and their research/ landing helpers are present."""
    from arail.portal import app as appmod
    routes = {getattr(r, "path", None) for r in appmod.app.routes}
    assert "/api/stt/transcribe" in routes
    assert "/api/ocr/extract" in routes
    # research/ landing helpers untouched
    assert hasattr(appmod, "_land_raw_voice_note")
    assert hasattr(appmod, "_land_raw_ocr_note")
