"""Linux backends. Speech-to-text is now served by the platform-neutral
local-Whisper backend (``backends/whisper_stt.py``, registered for linux too) —
the old Linux STT stub was RETIRED, so Linux is off the STT stub (WC-3). Only the
audio-capture seam remains a Linux ROADMAP stub (capture is in the browser
regardless, so file-in STT works today via /api/stt/transcribe).
"""

from __future__ import annotations

from . import audio_backend as _audio  # noqa: F401
