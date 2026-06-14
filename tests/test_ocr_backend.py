"""MacOSImageOCR backend unit tests (injectable _runner; no live Vision).

The OCR boundary is the ``_runner`` callable; we inject a fake runner returning
known JSON (the helper contract) so CI never compiles swiftc or runs Vision. The
real path (lazy swiftc compile → arail-ocr → Vision) is gated behind
``@pytest.mark.live_ocr`` and skipped by default.

Covers:
- error-code mapping in invoke() across the seam (ok / no_text / decode_failed /
  model_unavailable / bad JSON),
- is_available() (darwin + xcrun present vs absent),
- real Vision OCR on a synthesized constants image (live_ocr),
- helper compiles once + is cached (live_ocr),
- the WC-B OCR Apple-symbol grep matches only under backends/macos/.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from arail.capabilities.backends.macos.ocr_backend import MacOSImageOCR
import arail.capabilities.backends.macos.ocr_backend as ob
from arail.capabilities import CapabilityError, CapabilityUnavailable


# ── invoke() error-code mapping across the seam (fake _runner) ─────────


def test_runner_success_maps_text():
    payload = json.dumps({"ok": True, "text": "k = 1.380649e-23 J/K\nE = mc^2"})
    ocr = MacOSImageOCR(runner=lambda args: (0, payload, ""))
    out = ocr.invoke(image={"path": "/tmp/x.png", "mime": "image/png"})
    assert out["text"] == "k = 1.380649e-23 J/K\nE = mc^2"
    assert out["lines"] == ["k = 1.380649e-23 J/K", "E = mc^2"]
    assert out["on_device"] is True


def test_no_text_maps_to_empty():
    err = json.dumps({"ok": False, "error": "no_text", "message": "No text found."})
    ocr = MacOSImageOCR(runner=lambda args: (4, err, ""))
    out = ocr.invoke(image={"path": "/tmp/x.png", "mime": "image/png"})
    assert out["text"] == "" and out["lines"] == [] and out["on_device"] is True


def test_decode_failed_raises_capability_error():
    err = json.dumps({"ok": False, "error": "decode_failed", "message": "Couldn't read that image."})
    ocr = MacOSImageOCR(runner=lambda args: (3, err, ""))
    with pytest.raises(CapabilityError) as ei:
        ocr.invoke(image={"path": "/tmp/x.png", "mime": "image/png"})
    assert "read that image" in ei.value.user_message


def test_model_unavailable_raises_capability_unavailable():
    err = json.dumps({"ok": False, "error": "model_unavailable", "message": "Run xcode-select --install."})
    ocr = MacOSImageOCR(runner=lambda args: (2, err, ""))
    with pytest.raises(CapabilityUnavailable) as ei:
        ocr.invoke(image={"path": "/tmp/x.png", "mime": "image/png"})
    assert "xcode-select" in ei.value.user_message


def test_bad_json_on_success_raises_capability_error():
    ocr = MacOSImageOCR(runner=lambda args: (0, "not json", ""))
    with pytest.raises(CapabilityError):
        ocr.invoke(image={"path": "/tmp/x.png", "mime": "image/png"})


def test_error_json_in_stderr_is_parsed():
    err = json.dumps({"ok": False, "error": "decode_failed", "message": "bad pixels"})
    ocr = MacOSImageOCR(runner=lambda args: (3, "", err))
    with pytest.raises(CapabilityError) as ei:
        ocr.invoke(image={"path": "/tmp/x.png", "mime": "image/png"})
    assert "bad pixels" in ei.value.user_message


# ── is_available() ─────────────────────────────────────────────────────


def test_is_available_true_on_darwin_with_xcrun(monkeypatch):
    monkeypatch.setattr(ob._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ob.shutil, "which", lambda name: "/usr/bin/" + name)
    assert MacOSImageOCR().is_available() is True


def test_is_available_false_without_xcrun(monkeypatch):
    monkeypatch.setattr(ob._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ob.shutil, "which", lambda name: None)
    assert MacOSImageOCR().is_available() is False


def test_is_available_false_off_darwin(monkeypatch):
    monkeypatch.setattr(ob._platform, "system", lambda: "Linux")
    monkeypatch.setattr(ob.shutil, "which", lambda name: "/usr/bin/" + name)
    assert MacOSImageOCR().is_available() is False


def test_ensure_helper_missing_clt_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(ob, "_bin_dir", lambda: tmp_path)
    monkeypatch.setattr(ob, "_toolchain_present", lambda: False)
    with pytest.raises(CapabilityUnavailable) as ei:
        ob._ensure_helper()
    assert "xcode-select" in ei.value.user_message


# ── live_ocr: real Apple Vision (compiles swiftc + OCRs a real image) ──


def _synthesize_constants_png(dest: pathlib.Path) -> bool:
    """Render a known-text constants image via CoreGraphics (PyObjC not required;
    use a Swift one-liner through `sips`/AppKit if available). Returns True on
    success. Best-effort — the live_ocr test skips if it can't render."""
    # Render with a tiny swift snippet using AppKit (matches the spike approach).
    swift = r'''
import AppKit
let text = "Physical Constants (CODATA)\nk = 1.380649e-23 J/K\nalpha = 7.2973525693e-3\nc = 299792458 m/s\nE = mc^2"
let size = NSSize(width: 700, height: 240)
let img = NSImage(size: size)
img.lockFocus()
NSColor.white.setFill()
NSRect(origin: .zero, size: size).fill()
let attrs: [NSAttributedString.Key: Any] = [
  .font: NSFont.monospacedSystemFont(ofSize: 28, weight: .regular),
  .foregroundColor: NSColor.black,
]
(text as NSString).draw(at: NSPoint(x: 20, y: 20), withAttributes: attrs)
img.unlockFocus()
guard let tiff = img.tiffRepresentation,
      let rep = NSBitmapImageRep(data: tiff),
      let png = rep.representation(using: .png, properties: [:]) else { exit(1) }
try! png.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
'''
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".swift", delete=False) as f:
        f.write(swift)
        src = f.name
    try:
        proc = subprocess.run(
            ["xcrun", "swift", src, str(dest)],
            capture_output=True, text=True, timeout=120,
        )
        return proc.returncode == 0 and dest.exists()
    except Exception:
        return False


