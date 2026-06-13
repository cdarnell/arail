"""Adapter ABC + the two typed seam sub-ABCs.

OS-specific code lives strictly BELOW these interfaces (in
``capabilities/backends/<platform>/``). Callers (the registry, the portal
route, ``resolve_capabilities``) go through these ABCs only — never import a
backend module — which is what makes the system Linux-ready by construction
(WC-B).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Adapter(ABC):
    """Base capability adapter.

    Subclasses set the class attributes ``id``, ``platform``, ``purpose`` and
    implement ``is_available()`` (a cheap probe) + ``invoke()`` (the work).
    """

    id: str = ""
    platform: str = ""  # "darwin" | "linux" (matches platform.system().lower())
    purpose: str = ""

    @abstractmethod
    def is_available(self) -> bool:
        """Cheap probe. True iff invoke() can plausibly succeed on this host now.

        macOS STT: (platform=='darwin') and xcrun/swiftc present.
        Linux stub: always False (never available).
        """

    @abstractmethod
    def invoke(self, **kwargs: Any) -> Any:
        """Run the capability. Raises CapabilityError / CapabilityUnavailable
        on failure (never a raw traceback to the caller)."""


class AudioCaptureAdapter(Adapter):
    """Seam A — audio/mic capture (materialization + validation).

    invoke(audio_bytes: bytes, mime: str) -> AudioArtifact (a dict):
        {"path": Path, "mime": str, "duration_s": float | None}
    """

    id = "audio-capture"


class SpeechToTextAdapter(Adapter):
    """Seam B — speech-to-text.

    invoke(audio: AudioArtifact, locale: str = "en-US") -> Transcript (a dict):
        {"text": str, "segments": list[{"text","ts"}],
         "confidence": float, "on_device": bool}
    """

    id = "speech-to-text"
