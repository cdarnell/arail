"""Capability registry + resolution + mount-sidecar tests.

Covers (per ARCHITECTURE §9):
- registry resolution states (available / declared-unavailable / no-adapter)
- WC-B: Linux backend selected on macOS raises a clean CapabilityUnavailable;
        the Apple-symbol grep is clean.
- WC-C: a second declared id (equation-ocr) degrades gracefully, zero code.
- WC-D: a bundle with no capabilities.json mounts clean (no sidecar caps).
- malformed capabilities.json → mount succeeds, capabilities_error recorded.
- missing-CLT → STT is_available() False → declared_unavailable.
- unmount removes the sidecar.
"""

from __future__ import annotations

import json
import pathlib
import subprocess

import pytest

from arail import world_mount as wm
from arail import capabilities as caps
from arail.capabilities import registry, resolve_capabilities, CapabilitySpec, CapabilityUnavailable
from arail.capabilities.spec import parse_capabilities_file, MalformedCapabilities

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
CAPS_STT = FIXTURES / "world-caps-stt"
CAPS_BOTH = FIXTURES / "world-caps-both"
NO_CAPS = FIXTURES / "world-no-caps"


# ── registry resolution states ─────────────────────────────────────────


def test_registry_select_unknown_id_returns_none():
    assert registry.select("totally-made-up-capability") is None


def test_registry_resolution_states():
    """available (stt on mac) / declared_unavailable (no adapter) map correctly."""
    specs = [
        CapabilitySpec(id="speech-to-text", purpose="p", desired=True),
        CapabilitySpec(id="equation-ocr", purpose="q", desired=True),
    ]
    resolved = {r.id: r for r in resolve_capabilities(specs)}
    # equation-ocr now has a registered backend (macOS Vision / Linux stub) — it
    # resolves available-or-declared_unavailable depending on host, never "no
    # adapter". (The N=1 "no adapter at all" state is gone — this is the WC-C flip.)
    assert resolved["equation-ocr"].state in ("available", "declared_unavailable")
    assert resolved["equation-ocr"].adapter_platform in ("darwin", "linux")
    # stt: available on darwin w/ CLT; declared_unavailable elsewhere — both valid states.
    assert resolved["speech-to-text"].state in ("available", "declared_unavailable")


def test_resolve_model_absent_airgapped_declared_unavailable(monkeypatch):
    """Model absent + airgapped → WhisperSpeechToText.is_available() False →
    declared_unavailable (the post-swap equivalent of the old missing-CLT gate)."""
    import arail.capabilities.backends.whisper_stt as ws
    monkeypatch.setattr(ws._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ws, "_model_present", lambda: False)
    monkeypatch.setattr(ws, "_is_airgapped", lambda: True)  # absent + airgapped → not fetchable
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    resolved = resolve_capabilities([CapabilitySpec(id="speech-to-text")])
    assert resolved[0].state == "declared_unavailable"


# ── WC-3: Linux is OFF the STT stub (Whisper is cross-platform) ─────────


def test_wc3_linux_selected_returns_whisper(monkeypatch):
    """Post-swap: forcing linux selects the platform-neutral Whisper backend,
    NOT a CapabilityNotImplemented stub — Linux is off the STT stub (WC-3)."""
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "linux")
    adapter = registry.select("speech-to-text")
    assert type(adapter).__name__ == "WhisperSpeechToText"
    assert adapter.platform == "linux"


def test_wc_b_no_apple_symbols_anywhere():
    """The STT Apple-symbol grep returns nothing in source — the Apple-Speech path
    is deleted. (``swiftc``/``xcrun`` are now legitimately reintroduced by the OCR
    Vision backend under ``backends/macos/``; those are covered by the OCR WC-B
    test and excluded here, along with build-cache artifacts.)"""
    repo = pathlib.Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        ["grep", "-rEln", "--include=*.py", "--include=*.swift",
         "--exclude-dir=.mypy_cache", "--exclude-dir=__pycache__",
         r"AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b", "src/"],
        cwd=repo, capture_output=True, text=True,
    )
    assert proc.returncode != 0, f"Apple STT symbols leaked:\n{proc.stdout}"


# ── WC-C: second declared id, zero code ────────────────────────────────


