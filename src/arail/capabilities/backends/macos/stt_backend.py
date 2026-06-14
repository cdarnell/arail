"""macOS speech-to-text — now the platform-neutral local-Whisper backend.

The old Apple-Speech path (a lazy-compiled helper shelling the on-device speech
recognizer) is **dead**: an unsigned CLI binary SIGABRTs on the speech-recognition
TCC grant, and shipping a signed ``.app`` was rejected by the owner (see BUILD_LOG
DELTA 1 + ARCHITECTURE Addendum A). The old helper source
(``stt_helper.swift``) and Apple body were DELETED; STT is now local Whisper
(``backends/whisper_stt.py``), registered for both darwin and linux there.

This module is retained only as a backward-compatible alias so existing imports
(`from ...backends.macos.stt_backend import MacOSSpeechToText`) keep working. It
contains **zero** Apple symbols — the WC-B grep is clean over all of ``src/``.
``MacOSSpeechToText`` is just ``WhisperSpeechToText`` (the macOS-tagged class).
"""

from __future__ import annotations

from ..whisper_stt import WhisperSpeechToText, _default_runner  # noqa: F401

# Backward-compatible name. Registration is owned by whisper_stt (both platforms);
# importing this module does NOT double-register.
MacOSSpeechToText = WhisperSpeechToText
