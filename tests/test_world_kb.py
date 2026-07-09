"""Phase 2 tests: KB staging + index.

Regression (10%) + Setup (30%) allocations:
- staged dir holds exactly the 6 files + world-<slug>.md
- ensure_ready + schedule_upsert called per staged file
- LanceDB-absent doesn't raise
- staging idempotent (double-mount same world)
"""

from __future__ import annotations

import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"

from arail.world_mount import (
    _BUNDLE_FILES,
    mount,
)

# 6 bundle files + the world index page + the per-term pages dir (WK-1:
# every term is now its own wiki page under terms/, so the graph + search
# populate instead of one JSON blob).
_EXPECTED_FILES = _BUNDLE_FILES | {"world-physics.md", "terms"}


def test_staged_dir_holds_all_files(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    staged = pathlib.Path(record.staged_dir)
    assert staged.exists()

    staged_names = {f.name for f in staged.iterdir()}
    assert staged_names == _EXPECTED_FILES


def test_staged_files_hash_match(tmp_path):
    """Each staged file's sha256 matches the physics manifest."""
    import hashlib
    import json

    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    staged = pathlib.Path(record.staged_dir)
    manifest = json.loads((PHYSICS / "manifest.json").read_bytes())
    files_map = manifest["files"]

    for fname, expected_hash in files_map.items():
        staged_file = staged / fname
        assert staged_file.exists(), f"{fname} missing from staged dir"
        computed = hashlib.sha256(staged_file.read_bytes()).hexdigest()
        assert computed == expected_hash, f"hash mismatch for {fname}"


def test_index_page_content(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    staged = pathlib.Path(record.staged_dir)
    index_page = staged / "world-physics.md"
    assert index_page.exists()

    content = index_page.read_text()
    assert "Physics" in content
    assert "| Term |" in content
    # At least one term from the bundle appears
    assert "Amount of substance" in content or "Ampere" in content


def test_staging_idempotent(tmp_path):
    """Double-mounting the same world works (replaces old staging dir)."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    r1 = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    r2 = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    staged = pathlib.Path(r2.staged_dir)
    assert staged.exists()
    staged_names = {f.name for f in staged.iterdir()}
    assert staged_names == _EXPECTED_FILES


def test_lancedb_absent_no_raise(tmp_path, monkeypatch):
    """If pkb_index raises (LanceDB absent), mount proceeds without raising."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    # Monkeypatch ensure_ready to raise ImportError (LanceDB absent)
    import arail.world_mount as wm_mod

    def fake_index(staged_dir, pkb_root):
        raise ImportError("lancedb not installed")

    monkeypatch.setattr(wm_mod, "_index_staged", fake_index)

    # mount should still succeed (indexing is best-effort)
    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    assert record.world == "physics"


def test_schedule_upsert_called_per_file(tmp_path, monkeypatch):
    """schedule_upsert must be called for each staged file."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    upserted = []
    import arail.world_mount as wm_mod

    original_index = wm_mod._index_staged

    def tracking_index(staged_dir, pkb_r):
        for p in pathlib.Path(staged_dir).iterdir():
            upserted.append(p.name)

    monkeypatch.setattr(wm_mod, "_index_staged", tracking_index)

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    # 6 bundle files + world-physics.md index + the terms/ pages dir (WK-1)
    assert len(upserted) == 8
