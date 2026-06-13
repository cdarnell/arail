"""macOS on-device speech-to-text adapter.

Shells a tiny Swift helper (``stt_helper.swift``) compiled lazily to
``lab/bin/arail-stt`` via ``xcrun swiftc``. No Python Apple bindings (no pyobjc).
On-device only: the helper sets ``requiresOnDeviceRecognition = true`` so it
never contacts Apple servers and works under ``LAB_MODE=airgapped``.

The subprocess boundary is injectable via ``_runner`` so CI runs without real
audio / mic / Speech.framework.
"""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ...adapter import SpeechToTextAdapter
from ...errors import CapabilityError, CapabilityUnavailable
from ... import registry

_HELPER_SRC = Path(__file__).with_name("stt_helper.swift")
_HELPER_BIN_NAME = "arail-stt"

# A runner takes the helper-arg list and returns (returncode, stdout, stderr).
RunnerResult = tuple[int, str, str]
Runner = Callable[[list[str]], RunnerResult]


def _bin_dir() -> Path:
    from arail.config import LAB_ROOT
    d = Path(LAB_ROOT) / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default_runner(args: list[str]) -> RunnerResult:
    proc = subprocess.run(args, capture_output=True, text=True, timeout=180)
    return proc.returncode, proc.stdout, proc.stderr


class MacOSSpeechToText(SpeechToTextAdapter):
    platform = "darwin"
    purpose = "Transcribe spoken observations into the lab knowledge base (on-device)."

    def __init__(self, runner: Optional[Runner] = None):
        # Injectable subprocess boundary; default = real helper.
        self._runner: Runner = runner or _default_runner

    def is_available(self) -> bool:
        return platform.system().lower() == "darwin" and shutil.which("xcrun") is not None

    def _ensure_helper(self) -> Path:
        """Compile the Swift helper once, cache the binary, reuse it."""
        binary = _bin_dir() / _HELPER_BIN_NAME
        if binary.exists():
            return binary
        if shutil.which("xcrun") is None or shutil.which("swiftc") is None:
            raise CapabilityUnavailable(
                "model_unavailable: xcode CLT missing",
                user_message=(
                    "Speech-to-text needs Apple's command-line tools. "
                    "Run: `xcode-select --install`, then try again."
                ),
            )
        try:
            subprocess.run(
                ["xcrun", "swiftc", str(_HELPER_SRC), "-o", str(binary)],
                capture_output=True, text=True, check=True, timeout=300,
            )
        except Exception as e:  # noqa: BLE001
            raise CapabilityUnavailable(
                f"helper compile failed: {e}",
                user_message=(
                    "Couldn't build the on-device speech helper. Ensure Xcode "
                    "command-line tools are installed (`xcode-select --install`)."
                ),
            ) from e
        return binary

    def invoke(self, **kwargs: Any) -> Dict[str, Any]:
        audio = kwargs["audio"]
        locale = kwargs.get("locale", "en-US")
        audio_path = Path(audio["path"])

        binary = self._ensure_helper()
        args = [str(binary), "--audio", str(audio_path), "--locale", locale, "--timeout", "120"]

        try:
            rc, out, err = self._runner(args)
        except subprocess.TimeoutExpired as e:
            raise CapabilityError(
                "timeout",
                user_message="Recording too long — keep voice notes under ~2 minutes for v1.",
            ) from e

        if rc == 0:
            try:
                data = json.loads(out)
            except Exception as e:  # noqa: BLE001
                raise CapabilityError(
                    f"decode_failed: bad helper output: {e}",
                    user_message="Transcription produced an unreadable result. Try again.",
                ) from e
            return {
                "text": str(data.get("transcript", "")),
                "segments": list(data.get("segments", [])),
                "confidence": float(data.get("confidence", 0.0) or 0.0),
                "on_device": bool(data.get("on_device", True)),
            }

        # Non-zero: parse stderr JSON for an error code.
        code = "decode_failed"
        message = "Transcription failed. Try again."
        try:
            edata = json.loads(err)
            code = str(edata.get("error", code))
            message = str(edata.get("message", message))
        except Exception:  # noqa: BLE001
            pass

        if code == "no_speech":
            # Graceful "nothing heard" — empty transcript, not an error.
            return {"text": "", "segments": [], "confidence": 0.0, "on_device": True}
        if code in ("permission_denied", "model_unavailable"):
            raise CapabilityUnavailable(code, user_message=message)
        if code == "timeout":
            raise CapabilityError(
                "timeout",
                user_message="Recording too long — keep voice notes under ~2 minutes for v1.",
            )
        if code == "unsupported_audio":
            raise CapabilityError("unsupported_audio", user_message=message)
        raise CapabilityError(code, user_message=message)


registry.register(MacOSSpeechToText())
