"""Backend packages. Importing each registers its adapters into the registry.

The speech-to-text backend is the platform-neutral local-Whisper adapter
(``whisper_stt``), registered here for BOTH darwin and linux (it replaced the
dead Apple-Speech path — see ARCHITECTURE Addendum A). The per-platform packages
(``macos``/``linux``) register only the audio-capture seam.
"""

from __future__ import annotations

# Speech-to-text: one platform-neutral Whisper backend for darwin + linux.
from . import whisper_stt as _whisper_stt  # noqa: F401
