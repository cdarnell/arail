"""Platform-neutral on-device speech-to-text via local Whisper (faster-whisper).

Replaces the dead Apple-Speech backend (which SIGABRTed on the speech-recognition
TCC grant as an unsigned CLI binary — see BUILD_LOG DELTA 1 + Addendum A). There
is **no Apple Speech framework, no TCC grant, no code-signing** here: mic capture
stays in the browser (getUserMedia/MediaRecorder), the backend receives an audio
file and transcribes it locally with the `base.en` Whisper model.

The swap is entirely BELOW the existing adapter seam. The injectable ``_runner``
contract is UNCHANGED: a callable taking the helper-arg list and returning
``(rc, stdout, stderr)`` where stdout/stderr carry the SAME JSON shape the old
helper emitted — so every existing fake-``_runner`` test passes unchanged.

The default ``_runner``:
  1. ``afconvert -f WAVE -d LEI16@16000 -c 1 <in> <wav>`` (m4a/aac/wav/flac → 16 kHz
     mono 16-bit WAV; no ffmpeg). On Linux, decode via PyAV (``av``, pulled in
     transitively by faster-whisper).
  2. Lazy-load ``base.en`` from ``lab/models/whisper/base.en/`` (fetch on first use
     if not airgapped; graceful ``model_unavailable`` if absent + airgapped).
  3. ``model.transcribe(wav, language="en", beam_size=1)`` → join segments → JSON.
  4. ``finally:`` delete the intermediate WAV.

Registered for BOTH darwin and linux (Whisper is cross-platform), which advances
WC-3 (Linux off the STT stub). Whisper is not Apple, so the WC-B Apple-symbol
grep is trivially clean.
"""

from __future__ import annotations

import importlib.util
import json
import platform as _platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..adapter import SpeechToTextAdapter
from ..errors import CapabilityError, CapabilityUnavailable
from .. import registry

WHISPER_MODEL = "base.en"

# A runner takes the helper-arg list and returns (returncode, stdout, stderr) —
# SAME contract as the dead Swift helper, so fake-runner tests survive the swap.
RunnerResult = tuple[int, str, str]
Runner = Callable[[list[str]], RunnerResult]

# afconvert: m4a/aac/wav/flac → 16 kHz mono 16-bit WAV PCM (system binary, no ffmpeg).
_AFCONVERT_ARGS = ["-f", "WAVE", "-d", "LEI16@16000", "-c", "1"]

# Cap recorded length for v1 (long-form is ROADMAP).
_MAX_AUDIO_SECONDS = 150.0


def _model_dir() -> Path:
    """lab/models/whisper/base.en — per the MODELS_DIR convention."""
    from arail.config import MODELS_DIR
    return Path(MODELS_DIR) / "whisper" / WHISPER_MODEL


def _whisper_importable() -> bool:
    """Cheap probe — does NOT import the heavy module."""
    return importlib.util.find_spec("faster_whisper") is not None


def _afconvert_present() -> bool:
    return shutil.which("afconvert") is not None


def _pyav_importable() -> bool:
    """Linux decode path: PyAV (`av`), pulled in transitively by faster-whisper."""
    return importlib.util.find_spec("av") is not None


def _decode_available() -> bool:
    """A way to turn browser audio into a 16 kHz mono WAV on this host."""
    if _platform.system().lower() == "darwin":
        return _afconvert_present()
    # Linux (and anything else): PyAV or a system ffmpeg.
    return _pyav_importable() or shutil.which("ffmpeg") is not None


def _is_airgapped() -> bool:
    from arail.config import is_airgapped
    return bool(is_airgapped())


def _model_present() -> bool:
    return (_model_dir() / "model.bin").exists()


def _model_present_or_fetchable() -> bool:
    """Pure filesystem + mode check — no model load, no network in the probe."""
    return _model_present() or not _is_airgapped()


