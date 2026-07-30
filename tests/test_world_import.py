"""POST /api/worlds/import — the consumer-side "Add a World" affordance.

Imports a sealed bundle from a path OUTSIDE WORLDS_DIR (a DaC export, a shared
World), with parity-with-select CSRF + the full mount seal gate, then adopts it
into the catalog so it persists in the switcher.

Pins:
  - CSRF envelope: cross-site / cross-origin → 403.
  - Bad input: missing path → 400; non-directory → 400.
  - Non-bundle dir → 409 (refused), nothing mounted.
  - Happy path: a real external bundle dir mounts AND lands in the catalog.
"""
from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from arail.portal import app as app_mod
from arail import world_mount as wm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"

# Same-origin headers the browser would send for a real fetch() from the portal.
SAME_ORIGIN = {"sec-fetch-site": "same-origin", "origin": "http://testserver",
               "host": "testserver"}


@pytest.fixture()
def client():
    return TestClient(app_mod.app)


@pytest.fixture()
def isolated(monkeypatch, tmp_path):
    """Point the default pkb/data/worlds dirs at tmp so import writes nowhere real."""
    pkb = tmp_path / "pkb"
    data = tmp_path / "data"
    worlds = tmp_path / "worlds"
    for p in (pkb, data, worlds):
        p.mkdir(parents=True)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    return pkb, data, worlds


# ── CSRF envelope ────────────────────────────────────────────────────────────

def test_cross_site_refused(client):
    r = client.post("/api/worlds/import",
                    json={"path": str(PHYSICS)},
                    headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


def test_cross_origin_refused(client):
    r = client.post("/api/worlds/import",
                    json={"path": str(PHYSICS)},
                    headers={"sec-fetch-site": "same-site",
                             "origin": "http://evil.example", "host": "testserver"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_origin"


# ── Bad input ────────────────────────────────────────────────────────────────

def test_missing_path_is_400(client):
    r = client.post("/api/worlds/import", json={}, headers=SAME_ORIGIN)
    assert r.status_code == 400
    assert r.json()["error"] == "bad_request"


def test_not_a_dir_is_400(client, tmp_path):
    f = tmp_path / "afile.txt"
    f.write_text("not a bundle")
    r = client.post("/api/worlds/import", json={"path": str(f)}, headers=SAME_ORIGIN)
    assert r.status_code == 400
    assert r.json()["error"] == "not_a_dir"


def test_non_bundle_dir_is_409(client, isolated, tmp_path):
    empty = tmp_path / "empty-dir"
    empty.mkdir()
    r = client.post("/api/worlds/import", json={"path": str(empty)},
                    headers=SAME_ORIGIN)
    assert r.status_code == 409
    assert r.json()["error"] == "import_refused"
    # Nothing mounted.
    _pkb, data, _worlds = isolated
    assert wm.current_mount(data) is None


# ── In-place switching removed (worlds-select-removal) ─────────────────────

def test_import_over_mounted_root_refused(client, isolated):
    # Import is a second door onto the same destructive sweep as select; it
    # gets the same in_place_switch_removed refusal when something else is
    # already mounted here.
    pkb, data, worlds = isolated
    r1 = client.post("/api/worlds/import", json={"path": str(PHYSICS)},
                     headers=SAME_ORIGIN)
    assert r1.status_code == 200, r1.text
    mounted_slug = r1.json()["current"]

    other = FIXTURES / "art-history-skill"
    r2 = client.post("/api/worlds/import", json={"path": str(other)},
                     headers=SAME_ORIGIN)
    assert r2.status_code == 409
    assert r2.json()["error"] == "in_place_switch_removed"
    assert wm.current_mount(data).world == mounted_slug  # unchanged


def test_import_reimport_identical_bundle_allowed(client, isolated):
    # mount() records bundle_dir as the resolved SOURCE path (pre-adoption),
    # so re-importing the same external path is the identical-bundle case.
    pkb, data, worlds = isolated
    r1 = client.post("/api/worlds/import", json={"path": str(PHYSICS)},
                     headers=SAME_ORIGIN)
    assert r1.status_code == 200, r1.text
    r2 = client.post("/api/worlds/import", json={"path": str(PHYSICS)},
                     headers=SAME_ORIGIN)
    assert r2.status_code == 200, r2.text


def test_reselect_by_slug_after_external_import_allowed(client, isolated):
    # REVIEW.md ASK-1: mount() records the SOURCE path pre-adoption, while
    # re-selecting the World by its catalog slug resolves to the ADOPTED
    # copy under WORLDS_DIR -- two different strings for one World. The
    # narrow fix allows the re-bind when cur.world == target_slug, even
    # though bundle_dir differs.
    pkb, data, worlds = isolated
    r1 = client.post("/api/worlds/import", json={"path": str(PHYSICS)},
                     headers=SAME_ORIGIN)
    assert r1.status_code == 200, r1.text
    slug = r1.json()["current"]
    assert (worlds / slug).is_dir()  # adopted into the catalog

    r2 = client.post("/api/worlds/select", json={"slug": slug},
                     headers=SAME_ORIGIN)
    assert r2.status_code == 200, r2.text
    assert r2.json()["current"] == slug


# ── Happy path ───────────────────────────────────────────────────────────────

def test_external_bundle_imports_and_lands_in_catalog(client, isolated):
    pkb, data, worlds = isolated
    assert PHYSICS.resolve().parent != worlds.resolve()  # genuinely external

    r = client.post("/api/worlds/import", json={"path": str(PHYSICS)},
                    headers=SAME_ORIGIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["imported"] is True
    slug = body["current"]

    # Mounted now…
    assert wm.current_mount(data).world == slug
    # …and adopted into the catalog so it persists in the switcher.
    listed = {w.slug for w in wm.list_available_worlds(worlds_dir=worlds, data_dir=data)}
    assert slug in listed
    assert (worlds / slug).is_dir()
