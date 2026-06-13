"""Linux speech-to-text — registered, unimplemented (ROADMAP: whisper.cpp/faster-whisper)."""

from __future__ import annotations

from typing import Any

from ...adapter import SpeechToTextAdapter
from ...errors import CapabilityNotImplemented
from ... import registry


class LinuxSpeechToText(SpeechToTextAdapter):
    platform = "linux"
    purpose = "Transcribe spoken observations into the lab knowledge base."

    def is_available(self) -> bool:
        return False

    def invoke(self, **kwargs: Any) -> Any:
        raise CapabilityNotImplemented(
            "speech-to-text: no backend for linux",
            user_message="Speech-to-text is not yet implemented on Linux.",
        )


registry.register(LinuxSpeechToText())