def test_wc_c_second_declared_id_zero_code(tmp_path, monkeypatch):
    """Mount world-caps-both: equation-ocr now resolves through a registered
    backend via the SAME resolve path — the WC-C flip. (Previously this id had no
    adapter; the OCR sprint registered one with zero engine code.)"""
    # An OCR adapter is now registered (macOS Vision + Linux stub).
    assert registry.adapters_for("equation-ocr"), "OCR backend should be registered"
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "darwin")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    rec = wm.mount(CAPS_BOTH, data_dir=data_dir, pkb_root=pkb_root)
    assert rec.world == "physics"
    side = json.loads((data_dir / "world-capabilities.json").read_text())
    byid = {c["id"]: c for c in side["capabilities"]}
    # On darwin w/ xcrun present it's available; otherwise declared_unavailable —
    # never the "no adapter" path anymore.
    assert byid["equation-ocr"]["state"] in ("available", "declared_unavailable")
    assert side["capabilities_error"] is None


# ── WC-D: no capabilities.json mounts clean ────────────────────────────


def test_resolve_no_capabilities_file_mounts_clean(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    rec = wm.mount(NO_CAPS, data_dir=data_dir, pkb_root=pkb_root)
    assert rec.world == "physics"
    # Sidecar exists but carries zero resolved capabilities (graceful absence).
    assert wm.current_capabilities(data_dir) == []
    side = json.loads((data_dir / "world-capabilities.json").read_text())
    assert side["capabilities"] == []
    assert side["capabilities_error"] is None


# ── malformed capabilities.json ────────────────────────────────────────


def test_resolve_malformed_capabilities_mounts_clean(tmp_path):
    # Build a corrupt-caps bundle by copying world-no-caps + a bad file.
    import shutil
    bad = tmp_path / "bad-bundle"
    shutil.copytree(NO_CAPS, bad)
    (bad / "capabilities.json").write_text("{ this is not valid json ")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    rec = wm.mount(bad, data_dir=data_dir, pkb_root=pkb_root)
    assert rec.world == "physics"
    side = json.loads((data_dir / "world-capabilities.json").read_text())
    assert side["capabilities"] == []
    assert side["capabilities_error"]  # recorded


def test_parse_rejects_wrong_schema(tmp_path):
    p = tmp_path / "capabilities.json"
    p.write_text(json.dumps({"capabilities": []}))  # missing 'schema'
    with pytest.raises(MalformedCapabilities):
        parse_capabilities_file(p)
    p.write_text(json.dumps({"schema": "x", "capabilities": "not-a-list"}))
    with pytest.raises(MalformedCapabilities):
        parse_capabilities_file(p)


def test_parse_tolerant_of_optional_fields(tmp_path):
    p = tmp_path / "capabilities.json"
    p.write_text(json.dumps({
        "schema": "dac.world-capabilities/v1",
        "unknown_top_key": 1,
        "capabilities": [{"id": "speech-to-text"}, {"no_id": True}],
    }))
    specs = parse_capabilities_file(p)
    assert len(specs) == 1
    assert specs[0].id == "speech-to-text"
    assert specs[0].purpose == "" and specs[0].desired is True


# ── unmount removes the sidecar ────────────────────────────────────────


def test_unmount_removes_sidecar(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    wm.mount(CAPS_STT, data_dir=data_dir, pkb_root=pkb_root)
    assert (data_dir / "world-capabilities.json").exists()
    wm.unmount(data_dir=data_dir, pkb_root=pkb_root)
    assert not (data_dir / "world-capabilities.json").exists()


# ── WC-C generalization: the registry serves TWO live capabilities ─────


def _force_both_available(monkeypatch):
    """Force speech-to-text AND equation-ocr is_available()=True on darwin, so the
    resolve path is exercised without a Whisper model or the swiftc toolchain."""
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "darwin")
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    # Patch at the CLASS level (not the instance): a monkeypatch.setattr on an
    # instance restores by SETTING an instance attribute on teardown, which then
    # shadows any later class-level patch of the same adapter (the mic/OCR chat
    # tests patch the class) — a cross-test leak. Class patching tears down
    # cleanly and leaves no shadow.
    for adapter in registry.adapters_for("speech-to-text"):
        if adapter.platform == "darwin":
            monkeypatch.setattr(type(adapter), "is_available", lambda self: True)
    for adapter in registry.adapters_for("equation-ocr"):
        if adapter.platform == "darwin":
            monkeypatch.setattr(type(adapter), "is_available", lambda self: True)


def test_two_live_capabilities_resolve_available(monkeypatch):
    """THE HEADLINE WC-C FLIP: with both adapters available, world-caps-both lights
    up speech-to-text AND equation-ocr through the identical resolve path."""
    _force_both_available(monkeypatch)
    specs = [
        CapabilitySpec(id="speech-to-text", purpose="p", desired=True),
        CapabilitySpec(id="equation-ocr", purpose="q", desired=True),
    ]
    resolved = {r.id: r for r in resolve_capabilities(specs)}
    assert resolved["speech-to-text"].state == "available"
    assert resolved["equation-ocr"].state == "available"
    assert resolved["equation-ocr"].adapter_platform == "darwin"


def test_wc_c_third_undeclared_id_still_declared_unavailable(monkeypatch):
    """Adding the OCR adapter special-cased NOTHING: a third id with no adapter
    still resolves declared_unavailable through the same path."""
    _force_both_available(monkeypatch)
    resolved = {r.id: r for r in resolve_capabilities(
        [CapabilitySpec(id="totally-undeclared-cap", purpose="z", desired=True)])}
    assert resolved["totally-undeclared-cap"].state == "declared_unavailable"
    assert resolved["totally-undeclared-cap"].adapter_platform is None


def test_ocr_zero_code_in_engine():
    """The OCR adapter is reached via the existing select() with NO edit to the
    engine core — assert select returns a real adapter and the engine modules are
    untouched by the diff (structural: changes live in adapter.py + backends/)."""
    adapter = registry.select("equation-ocr")
    assert adapter is not None
    assert adapter.id == "equation-ocr"


def test_wc_b_linux_ocr_raises_clean(monkeypatch):
    """Forced linux → OCR invoke() raises the clean CapabilityNotImplemented."""
    from arail.capabilities import CapabilityNotImplemented
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "linux")
    adapter = registry.select("equation-ocr")
    assert type(adapter).__name__ == "LinuxImageOCR"
    with pytest.raises(CapabilityNotImplemented) as ei:
        adapter.invoke(image={"path": "/x", "mime": "image/png"})
    assert "no backend for linux" in str(ei.value)


