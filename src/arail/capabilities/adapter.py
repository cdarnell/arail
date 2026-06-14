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

        macOS STT: (platform=='darwin') and the Apple compiler toolchain present.
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


class ImageTextRecognitionAdapter(Adapter):
    """Seam C — image → text OCR (printed text/numbers, v1).

    invoke(image: ImageArtifact, ...) -> OcrResult (a dict):
        ImageArtifact = {"path": Path, "mime": str}   # materialized temp file
        OcrResult     = {"text": str, "lines": list[str], "on_device": bool}

    v1 contract: inputs = one image (PNG/JPEG); outputs = `text` (lines joined by
    "\\n"). NOT LaTeX, NOT layout/tables, NOT bounding boxes (all ROADMAP). The
    declared id stays ``equation-ocr`` (fixture/WC-C continuity); v1 = TEXT.
    """

    id = "equation-ocr"
