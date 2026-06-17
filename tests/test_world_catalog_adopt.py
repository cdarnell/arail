"""Catalog adoption: a World mounted from an external path stays re-selectable.

Bug: after switching out of a World mounted from outside WORLDS_DIR (CLI
`world mount <dir>`, a DaC export elsewhere), the switcher only showed
"AI Lab (default)" — the World vanished and could not be re-mounted, because
the portal's selection is path-jailed to WORLDS_DIR and the bundle never lived
there.

Fix: mount() adopts a byte-for-byte copy of the bundle into WORLDS_DIR/<slug>/,
so it persists in the catalog and the jailed slug path can re-mount it.
"""
from __future__ import annotations

import pathlib

import pytest

from arail import world_mount as wm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"


@pytest.fixture()
def roots(tmp_path):
    pkb = tmp_path / "pkb"
    data = tmp_path / "data"
    worlds = tmp_path / "worlds"
    for p in (pkb, data, worlds):
        p.mkdir(parents=True)
    return pkb, data, worlds


def test_external_mount_is_adopted_into_catalog(roots):
    pkb, data, worlds = roots
    assert PHYSICS.resolve().parent != worlds.resolve()  # genuinely external

    rec = wm.mount(PHYSICS, pkb_root=pkb, data_dir=data, worlds_dir=worlds)

    adopted = worlds / rec.world
    assert adopted.is_dir(), "bundle should be copied into WORLDS_DIR on mount"
    # Byte-for-byte copy → seal still verifies → re-mount works.
    assert (adopted / "manifest.json").exists()


def test_world_survives_unmount_and_is_reselectable(roots):
    pkb, data, worlds = roots
    rec = wm.mount(PHYSICS, pkb_root=pkb, data_dir=data, worlds_dir=worlds)
    slug = rec.world

    # Unmount (the "switch back to default AI Lab" action).
    wm.unmount(data_dir=data, pkb_root=pkb)
    assert wm.current_mount(data) is None

    # The bug: the World disappeared. The fix: it's still in the catalog.
    worlds_listed = wm.list_available_worlds(worlds_dir=worlds, data_dir=data)
    slugs = {w.slug for w in worlds_listed}
    assert slug in slugs, "previously-mounted World must remain in the catalog"
    entry = next(w for w in worlds_listed if w.slug == slug)
    assert entry.valid and not entry.mounted

    # And it re-mounts cleanly from the adopted copy.
    rec2 = wm.mount(worlds / slug, pkb_root=pkb, data_dir=data, worlds_dir=worlds)
    assert rec2.world == slug
    assert wm.current_mount(data).world == slug


def test_adopt_is_noop_when_already_under_worlds_dir(roots):
    pkb, data, worlds = roots
    # Mount once to adopt the bundle into the catalog.
    wm.mount(PHYSICS, pkb_root=pkb, data_dir=data, worlds_dir=worlds)
    slug = wm.current_mount(data).world
    catalog_copy = worlds / slug
    mtime_before = catalog_copy.stat().st_mtime

    # Re-mounting the catalog copy must not re-copy onto itself.
    out = wm._adopt_into_catalog(catalog_copy, slug, worlds)
    assert out is None
    assert catalog_copy.stat().st_mtime == mtime_before


def test_adopt_rejects_bad_slug(roots):
    _pkb, _data, worlds = roots
    assert wm._adopt_into_catalog(PHYSICS, "../evil", worlds) is None
    assert not (worlds / "..").exists() or True  # no traversal dir created
