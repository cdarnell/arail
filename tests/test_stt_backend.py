"""WhisperSpeechToText backend unit tests (injectable _runner; no live model).

The transcription boundary is the ``_runner`` callable; we inject a fake runner
returning known JSON (the SAME shape the old Apple helper emitted) so CI never
loads a model or shells afconvert. The real path (afconvert → base.en) is gated
behind ``@pytest.mark.live_stt`` and skipped by default.

Covers (Addendum A.8):
- error-code mapping in invoke() across the seam (kept from the Apple backend —
  the JSON contract is identical, so these survive the swap),
- is_available() availability (model present vs absent + airgapped),
- afconvert arg-list / 16 kHz-mono-WAV conversion,
- a real base.en transcription (live_stt),
- airgapped-graceful model_unavailable (no network, no crash),
- the WC-B Apple-symbol grep is clean over ALL of src/ (no exclude).
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import wave

import pytest

from arail.capabilities.backends.whisper_stt import WhisperSpeechToText
import arail.capabilities.backends.whisper_stt as ws
from arail.capabilities.backends.macos.audio_backend import MacOSAudioCapture
from arail.capabilities import CapabilityError, CapabilityUnavailable

AUDIO_DIR = pathlib.Path(__file__).parent / "fixtures" / "audio"


# ── invoke() error-code mapping across the seam (fake _runner) ─────────


def test_runner_success_maps_transcript():
    payload = json.dumps({
        "ok": True, "transcript": "hello world",
        "segments": [{"text": "hello", "ts": 0.0}],
        "confidence": 0.95, "on_device": True,
    })
    adapter = WhisperSpeechToText(runner=lambda args: (0, payload, ""))
    t = adapter.invoke(audio={"path": "/tmp/x.m4a"}, locale="en-US")
    assert t["text"] == "hello world"
    assert t["confidence"] == pytest.approx(0.95)
    assert t["on_device"] is True
    assert t["segments"][0]["text"] == "hello"


def test_no_speech_returns_empty_transcript():
    err = json.dumps({"ok": False, "error": "no_speech", "message": "Nothing heard."})
    adapter = WhisperSpeechToText(runner=lambda args: (3, "", err))
    t = adapter.invoke(audio={"path": "/tmp/x.m4a"})
    assert t["text"] == ""  # graceful, not an exception


def test_model_unavailable_raises_unavailable():
    err = json.dumps({"ok": False, "error": "model_unavailable", "message": "No model."})
    adapter = WhisperSpeechToText(runner=lambda args: (2, "", err))
    with pytest.raises(CapabilityUnavailable):
        adapter.invoke(audio={"path": "/tmp/x.m4a"})


def test_decode_failed_raises_error():
    err = json.dumps({"ok": False, "error": "decode_failed", "message": "bad m4a"})
    adapter = WhisperSpeechToText(runner=lambda args: (1, "", err))
    with pytest.raises(CapabilityError):
        adapter.invoke(audio={"path": "/tmp/x.m4a"})


def test_bad_runner_output_raises_error():
    adapter = WhisperSpeechToText(runner=lambda args: (0, "not json", ""))
    with pytest.raises(CapabilityError):
        adapter.invoke(audio={"path": "/tmp/x.m4a"})


# ── is_available(): model present vs absent + airgapped ────────────────


def test_backend_available_model_present(monkeypatch):
    monkeypatch.setattr(ws._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ws, "_whisper_importable", lambda: True)
    monkeypatch.setattr(ws, "_decode_available", lambda: True)
    monkeypatch.setattr(ws, "_model_present", lambda: True)
    monkeypatch.setattr(ws, "_is_airgapped", lambda: True)
    assert WhisperSpeechToText(platform="darwin").is_available() is True


def test_backend_unavailable_model_absent_airgapped(monkeypatch):
    monkeypatch.setattr(ws._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ws, "_whisper_importable", lambda: True)
    monkeypatch.setattr(ws, "_decode_available", lambda: True)
    monkeypatch.setattr(ws, "_model_present", lambda: False)
    monkeypatch.setattr(ws, "_is_airgapped", lambda: True)  # absent + airgapped → not fetchable
    assert WhisperSpeechToText(platform="darwin").is_available() is False


def test_backend_available_model_absent_but_fetchable(monkeypatch):
    """Absent but NOT airgapped → fetchable → available (lazy download on use)."""
    monkeypatch.setattr(ws._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ws, "_whisper_importable", lambda: True)
    monkeypatch.setattr(ws, "_decode_available", lambda: True)
    monkeypatch.setattr(ws, "_model_present", lambda: False)
    monkeypatch.setattr(ws, "_is_airgapped", lambda: False)
    assert WhisperSpeechToText(platform="darwin").is_available() is True


# ── airgapped-graceful model_unavailable (no network, no crash) ────────


def test_airgapped_graceful_unavailable(monkeypatch):
    """Model absent + airgapped → _ensure_model raises CapabilityUnavailable
    with an actionable message; the default runner surfaces it as model_unavailable.
    No network call, no crash."""
    monkeypatch.setattr(ws, "_model_present", lambda: False)
    monkeypatch.setattr(ws, "_is_airgapped", lambda: True)
    with pytest.raises(CapabilityUnavailable) as ei:
        ws._ensure_model()
    assert "model not installed" in ei.value.user_message.lower() \
        or "lab/models/whisper" in ei.value.user_message

    # And end-to-end through the real default runner (no model load attempted):
    adapter = WhisperSpeechToText()  # real _default_runner
    # afconvert would fail on a nonexistent file before model load; force the
    # decode to pass-through so we reach the airgapped model check.
    monkeypatch.setattr(ws, "_afconvert_to_wav", lambda i, o: None)
    with pytest.raises(CapabilityUnavailable):
        adapter.invoke(audio={"path": str(AUDIO_DIR / "missing.m4a")})


# ── afconvert conversion (live_stt: shells afconvert) ──────────────────


def _synthesize_wav(path: pathlib.Path, seconds: float = 1.0, rate: int = 44100):
    """Write a tiny non-16kHz WAV so afconvert has real work to do."""
    import struct, math
    nframes = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(
            struct.pack("<h", int(3000 * math.sin(2 * math.pi * 220 * n / rate)))
            for n in range(nframes)
        )
        w.writeframes(frames)


@pytest.mark.live_stt
def test_afconvert_conversion(tmp_path):
    import shutil
    if shutil.which("afconvert") is None:
        pytest.skip("afconvert not present (non-macOS)")
    src = tmp_path / "in.wav"
    out = tmp_path / "out.wav"
    _synthesize_wav(src, seconds=0.5, rate=44100)
    err = ws._afconvert_to_wav(src, out)
    assert err is None, f"afconvert failed: {err}"
    with wave.open(str(out), "rb") as w:
        assert w.getframerate() == 16000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2  # 16-bit


# ── real transcription (live_stt: loads base.en) ───────────────────────


@pytest.mark.live_stt
def test_real_transcription(tmp_path):
    """Standing WC-A.4 proof: run real Whisper on a synthesized speech WAV and
    assert a non-empty transcript containing an expected token."""
    import shutil
    if shutil.which("say") is None or shutil.which("afconvert") is None:
        pytest.skip("say/afconvert not present")
    if not ws._whisper_importable():
        pytest.skip("faster_whisper not importable")
    if not ws._model_present() and ws._is_airgapped():
        pytest.skip("base.en model absent and airgapped")
    m4a = tmp_path / "hello.m4a"
    subprocess.run(["say", "-o", str(m4a), "--data-format=aac",
                    "hello this is a real local whisper transcription test"],
                   check=True, timeout=30)
    adapter = WhisperSpeechToText()  # real default runner
    t = adapter.invoke(audio={"path": str(m4a)})
    assert t["text"].strip(), "expected a non-empty transcript"
    assert "hello" in t["text"].lower()


# ── audio capture: format gating (unchanged seam) ──────────────────────


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


# ── WC-B: no Apple symbols anywhere in src/ ────────────────────────────


def test_no_apple_symbols_anywhere():
    repo = pathlib.Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        ["grep", "-rEn", r"AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b|swiftc|xcrun", "src/"],
        cwd=repo, capture_output=True, text=True,
    )
    assert proc.returncode != 0, f"Apple symbols leaked:\n{proc.stdout}"