def _ensure_model() -> Path:
    """Return the local model dir, lazily downloading base.en on first use.

    Filesystem-stat first (never touches HF if the model is present). If absent
    and airgapped (or download fails), raise a graceful CapabilityUnavailable
    with an actionable message — never crash, never hang on the network.
    """
    mdir = _model_dir()
    if (mdir / "model.bin").exists():
        return mdir
    if _is_airgapped():
        raise CapabilityUnavailable(
            "model_unavailable",
            user_message=(
                "On-device speech model not installed. Run `./arailctl setup` with "
                "network once, or place the Whisper base.en model under "
                "`lab/models/whisper/base.en/`."
            ),
        )
    # Not airgapped: first-use lazy download with a clear activity-log line.
    print(
        f"[stt] downloading whisper {WHISPER_MODEL} (~148 MB, one time)…",
        file=sys.stderr, flush=True,
    )
    try:
        from faster_whisper import download_model
        mdir.mkdir(parents=True, exist_ok=True)
        download_model(WHISPER_MODEL, output_dir=str(mdir))
    except Exception as e:  # noqa: BLE001 — any download failure degrades gracefully
        raise CapabilityUnavailable(
            "model_unavailable",
            user_message=(
                "On-device speech engine isn't available; reinstall with "
                "`./arailctl setup` (network needed once to fetch the speech model)."
            ),
        ) from e
    return mdir


def _afconvert_to_wav(in_path: Path, wav_path: Path) -> RunnerResult | None:
    """Decode `in_path` → 16 kHz mono 16-bit WAV at `wav_path`.

    Returns None on success, or a ``decode_failed`` RunnerResult on failure.
    """
    if _platform.system().lower() == "darwin" and _afconvert_present():
        cmd = ["afconvert", *_AFCONVERT_ARGS, str(in_path), str(wav_path)]
    elif shutil.which("ffmpeg") is not None:
        cmd = ["ffmpeg", "-y", "-i", str(in_path), "-ar", "16000", "-ac", "1",
               "-sample_fmt", "s16", str(wav_path)]
    else:
        # PyAV-only Linux path: faster-whisper can decode the source directly via
        # av, so pass the original file straight through (it resamples internally).
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa: BLE001
        return (1, "", json.dumps({"ok": False, "error": "decode_failed", "message": str(e)}))
    if proc.returncode != 0:
        return (proc.returncode, "", json.dumps(
            {"ok": False, "error": "decode_failed", "message": proc.stderr or "afconvert failed"}))
    return None


def _default_runner(args: list[str]) -> RunnerResult:
    """Real path: afconvert → load base.en → transcribe → JSON. The WAV is the
    only intermediate and is cleaned in ``finally:``. Returns the SAME
    ``(rc, stdout, stderr)`` JSON shape the old Swift helper produced."""
    # args = [<binary>, "--audio", <path>, "--locale", <locale>, "--timeout", "120"]
    audio_path = Path(args[args.index("--audio") + 1])

    wav_path: Optional[Path] = None
    try:
        # 1. Decode to canonical 16 kHz mono WAV (or pass-through for PyAV Linux).
        fd, wav_name = tempfile.mkstemp(suffix=".wav", prefix="arail-stt-")
        Path(wav_name).unlink(missing_ok=True)  # we only wanted the unique name
        wav_path = Path(wav_name)
        import os as _os
        _os.close(fd)
        decode_err = _afconvert_to_wav(audio_path, wav_path)
        if decode_err is not None:
            return decode_err
        transcribe_target = wav_path if wav_path.exists() else audio_path

        # 2. Ensure the model is on disk (lazy fetch; airgapped-graceful).
        try:
            mdir = _ensure_model()
        except CapabilityUnavailable as e:
            return (2, "", json.dumps(
                {"ok": False, "error": "model_unavailable", "message": e.user_message}))

        # 3. Load + transcribe.
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel(str(mdir), device="cpu", compute_type="int8")
            segments_iter, info = model.transcribe(
                str(transcribe_target), language="en", beam_size=1)
        except Exception as e:  # noqa: BLE001 — engine/runtime failure → graceful
            return (2, "", json.dumps(
                {"ok": False, "error": "model_unavailable",
                 "message": "On-device speech engine isn't available; "
                            "reinstall with `./arailctl setup`. (" + str(e) + ")"}))

        # Long-audio guard (v1 cap ~2 min).
        if getattr(info, "duration", 0.0) and info.duration > _MAX_AUDIO_SECONDS:
            return (1, "", json.dumps(
                {"ok": False, "error": "timeout",
                 "message": "keep voice notes under ~2 minutes for v1."}))

        segs = []
        logprobs = []
        for s in segments_iter:
            text = s.text.strip()
            segs.append({"text": text, "ts": float(s.start)})
            if getattr(s, "avg_logprob", None) is not None:
                logprobs.append(float(s.avg_logprob))
        transcript = " ".join(s["text"] for s in segs).strip()
        # avg_logprob (~ -1..0) → a rough 0..1 confidence.
        if logprobs:
            import math
            confidence = max(0.0, min(1.0, math.exp(sum(logprobs) / len(logprobs))))
        else:
            confidence = 0.0

        if not transcript:
            return (3, "", json.dumps(
                {"ok": False, "error": "no_speech", "message": "Nothing heard."}))

        return (0, json.dumps(
            {"ok": True, "transcript": transcript, "segments": segs,
             "confidence": confidence, "on_device": True}), "")
    finally:
        if wav_path is not None:
            wav_path.unlink(missing_ok=True)


