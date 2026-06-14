"""Linux audio capture — registered, unimplemented (ROADMAP: ALSA/PulseAudio/PipeWire)."""

from __future__ import annotations

from typing import Any

from ...adapter import AudioCaptureAdapter
from ...errors import CapabilityNotImplemented
from ... import registry


class LinuxAudioCapture(AudioCaptureAdapter):
    platform = "linux"
    purpose = "Capture/materialize audio for transcription."

    def is_available(self) -> bool:
        return False

    def invoke(self, **kwargs: Any) -> Any:
        raise CapabilityNotImplemented(
            "audio-capture: no backend for linux",
            user_message="Audio capture is not yet implemented on Linux.",
        )


registry.register(LinuxAudioCapture())
