"""MacOSSpeechToText backend unit tests (injectable _runner; no live mic).

The Apple Speech boundary is the subprocess; we inject a fake runner returning
known JSON so CI never invokes the real helper. The real-compile path is gated
behind @pytest.mark.live_mic and skipped by default.
"""

from __future__ import annotations

import json
import shutil

import pytest

from arail.capabilities.backends.macos.stt_backend import MacOSSpeechToText
from arail.capabilities.backends.macos.audio_backend import MacOSAudioCapture
from arail.capabilities import CapabilityError, CapabilityUnavailable


def _fake_helper_present(adapter, monkeypatch):
    """Bypass _ensure_helper compilation by returning a fake binary path."""
    import arail.capabilities.backends.macos.stt_backend as mod
    monkeypatch.setattr(MacOSSpeechToText, "_ensure_helper", lambda self: mod.Path("/fake/arail-stt"))


def test_runner_success_maps_transcript(monkeypatch):
    payload = json.dumps({
        "ok": True, "transcript": "hello world",
        "segments": [{"text": "hello", "ts": 0.0}],
        "confidence": 0.95, "on_device": True,
    })
    adapter = MacOSSpeechToText(runner=lambda args: (0, payload, ""))
    _fake_helper_present(adapter, monkeypatch)
    t = adapter.invoke(audio={"path": "/tmp/x.m4a"}, locale="en-US")
    assert t["text"] == "hello world"
    assert t["confidence"] == pytest.approx(0.95)
    assert t["on_device"] is True
    assert t["segments"][0]["text"] == "hello"


def test_no_speech_returns_empty_transcript(monkeypatch):
    err = json.dumps({"ok": False, "error": "no_speech", "message": "Nothing heard."})
    adapter = MacOSSpeechToText(runner=lambda args: (3, "", err))
    _fake_helper_present(adapter, monkeypatch)
    t = adapter.invoke(audio={"path": "/tmp/x.m4a"})
    assert t["text"] == ""  # graceful, not an exception


def test_permission_denied_raises_unavailable(monkeypatch):
    err = json.dumps({"ok": False, "error": "permission_denied", "message": "Enable it in Settings."})
    adapter = MacOSSpeechToText(runner=lambda args: (2, "", err))
    _fake_helper_present(adapter, monkeypatch)
    with pytest.raises(CapabilityUnavailable) as ei:
        adapter.invoke(audio={"path": "/tmp/x.m4a"})
    assert "Settings" in ei.value.user_message


def test_model_unavailable_raises_unavailable(monkeypatch):
    err = json.dumps({"ok": False, "error": "model_unavailable", "message": "No model."})
    adapter = MacOSSpeechToText(runner=lambda args: (2, "", err))
    _fake_helper_present(adapter, monkeypatch)
    with pytest.raises(CapabilityUnavailable):
        adapter.invoke(audio={"path": "/tmp/x.m4a"})


def test_decode_failed_raises_error(monkeypatch):
    adapter = MacOSSpeechToText(runner=lambda args: (0, "not json", ""))
    _fake_helper_present(adapter, monkeypatch)
    with pytest.raises(CapabilityError):
        adapter.invoke(audio={"path": "/tmp/x.m4a"})


def test_ensure_helper_missing_clt_raises(monkeypatch, tmp_path):
    adapter = MacOSSpeechToText(runner=lambda args: (0, "{}", ""))
    import arail.capabilities.backends.macos.stt_backend as mod
    monkeypatch.setattr(mod, "_bin_dir", lambda: tmp_path)
    monkeypatch.setattr(mod.shutil, "which", lambda _n: None)
    with pytest.raises(CapabilityUnavailable) as ei:
        adapter._ensure_helper()
    assert "xcode-select" in ei.value.user_message


# ── audio capture: format gating ───────────────────────────────────────


def test_audio_rejects_webm():
    cap = MacOSAudioCapture()
    with pytest.raises(CapabilityError) as ei:
        cap.invoke(audio_bytes=b"x", mime="audio/webm;codecs=opus")
    assert "Safari" in ei.value.user_message


def test_audio_materializes_m4a(tmp_path, monkeypatch):
    import arail.capabilities.backends.macos.audio_backend as mod
    monkeypatch.setattr(mod, "_cache_dir", lambda: tmp_path)
    cap = MacOSAudioCapture()
    art = cap.invoke(audio_bytes=b"FAKEAAC", mime="audio/mp4")
    assert art["path"].suffix == ".m4a"
    assert art["path"].read_bytes() == b"FAKEAAC"
    assert art["mime"] == "audio/mp4"


# ── live compile (skipped in CI) ───────────────────────────────────────


@pytest.mark.live_mic
def test_helper_compiles_once(tmp_path, monkeypatch):
    if shutil.which("xcrun") is None:
        pytest.skip("xcrun not present")
    import arail.capabilities.backends.macos.stt_backend as mod
    monkeypatch.setattr(mod, "_bin_dir", lambda: tmp_path)
    adapter = MacOSSpeechToText()
    binary = adapter._ensure_helper()
    assert binary.exists()
    # second call is a no-op (cached)
    assert adapter._ensure_helper() == binary
