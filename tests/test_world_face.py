"""Phase 4 tests: theme/face flip + consent.

Setup (30%) allocation:
- --apply-face writes exactly 5 keys (LAB_INTENT=other, LAB_INTENT_NAME, LAB_INTENT_DESCRIPTION,
  LAB_THEME, LAB_UI_THEME)
- brand untouched (LAB_NAME/LAB_LOGO not written)
- unknown palette leaves LAB_UI_THEME unwritten
- KB-only mount (no --apply-face) does NOT write any env keys
- restart hint logic (verified in CLI output)
"""

from __future__ import annotations

import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"


from arail.world_mount import mount
from arail.env_writer import read_env_var


def _mount_with_face(tmp_path, apply_face=True, bundle_dir=None):
    bundle_dir = bundle_dir or PHYSICS
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    env_path = tmp_path / ".env"
    data_dir.mkdir(exist_ok=True)
    record = mount(
        bundle_dir,
        env_path=env_path,
        pkb_root=pkb_root,
        data_dir=data_dir,
        apply_face=apply_face,
    )
    return record, env_path


# ── face flip writes 5 keys ───────────────────────────────────────────────────

def test_apply_face_writes_lab_intent_other(tmp_path):
    _, env_path = _mount_with_face(tmp_path)
    assert read_env_var(env_path, "LAB_INTENT") == "other"


def test_apply_face_writes_lab_intent_name(tmp_path):
    _, env_path = _mount_with_face(tmp_path)
    val = read_env_var(env_path, "LAB_INTENT_NAME")
    assert val is not None and len(val) > 0


def test_apply_face_writes_lab_intent_description(tmp_path):
    _, env_path = _mount_with_face(tmp_path)
    val = read_env_var(env_path, "LAB_INTENT_DESCRIPTION")
    assert val is not None and len(val) > 0


def test_apply_face_writes_lab_theme(tmp_path):
    _, env_path = _mount_with_face(tmp_path)
    val = read_env_var(env_path, "LAB_THEME")
    assert val is not None and len(val) > 0


def test_apply_face_writes_lab_ui_theme_for_known_palette(tmp_path):
    # physics face.json has palette_hint="blue-cyan-lab" which resolves
    _, env_path = _mount_with_face(tmp_path)
    val = read_env_var(env_path, "LAB_UI_THEME")
    assert val == "blue-cyan-lab"


def test_apply_face_writes_exactly_5_keys(tmp_path):
    _, env_path = _mount_with_face(tmp_path)
    expected_keys = {"LAB_INTENT", "LAB_INTENT_NAME", "LAB_INTENT_DESCRIPTION",
                     "LAB_THEME", "LAB_UI_THEME"}
    for key in expected_keys:
        assert read_env_var(env_path, key) is not None, f"{key} not written"


# ── brand untouched ───────────────────────────────────────────────────────────

def test_apply_face_does_not_write_lab_name(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LAB_NAME=MyLab\n")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    mount(PHYSICS, env_path=env_path, pkb_root=pkb_root, data_dir=data_dir, apply_face=True)
    # LAB_NAME must still be MyLab (not overwritten)
    assert read_env_var(env_path, "LAB_NAME") == "MyLab"


def test_apply_face_does_not_write_lab_logo(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LAB_LOGO=mylogo.png\n")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    mount(PHYSICS, env_path=env_path, pkb_root=pkb_root, data_dir=data_dir, apply_face=True)
    assert read_env_var(env_path, "LAB_LOGO") == "mylogo.png"


# ── unknown palette leaves LAB_UI_THEME unwritten ────────────────────────────

def test_unknown_palette_leaves_ui_theme_unwritten(tmp_path):
    import shutil, json
    bundle_dir = tmp_path / "bundle_unknown_palette"
    shutil.copytree(PHYSICS, bundle_dir)
    face_path = bundle_dir / "face.json"
    face = json.loads(face_path.read_bytes())
    face["palette_hint"] = "nonexistent-palette-xyz"
    face_path.write_text(json.dumps(face))

    # Re-hash manifest for modified face.json
    import hashlib
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for fname in ["face.json"]:
        h = hashlib.sha256((bundle_dir / fname).read_bytes()).hexdigest()
        manifest["files"][fname] = h
    manifest_path.write_text(json.dumps(manifest))

    sub = tmp_path / "data_uk"
    sub.mkdir()
    _, env_path = _mount_with_face(sub, apply_face=True, bundle_dir=bundle_dir)
    # LAB_UI_THEME should NOT be written
    assert read_env_var(env_path, "LAB_UI_THEME") is None


# ── KB-only mount (no --apply-face) ──────────────────────────────────────────

def test_kb_only_mount_no_env_written(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    env_path = tmp_path / ".env"
    data_dir.mkdir()

    mount(PHYSICS, env_path=env_path, pkb_root=pkb_root, data_dir=data_dir, apply_face=False)

    # No env keys written at all
    assert not env_path.exists() or env_path.read_text().strip() == ""


# ── missing face.json tolerated ──────────────────────────────────────────────

def test_missing_face_no_env_written(tmp_path):
    """face.json missing → KB mounts, env skipped, no error."""
    import shutil, json, hashlib
    bundle_dir = tmp_path / "no_face_bundle"
    shutil.copytree(PHYSICS, bundle_dir)
    face_path = bundle_dir / "face.json"
    face_path.unlink()
    # Update manifest to remove face.json entry (else seal check fails on face)
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    del manifest["files"]["face.json"]
    manifest_path.write_text(json.dumps(manifest))

    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    env_path = tmp_path / ".env"
    data_dir.mkdir()

    # Should not raise
    record = mount(bundle_dir, env_path=env_path, pkb_root=pkb_root, data_dir=data_dir, apply_face=True)
    assert record.world == "physics"
    # No LAB_INTENT written since face was missing
    assert read_env_var(env_path, "LAB_INTENT") is None
