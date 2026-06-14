"""Face flip tests — NEW no-env contract.

Mounting a World writes NO ``.env``. Identity (name, logo, theme, intent,
framing, palette) resolves live from the mount sidecar via
``arail.identity.effective_identity``. These tests replace the former
``--apply-face`` env-write suite: they assert the identity the resolver reports
off the sidecar, and that no env file is ever written by ``mount()``.
"""

from __future__ import annotations

import pathlib

from arail.world_mount import mount
from arail.identity import effective_identity
from arail.brand import load_brand
from arail.ui_theme import default_ui_theme

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"


def _mount(tmp_path, bundle_dir=None):
    bundle_dir = bundle_dir or PHYSICS
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    env_path = tmp_path / ".env"
    data_dir.mkdir(exist_ok=True)
    record = mount(bundle_dir, pkb_root=pkb_root, data_dir=data_dir)
    return record, data_dir, env_path


# ── face flip is reflected by the resolver (no env) ───────────────────────────

def test_mount_intent_is_other(tmp_path):
    _, data_dir, _ = _mount(tmp_path)
    assert effective_identity(data_dir).intent == "other"


def test_mount_intent_name_set(tmp_path):
    _, data_dir, _ = _mount(tmp_path)
    val = effective_identity(data_dir).intent_name
    assert val and len(val) > 0


def test_mount_intent_description_is_domain_framing(tmp_path):
    import json
    _, data_dir, _ = _mount(tmp_path)
    face = json.loads((PHYSICS / "face.json").read_bytes())
    assert effective_identity(data_dir).intent_description == face["domain_framing"]


def test_mount_lab_theme_is_face_name(tmp_path):
    import json
    _, data_dir, _ = _mount(tmp_path)
    face = json.loads((PHYSICS / "face.json").read_bytes())
    assert effective_identity(data_dir).lab_theme == face["name"]


def test_mount_ui_theme_for_known_palette(tmp_path):
    # physics face.json palette_hint="blue-cyan-lab" resolves to that preset.
    _, data_dir, _ = _mount(tmp_path)
    assert effective_identity(data_dir).ui_theme.id == "blue-cyan-lab"


def test_mount_writes_no_env(tmp_path):
    """The old --apply-face wrote 5 keys; mount now writes ZERO."""
    _, _, env_path = _mount(tmp_path)
    assert not env_path.exists()


# ── brand untouched: operator .env is never written ───────────────────────────

def test_mount_does_not_write_lab_name(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LAB_NAME=MyLab\n")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    # operator .env is physically untouched
    assert env_path.read_text() == "LAB_NAME=MyLab\n"
    # but the resolver reports the World name from the sidecar
    assert effective_identity(data_dir).name == "Physics — Measurement & Units"


def test_mount_does_not_write_lab_logo(tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LAB_LOGO=mylogo.png\n")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    assert env_path.read_text() == "LAB_LOGO=mylogo.png\n"


# ── unknown palette falls back to default theme (no error) ────────────────────

def test_unknown_palette_falls_back_to_default(tmp_path):
    import shutil, json, hashlib
    bundle_dir = tmp_path / "bundle_unknown_palette"
    shutil.copytree(PHYSICS, bundle_dir)
    face_path = bundle_dir / "face.json"
    face = json.loads(face_path.read_bytes())
    face["palette_hint"] = "nonexistent-palette-xyz"
    face_path.write_text(json.dumps(face))

    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    for fname in ["face.json"]:
        h = hashlib.sha256((bundle_dir / fname).read_bytes()).hexdigest()
        manifest["files"][fname] = h
    manifest_path.write_text(json.dumps(manifest))

    sub = tmp_path / "sub"
    sub.mkdir()
    _, data_dir, _ = _mount(sub, bundle_dir=bundle_dir)
    assert effective_identity(data_dir).ui_theme == default_ui_theme()


# ── missing face.json tolerated: KB mounts, identity falls back per field ─────

def test_missing_face_falls_back_to_operator_brand(tmp_path):
    """face.json missing → KB mounts (tolerated-partial), no error, and identity
    falls back to the operator brand per field."""
    import shutil, json
    bundle_dir = tmp_path / "no_face_bundle"
    shutil.copytree(PHYSICS, bundle_dir)
    (bundle_dir / "face.json").unlink()
    manifest_path = bundle_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    del manifest["files"]["face.json"]
    manifest_path.write_text(json.dumps(manifest))

    sub = tmp_path / "sub"
    sub.mkdir()
    record, data_dir, env_path = _mount(sub, bundle_dir=bundle_dir)
    assert record.world == "physics"
    ident = effective_identity(data_dir)
    assert ident.mounted is True
    assert ident.name == load_brand().name        # name falls back
    assert ident.intent_description == ""          # framing falls back
    assert not env_path.exists()                   # still no env written
