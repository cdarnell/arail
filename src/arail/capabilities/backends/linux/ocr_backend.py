"""Linux image-text OCR — registered stub (ROADMAP).

The macOS v1 backend is Apple-only, so OCR cannot serve Linux for free the way
cross-platform Whisper did for STT. The honest v1 Linux answer is a
**registered stub**: ``is_available()`` → False (resolves ``declared_unavailable``)
and ``invoke()`` raises a clean ``CapabilityNotImplemented`` — never a crash.

The cross-platform Tesseract/PaddleOCR path is the ROADMAP that *serves* Linux
later: adding it = implementing this one ``invoke()`` (no contract/schema/loader/
portal change), which is the WC-B proof.
"""

from __future__ import annotations

from typing import Any

from ...adapter import ImageTextRecognitionAdapter
from ...errors import CapabilityNotImplemented
from ... import registry


class LinuxImageOCR(ImageTextRecognitionAdapter):
    platform = "linux"
    purpose = "Recognize printed text and numbers in an image (Linux backend — roadmap)."

    def is_available(self) -> bool:
        return False

    def invoke(self, **kwargs: Any) -> Any:
        raise CapabilityNotImplemented(
            "equation-ocr: no backend for linux",
            user_message=(
                "Image OCR is not yet implemented on Linux "
                "(the Tesseract path is on the roadmap)."
            ),
        )


registry.register(LinuxImageOCR())
