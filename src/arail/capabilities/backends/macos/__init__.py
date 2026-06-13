"""macOS backends. Apple symbols (AVFoundation, Speech, SFSpeechRecognizer,
xcrun, swiftc) are confined to THIS package by design — WC-B. A grep for those
strings outside this directory must come back clean.

Importing each module registers its adapter into the registry.
"""

from __future__ import annotations

from . import audio_backend as _audio  # noqa: F401
from . import stt_backend as _stt  # noqa: F401
