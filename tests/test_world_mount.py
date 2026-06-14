"""Phase 1 tests: mount/unmount/swap atomicity + pointer.

Setup (30%) allocation:
- verify/mount/unmount/swap atomicity (pointer last, no orphan on staging fail)
- clean tmp_path end-to-end mount
- unmount removes pointer first
- swap keeps old on failure
"""

from __future__ import annotations

import json
import pathlib
import shutil

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"
TAMPERED = FIXTURES / "tampered"


from arail.world_mount import (
    MountRecord,
    SealMismatch,
    _mount_record_path,
    _staged_dir_path,
    current_mount,
    mount,
    swap,
    unmount,
)


# ── end-to-end mount ─────────────────────────────────────────────────────────

def test_mount_clean(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    record = mount(
        PHYSICS,
        pkb_root=pkb_root,
        data_dir=data_dir,
    )
    assert record.world == "physics"
    assert record.bundle_version == 1
    assert record.world_sha256 == "b91d525a4c412796789f1022c17290d484c35b5abd17693634ca2c340b5bc6a3"

    # Pointer written
    pointer = _mount_record_path(data_dir)
    assert pointer.exists()
    d = json.loads(pointer.read_text())
    assert d["world"] == "physics"


def test_mount_pointer_written_last(tmp_path, monkeypatch):
    """If staging fails, pointer must NOT be written."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    # Make staging fail by making sources dir a file
    sources = pkb_root / "sources"
    sources.mkdir(parents=True)
    (sources / "world-physics").write_text("I am a file not a dir")

    with pytest.raises(Exception):
        mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    pointer = _mount_record_path(data_dir)
    assert not pointer.exists(), "Pointer must NOT be written when staging fails"


def test_current_mount_returns_record(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    assert current_mount(data_dir) is None

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    record = current_mount(data_dir)
    assert record is not None
    assert record.world == "physics"


def test_current_mount_no_pointer(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assert current_mount(data_dir) is None


def test_current_mount_corrupt_pointer(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _mount_record_path(data_dir).write_text("not json {{{")
    # Should return None without raising
    assert current_mount(data_dir) is None


# ── unmount ──────────────────────────────────────────────────────────────────

def test_unmount_removes_pointer(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    assert _mount_record_path(data_dir).exists()

    was = unmount(data_dir=data_dir, pkb_root=pkb_root)
    assert was is True
    assert not _mount_record_path(data_dir).exists()


def test_unmount_when_not_mounted(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    was = unmount(data_dir=data_dir)
    assert was is False


def test_unmount_remove_staged(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    staged = pathlib.Path(record.staged_dir)
    assert staged.exists()

    unmount(data_dir=data_dir, pkb_root=pkb_root, remove_staged=True)
    assert not staged.exists()


def test_unmount_pointer_removed_first(tmp_path, monkeypatch):
    """Pointer removal happens before staged dir removal.
    Even if staged removal fails, pointer is already gone."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    # Monkeypatch shutil.rmtree to raise after pointer check
    import shutil as shutil_mod
    original_rmtree = shutil_mod.rmtree

    pointer_state_when_rmtree_called = []

    def fake_rmtree(path, *args, **kwargs):
        pointer_state_when_rmtree_called.append(_mount_record_path(data_dir).exists())
        original_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(shutil_mod, "rmtree", fake_rmtree)

    unmount(data_dir=data_dir, pkb_root=pkb_root, remove_staged=True)
    # Pointer was already removed when rmtree was called
    assert pointer_state_when_rmtree_called == [False]


# ── swap ─────────────────────────────────────────────────────────────────────

def test_swap_replaces_mount(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    # Mount physics first
    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    r1 = current_mount(data_dir)
    assert r1.world == "physics"

    # Swap to physics again (simulating a different version)
    r2 = swap(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    assert r2.world == "physics"

    # Pointer now points at new record
    r3 = current_mount(data_dir)
    assert r3.world == "physics"


def test_swap_keeps_old_on_failure(tmp_path):
    """If new bundle fails verification, old mount pointer is untouched."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    old_record = current_mount(data_dir)

    with pytest.raises(SealMismatch):
        swap(TAMPERED, pkb_root=pkb_root, data_dir=data_dir)

    # Old record still intact
    still_mounted = current_mount(data_dir)
    assert still_mounted is not None
    assert still_mounted.world_sha256 == old_record.world_sha256


# ── MountRecord round-trip ────────────────────────────────────────────────────

def test_mount_record_round_trip():
    r = MountRecord(
        world="physics",
        bundle_version=1,
        world_sha256="abc123",
        mounted_at="2026-06-13T00:00:00+00:00",
        bundle_dir="/tmp/bundle",
        staged_dir="/tmp/staged",
        pin={"world_sha256": "abc123"},
    )
    d = r.to_dict()
    r2 = MountRecord.from_dict(d)
    assert r2.world == "physics"
    assert r2.pin == {"world_sha256": "abc123"}
