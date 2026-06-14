"""macOS backends. The Apple-Speech STT path is DELETED (Addendum A): STT is now
the platform-neutral local-Whisper backend (``backends/whisper_stt.py``). No Apple
framework symbols remain anywhere in ``src/`` — the WC-B grep is clean with no
exclude. This package now registers only the audio-capture materialization seam;
``stt_backend`` is kept as a no-Apple backward-compatible alias for Whisper.
"""

from __future__ import annotations

from . import audio_backend as _audio  # noqa: F401
from . import stt_backend as _stt  # noqa: F401
from . import ocr_backend as _ocr  # noqa: F401  # registers MacOSImageOCR