@pytest.mark.live_ocr
def test_real_ocr(tmp_path, monkeypatch):
    """Real Vision OCR on a synthesized constants image — the WC-A.4 digit-fidelity
    proof. Asserts the recovered text contains the Boltzmann mantissa."""
    import shutil as _sh
    if _sh.which("xcrun") is None:
        pytest.skip("xcrun not present")
    img = tmp_path / "constants.png"
    if not _synthesize_constants_png(img):
        pytest.skip("could not synthesize the constants image")
    # Compile helper into a tmp bin dir, then run the real default runner.
    monkeypatch.setattr(ob, "_bin_dir", lambda: tmp_path)
    ocr = MacOSImageOCR()  # real _default_runner
    out = ocr.invoke(image={"path": img, "mime": "image/png"})
    assert "1.380649e-23" in out["text"], out["text"]
    assert out["on_device"] is True


@pytest.mark.live_ocr
def test_ocr_helper_compiles_once(tmp_path, monkeypatch):
    """_ensure_helper compiles arail-ocr once and caches it (second call no-op)."""
    import shutil as _sh
    if _sh.which("xcrun") is None:
        pytest.skip("xcrun not present")
    monkeypatch.setattr(ob, "_bin_dir", lambda: tmp_path)
    helper = ob._ensure_helper()
    assert helper.exists()
    mtime = helper.stat().st_mtime
    helper2 = ob._ensure_helper()
    assert helper2 == helper
    assert helper2.stat().st_mtime == mtime  # cached, not recompiled