def test_ocr_declared_unavailable_off_platform(monkeypatch):
    """ARAIL_FORCE_PLATFORM=linux → equation-ocr resolves declared_unavailable
    (the Linux stub's is_available() is False)."""
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "linux")
    resolved = resolve_capabilities([CapabilitySpec(id="equation-ocr", purpose="q")])
    assert resolved[0].state == "declared_unavailable"
    assert resolved[0].adapter_platform == "linux"


def test_ocr_unavailable_missing_clt(monkeypatch):
    """No xcrun on PATH → MacOSImageOCR.is_available() False → declared_unavailable
    with the xcode-select hint reachable at invoke."""
    import arail.capabilities.backends.macos.ocr_backend as ob
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "darwin")
    monkeypatch.setattr(ob._platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ob.shutil, "which", lambda name: None)
    adapter = registry.select("equation-ocr")
    # select() returns the darwin adapter even though unavailable (right message).
    assert type(adapter).__name__ == "MacOSImageOCR"
    assert adapter.is_available() is False
    resolved = resolve_capabilities([CapabilitySpec(id="equation-ocr", purpose="q")])
    assert resolved[0].state == "declared_unavailable"


def test_wc_b_no_apple_ocr_symbols_above_seam():
    """The OCR Apple-symbol grep matches ONLY under backends/macos/."""
    repo = pathlib.Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        ["grep", "-rEl", "--include=*.py", "--include=*.swift",
         "--exclude-dir=.mypy_cache", "--exclude-dir=__pycache__",
         r"Vision|VNRecognizeTextRequest|AppKit|swiftc|xcrun", "src/"],
        cwd=repo, capture_output=True, text=True,
    )
    hits = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    leaked = [h for h in hits if "backends/macos/" not in h]
    assert leaked == [], f"Apple OCR symbols leaked above the seam:\n{leaked}"
