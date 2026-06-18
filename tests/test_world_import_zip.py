"""POST /api/worlds/import-zip — peer-sharing "drop a .zip a friend sent".

The .zip layer on top of /api/worlds/import (#96): an uploaded archive is
bounded + zip-slip/bomb-guarded, extracted to a throwaway staging dir, and the
resolved bundle root is handed to the SAME mount() seal gate. Same trust model,
one extra untrusted-input step in front.

Pins:
  - CSRF envelope: cross-site / cross-origin → 403 (parity with import/select).
  - Bad input: no file → 400; not-a-zip → 400; corrupt zip → 400 (bad_zip);
    zip-slip member → 400 (unsafe_zip).
  - Archive with no manifest.json → 409 (import_refused), nothing mounted.
  - Happy path (flat zip AND folder-wrapped zip): mounts AND lands in catalog.
"""
from __future__ import annotations

import io
import pathlib
import zipfile

import pytest
from fastapi.testclient import TestClient

from arail.portal import app as app_mod
from arail import world_mount as wm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"

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


# ── Helpers: build bundle zips in-memory ─────────────────────────────────────

def _zip_bytes(arcname_prefix: str = "") -> bytes:
    """Zip the physics fixture. ``arcname_prefix`` simulates a wrapping folder."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(PHYSICS.iterdir()):
            zf.write(f, arcname=f"{arcname_prefix}{f.name}")
    return buf.getvalue()


def _post_zip(client, data: bytes, name: str = "world.zip", headers=SAME_ORIGIN):
    return client.post("/api/worlds/import-zip",
                       files={"file": (name, data, "application/zip")},
                       headers=headers)


# ── CSRF envelope ────────────────────────────────────────────────────────────

def test_cross_site_refused(client):
    r = _post_zip(client, _zip_bytes(), headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


def test_cross_origin_refused(client):
    r = _post_zip(client, _zip_bytes(),
                  headers={"sec-fetch-site": "same-site",
                           "origin": "http://evil.example", "host": "testserver"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_origin"


# ── Bad input ────────────────────────────────────────────────────────────────

def test_no_file_is_400(client):
    r = client.post("/api/worlds/import-zip", headers=SAME_ORIGIN)
    assert r.status_code == 400
    assert r.json()["error"] == "no_file"


def test_not_a_zip_is_400(client):
    r = _post_zip(client, b"not a zip", name="notes.txt")
    assert r.status_code == 400
    assert r.json()["error"] == "not_a_zip"


def test_corrupt_zip_is_400(client):
    r = _post_zip(client, b"PK\x03\x04 garbage not really a zip")
    assert r.status_code == 400
    assert r.json()["error"] == "bad_zip"


def test_zip_slip_is_refused(client):
    """A member that escapes the staging dir is refused before extraction."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.txt", "pwned")
    r = _post_zip(client, buf.getvalue())
    assert r.status_code == 400
    assert r.json()["error"] == "unsafe_zip"


def test_non_bundle_zip_is_409(client, isolated):
    """A valid zip with no manifest.json is not a bundle → refused, nothing mounted."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "just some files")
    r = _post_zip(client, buf.getvalue())
    assert r.status_code == 409
    assert r.json()["error"] == "import_refused"
    _pkb, data, _worlds = isolated
    assert wm.current_mount(data) is None


# ── Happy path ───────────────────────────────────────────────────────────────

def test_flat_zip_imports_and_lands_in_catalog(client, isolated):
    pkb, data, worlds = isolated
    r = _post_zip(client, _zip_bytes())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["imported"] is True
    slug = body["current"]
    assert wm.current_mount(data).world == slug
    listed = {w.slug for w in wm.list_available_worlds(worlds_dir=worlds, data_dir=data)}
    assert slug in listed
    assert (worlds / slug).is_dir()


def test_folder_wrapped_zip_imports(client, isolated):
    """A zip that wraps the bundle in a top-level folder still mounts (anchor-found)."""
    pkb, data, worlds = isolated
    r = _post_zip(client, _zip_bytes(arcname_prefix="physics/"))
    assert r.status_code == 200, r.text
    assert r.json()["imported"] is True
    assert wm.current_mount(data).world == r.json()["current"]
