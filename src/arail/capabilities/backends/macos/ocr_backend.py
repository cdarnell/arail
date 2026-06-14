"""macOS image-text OCR via Apple Vision (the v1 ``equation-ocr`` backend).

Unlike the dead Apple-Speech STT path (which SIGABRTed on the speech-recognition
TCC grant as an unsigned CLI binary), ``VNRecognizeTextRequest`` runs on a STATIC
image and needs **no TCC grant, no code-signing, no Info.plist** — so we resurrect
the lazy-``swiftc`` compile pattern STT had to abandon. The Vision helper
(``ocr_helper.swift``) compiles unsigned with the stock toolchain on first use and
runs on-device, airgapped, zero deps.

Mirrors ``whisper_stt.py``'s shape EXACTLY:
  - an injectable ``_runner(args) -> (rc, stdout, stderr)``-JSON boundary, so CI
    mocks the whole Vision/swiftc/image stack with a fake runner;
  - a cheap ``is_available()`` probe (darwin + ``xcrun`` present — no Vision call);
  - error-code mapping in ``invoke()``.

ALL Apple symbols (``Vision``/``VNRecognizeTextRequest``/``AppKit``/``swiftc``/
``xcrun``) are confined to THIS package (``backends/macos/``) — the WC-B grep over
``src/`` is clean above the seam.
"""

from __future__ import annotations

import json
import platform as _platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ...adapter import ImageTextRecognitionAdapter
from ...errors import CapabilityError, CapabilityUnavailable
from ... import registry

# A runner takes the helper-arg list and returns (returncode, stdout, stderr) —
# SAME contract as whisper_stt, so a fake runner mocks without Vision/swiftc.
RunnerResult = tuple[int, str, str]
Runner = Callable[[list[str]], RunnerResult]

_HELPER_NAME = "arail-ocr"


def _bin_dir() -> Path:
    """lab/bin — where the compiled helper is cached (mirrors the STT convention)."""
    from arail.config import LAB_ROOT
    d = Path(LAB_ROOT) / "bin"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _helper_path() -> Path:
    return _bin_dir() / _HELPER_NAME


def _helper_src() -> Path:
    """The bundled Vision helper source, next to this module."""
    return Path(__file__).resolve().parent / "ocr_helper.swift"


def _toolchain_present() -> bool:
    return shutil.which("xcrun") is not None and shutil.which("swiftc") is not None


def _ensure_helper() -> Path:
    """Lazily compile the Vision helper → lab/bin/arail-ocr, cached and reused.

    Stock toolchain only (``xcrun swiftc -O``); no Xcode project, no signing. If
    ``xcrun``/``swiftc`` is absent, raise CapabilityUnavailable with an actionable
    ``xcode-select`` hint — never crash, never hang.
    """
    helper = _helper_path()
    if helper.exists():
        return helper
    if not _toolchain_present():
        raise CapabilityUnavailable(
            "model_unavailable",
            user_message=(
                "Image OCR needs Apple's command-line tools. "
                "Run: `xcode-select --install`, then try again."
            ),
        )
    src = _helper_src()
    try:
        proc = subprocess.run(
            ["xcrun", "swiftc", "-O", str(src), "-o", str(helper)],
            capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # noqa: BLE001 — any compile failure degrades gracefully
        raise CapabilityUnavailable(
            "model_unavailable",
            user_message=(
                "Couldn't build the on-device OCR helper. Ensure Apple's "
                "command-line tools are installed (`xcode-select --install`)."
            ),
        ) from e
    if proc.returncode != 0 or not helper.exists():
        raise CapabilityUnavailable(
            "model_unavailable",
            user_message=(
                "Couldn't build the on-device OCR helper. Ensure Apple's "
                "command-line tools are installed (`xcode-select --install`)."
            ),
        )
    return helper


def _default_runner(args: list[str]) -> RunnerResult:
    """Real path: lazy-compile the Vision helper, then shell it on the image.

    Returns the SAME (rc, stdout, stderr) JSON shape the helper emits (§1.4). All
    swiftc/Vision/subprocess work lives HERE so a fake ``_runner`` in CI never
    compiles or shells anything.
    """
    image_path = args[args.index("--image") + 1]
    try:
        helper = _ensure_helper()
    except CapabilityUnavailable as e:
        return (2, "", json.dumps(
            {"ok": False, "error": "model_unavailable", "message": e.user_message}))
    try:
        proc = subprocess.run(
            [str(helper), "--image", str(image_path)],
            capture_output=True, text=True, timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise
    except Exception as e:  # noqa: BLE001
        return (1, "", json.dumps(
            {"ok": False, "error": "decode_failed", "message": str(e)}))
    return (proc.returncode, proc.stdout, proc.stderr)


class MacOSImageOCR(ImageTextRecognitionAdapter):
    """Apple-Vision image-text OCR. macOS only (Vision is Apple-native)."""

    platform = "darwin"
    purpose = (
        "Recognize printed text and numbers in an image into the lab knowledge "
        "base (on-device, Apple Vision)."
    )

    def __init__(self, runner: Optional[Runner] = None):
        # Injectable subprocess/Vision boundary; default = real OCR.
        self._runner: Runner = runner or _default_runner

    def _ensure_helper(self) -> Path:
        """Backward-compat seam (tests monkeypatch this); real work is in the runner."""
        return _ensure_helper()

    def is_available(self) -> bool:
        """Cheap probe: darwin + xcrun present (helper compiles on first use).
        No image, no Vision call."""
        return _platform.system().lower() == "darwin" and shutil.which("xcrun") is not None

    def invoke(self, **kwargs: Any) -> Dict[str, Any]:
        image = kwargs["image"]
        args = [_HELPER_NAME, "--image", str(image["path"])]

        try:
            rc, out, err = self._runner(args)
        except subprocess.TimeoutExpired as e:
            raise CapabilityError(
                "timeout",
                user_message="That image took too long to read. Try a smaller image.",
            ) from e

        if rc == 0:
            try:
                data = json.loads(out)
            except Exception as e:  # noqa: BLE001
                raise CapabilityError(
                    f"decode_failed: bad runner output: {e}",
                    user_message="OCR produced an unreadable result. Try again.",
                ) from e
            text = str(data.get("text", ""))
            lines = [ln for ln in text.split("\n")]
            return {"text": text, "lines": lines, "on_device": True}

        # Non-zero: parse the error JSON (stdout OR stderr) for a code.
        code = "decode_failed"
        message = "Couldn't read that image. Try a clearer PNG/JPEG."
        for blob in (out, err):
            try:
                edata = json.loads(blob)
                code = str(edata.get("error", code))
                message = str(edata.get("message", message))
                break
            except Exception:  # noqa: BLE001
                continue

        if code == "no_text":
            return {"text": "", "lines": [], "on_device": True}
        if code == "model_unavailable":
            raise CapabilityUnavailable(code, user_message=message)
        # decode_failed / unsupported_image → recoverable client error.
        raise CapabilityError(code, user_message=message)


registry.register(MacOSImageOCR())