class WhisperSpeechToText(SpeechToTextAdapter):
    """Local-Whisper STT, platform-neutral. Registered for darwin AND linux."""

    purpose = ("Transcribe spoken observations into the lab knowledge base "
               "(on-device, local Whisper).")

    def __init__(self, platform: str = "darwin", runner: Optional[Runner] = None):
        # Per-platform instance tag so registry.select() picks the right one; both
        # delegate to the same Whisper logic.
        self.platform = platform
        # Injectable subprocess/model boundary; default = real transcription.
        self._runner: Runner = runner or _default_runner

    def _ensure_helper(self) -> Path:
        """Backward-compat no-op seam.

        The old Apple backend compiled a helper binary here; the Whisper backend
        does its model lookup inside ``_default_runner`` instead. Retained so the
        existing fake-``_runner`` flow tests (which monkeypatch this away) keep
        working UNCHANGED — they replace the runner, so this never does real work.
        Returns the model dir for symmetry; callers ignore the result.
        """
        return _model_dir()

    def is_available(self) -> bool:
        """Cheap probe: lib importable + a decode path + model present-or-fetchable.
        No model load, no network."""
        if self.platform != _platform.system().lower():
            return False
        return _whisper_importable() and _decode_available() and _model_present_or_fetchable()

    def invoke(self, **kwargs: Any) -> Dict[str, Any]:
        audio = kwargs["audio"]
        locale = kwargs.get("locale", "en-US")
        audio_path = Path(audio["path"])

        args = ["whisper-stt", "--audio", str(audio_path),
                "--locale", locale, "--timeout", "120"]

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
                    f"decode_failed: bad runner output: {e}",
                    user_message="Transcription produced an unreadable result. Try again.",
                ) from e
            return {
                "text": str(data.get("transcript", "")),
                "segments": list(data.get("segments", [])),
                "confidence": float(data.get("confidence", 0.0) or 0.0),
                "on_device": bool(data.get("on_device", True)),
            }

        # Non-zero: parse stderr JSON for an error code (no TCC special-case — the
        # Apple signing wall is gone).
        code = "decode_failed"
        message = "Transcription failed. Try again."
        try:
            edata = json.loads(err)
            code = str(edata.get("error", code))
            message = str(edata.get("message", message))
        except Exception:  # noqa: BLE001
            pass

        if code == "no_speech":
            return {"text": "", "segments": [], "confidence": 0.0, "on_device": True}
        if code in ("permission_denied", "model_unavailable"):
            raise CapabilityUnavailable(code, user_message=message)
        if code == "timeout":
            raise CapabilityError(
                "timeout",
                user_message="Recording too long — keep voice notes under ~2 minutes for v1.",
            )
        if code in ("unsupported_audio", "decode_failed"):
            raise CapabilityError(code, user_message=message or "Couldn't read that recording. Try again.")
        raise CapabilityError(code, user_message=message)


# Register for BOTH platforms (Whisper is cross-platform → WC-3: Linux off the stub).
registry.register(WhisperSpeechToText(platform="darwin"))
registry.register(WhisperSpeechToText(platform="linux"))
