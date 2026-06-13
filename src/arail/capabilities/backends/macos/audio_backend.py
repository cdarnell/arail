"""macOS audio capture adapter.

Capture happens in the BROWSER (getUserMedia/MediaRecorder); this adapter's job
is validation + materialization, not device access. It writes the posted bytes
to a temp file under ``lab/data/cache/stt/<uuid>.<ext>`` and rejects mime types
Apple's AVFoundation cannot decode (webm/opus → unsupported_audio). A future
native CoreAudio capture impl slots in here without changing callers.
"""

from __future__ import annotations

import platform
import uuid
from pathlib import Path
from typing import Any, Dict

from ...adapter import AudioCaptureAdapter
from ...errors import CapabilityError
from ... import registry

# mime → file extension. AVFoundation decodes m4a/aac/wav/flac natively; it does
# NOT decode webm/opus (confirmed in the spike), so we reject those.
_MIME_EXT: Dict[str, str] = {
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/aac": ".aac",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/flac": ".flac",
}

_UNSUPPORTED = {"audio/webm", "audio/ogg", "audio/opus"}


def _cache_dir() -> Path:
    from arail.config import DATA_DIR
    d = Path(DATA_DIR) / "cache" / "stt"
    d.mkdir(parents=True, exist_ok=True)
    return d


class MacOSAudioCapture(AudioCaptureAdapter):
    platform = "darwin"
    purpose = "Materialize browser-captured audio for on-device transcription."

    def is_available(self) -> bool:
        return platform.system().lower() == "darwin"

    def invoke(self, **kwargs: Any) -> Dict[str, Any]:
        audio_bytes: bytes = kwargs["audio_bytes"]
        mime: str = (kwargs.get("mime") or "").split(";", 1)[0].strip().lower()

        if mime in _UNSUPPORTED or mime.startswith("audio/webm") or mime.startswith("audio/ogg"):
            raise CapabilityError(
                f"unsupported_audio: {mime}",
                user_message=(
                    "This browser recorded an audio format ARAIL can't transcribe "
                    "on-device yet (webm/opus). Use Safari for voice notes in v1."
                ),
            )
        ext = _MIME_EXT.get(mime)
        if ext is None:
            raise CapabilityError(
                f"unsupported_audio: {mime}",
                user_message=(
                    f"Unsupported audio type '{mime or 'unknown'}'. "
                    "Use Safari (audio/mp4) for voice notes in v1."
                ),
            )
        if not audio_bytes:
            raise CapabilityError(
                "unsupported_audio: empty",
                user_message="No audio was received. Try recording again.",
            )

        path = _cache_dir() / f"{uuid.uuid4().hex}{ext}"
        path.write_bytes(audio_bytes)
        return {"path": path, "mime": mime, "duration_s": None}


registry.register(MacOSAudioCapture())
