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
    # equation-ocr has no adapter at all → declared_unavailable, no platform.
    assert resolved["equation-ocr"].state == "declared_unavailable"
    assert resolved["equation-ocr"].adapter_platform is None
    # stt: available on darwin w/ CLT; declared_unavailable elsewhere — both valid states.
    assert resolved["speech-to-text"].state in ("available", "declared_unavailable")


def test_resolve_missing_clt_declared_unavailable(monkeypatch):
    """xcrun absent → MacOSSpeechToText.is_available() False → declared_unavailable."""
    import arail.capabilities.backends.macos.stt_backend as stt
    import platform as _pf
    monkeypatch.setattr(stt.shutil, "which", lambda _n: None)
    monkeypatch.setattr(stt.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(registry, "_host_platform", lambda: "darwin")
    resolved = resolve_capabilities([CapabilitySpec(id="speech-to-text")])
    assert resolved[0].state == "declared_unavailable"


# ── WC-B: Linux selected on macOS raises clean ─────────────────────────


def test_wc_b_linux_selected_raises_clean(monkeypatch):
    monkeypatch.setenv("ARAIL_FORCE_PLATFORM", "linux")
    adapter = registry.select("speech-to-text")
    assert type(adapter).__name__ == "LinuxSpeechToText"
    with pytest.raises(CapabilityUnavailable) as ei:
        adapter.invoke(audio={}, locale="en-US")
    assert str(ei.value) == "speech-to-text: no backend for linux"
    assert ei.value.user_message  # actionable


def test_wc_b_no_apple_symbols_above_seam():
    """The Apple-symbol grep (ARCHITECTURE §6) returns nothing outside macos backend."""
    repo = pathlib.Path(__file__).resolve().parent.parent
    proc = subprocess.run(
        ["grep", "-rEn", r"AVFoundation|SFSpeechRecognizer|pyobjc|\bobjc\b|swiftc|xcrun",
         "src/", "--exclude-dir=macos"],
        cwd=repo, capture_output=True, text=True,
    )
    assert proc.returncode != 0, f"Apple symbols leaked above the seam:\n{proc.stdout}"


# ── WC-C: second declared id, zero code ────────────────────────────────


def test_wc_c_second_declared_id_zero_code(tmp_path):
    """Mount world-caps-both: equation-ocr resolves declared_unavailable, lab works,
    nothing raised, and no equation-ocr adapter exists in the registry."""
    assert registry.adapters_for("equation-ocr") == []
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    rec = wm.mount(CAPS_BOTH, data_dir=data_dir, pkb_root=pkb_root, env_path=tmp_path / ".env")
    assert rec.world == "physics"
    side = json.loads((data_dir / "world-capabilities.json").read_text())
    byid = {c["id"]: c for c in side["capabilities"]}
    assert byid["equation-ocr"]["state"] == "declared_unavailable"
    assert side["capabilities_error"] is None


# ── WC-D: no capabilities.json mounts clean ────────────────────────────


def test_resolve_no_capabilities_file_mounts_clean(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    rec = wm.mount(NO_CAPS, data_dir=data_dir, pkb_root=pkb_root, env_path=tmp_path / ".env")
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
    rec = wm.mount(bad, data_dir=data_dir, pkb_root=pkb_root, env_path=tmp_path / ".env")
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
    wm.mount(CAPS_STT, data_dir=data_dir, pkb_root=pkb_root, env_path=tmp_path / ".env")
    assert (data_dir / "world-capabilities.json").exists()
    wm.unmount(data_dir=data_dir, pkb_root=pkb_root)
    assert not (data_dir / "world-capabilities.json").exists()
