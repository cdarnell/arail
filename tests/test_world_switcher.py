"""World switcher — catalog discovery + nav dropdown + select endpoint.

Weights: 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression.

The switcher loads Worlds like aerollm loads LLMs: scan ``lab/worlds/``
(``list_available_worlds``), expose ``GET /api/worlds`` + ``POST
/api/worlds/select`` (mount / unmount, path-jailed, CSRF-guarded), and a
``<details>`` nav dropdown. Identity flips live on the next request (the
existing instant-flip foundation), so a successful select + page render shows
the World name/badge.

Tests point ``WORLDS_DIR`` at a tmp dir populated from
``tests/fixtures/world-bundles/`` via the
``_default_worlds_dir`` / ``_default_data_dir`` / ``_default_pkb_root``
monkeypatch idiom (same instance the autouse ``_no_ambient_world_mount`` uses →
our override wins).
"""

from __future__ import annotations

import pathlib
import shutil

import pytest
from fastapi.testclient import TestClient

from arail import world_mount as wm

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"
PHYSICS_NAME = "Physics — Measurement & Units"  # face.name surfaced by identity


def _worlds(tmp_path, monkeypatch, *names):
    """Populate a tmp worlds dir from fixtures and repoint the default dirs."""
    wd = tmp_path / "worlds"
    wd.mkdir()
    for n in names:
        # allow ("fixture", "dirname") tuples to place under a custom dir name
        if isinstance(n, tuple):
            src, dst = n
        else:
            src, dst = n, n
        shutil.copytree(FIXTURES / src, wd / dst)
    data = tmp_path / "data"
    pkb = tmp_path / "pkb"
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: wd)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    return wd, data, pkb


def _client():
    from arail.portal import app as portal_app
    return TestClient(portal_app.app)


# ════════════════════════════ DISCOVERY (setup ~30%) ════════════════════════

def test_discovery_finds_valid_world(tmp_path, monkeypatch):
    wd, data, _ = _worlds(tmp_path, monkeypatch, "physics")
    worlds = wm.list_available_worlds(wd, data_dir=data)
    assert len(worlds) == 1
    w = worlds[0]
    assert w.slug == "physics"
    assert w.valid is True
    assert w.mounted is False
    assert w.display_name == "Physics (Measurement & Units)"


def test_discovery_invalid_dir_listed_with_reason(tmp_path, monkeypatch):
    wd, data, _ = _worlds(tmp_path, monkeypatch, "physics")
    # A dir missing manifest.json → load_bundle raises PartialBundle → valid:false.
    junk = wd / "broken"
    junk.mkdir()
    (junk / "terms.json").write_text("{}")
    worlds = wm.list_available_worlds(wd, data_dir=data)
    by_slug = {w.slug: w for w in worlds}
    assert by_slug["broken"].valid is False
    assert by_slug["broken"].reason  # non-empty operator-facing reason
    assert by_slug["physics"].valid is True  # the scan was not aborted


def test_discovery_empty_dir(tmp_path, monkeypatch):
    wd, data, _ = _worlds(tmp_path, monkeypatch)  # empty worlds dir
    assert wm.list_available_worlds(wd, data_dir=data) == []


def test_discovery_missing_dir_no_crash(tmp_path, monkeypatch):
    monkeypatch.setattr(wm, "_default_data_dir", lambda: tmp_path / "data")
    missing = tmp_path / "does-not-exist"
    assert wm.list_available_worlds(missing, data_dir=tmp_path / "data") == []


def test_discovery_dedupes_by_slug(tmp_path, monkeypatch):
    # Two dirs, same slug (physics). First (sorted) wins; the rest invalid.
    wd, data, _ = _worlds(
        tmp_path, monkeypatch,
        ("physics", "aaa-physics"), ("physics", "zzz-physics"),
    )
    worlds = wm.list_available_worlds(wd, data_dir=data)
    valid = [w for w in worlds if w.valid]
    dupes = [w for w in worlds if not w.valid]
    assert len(valid) == 1
    assert len(dupes) == 1
    assert "duplicate" in dupes[0].reason


def test_discovery_includes_out_of_folder_current(tmp_path, monkeypatch):
    # Mount physics from the fixtures path, then scan an EMPTY worlds dir.
    wd, data, pkb = _worlds(tmp_path, monkeypatch)
    wm.mount(PHYSICS, pkb_root=pkb, data_dir=data)
    worlds = wm.list_available_worlds(wd, data_dir=data)
    assert len(worlds) == 1
    assert worlds[0].slug == "physics"
    assert worlds[0].mounted is True


# ════════════════════════════ GET /api/worlds ════════════════════════════════

def test_api_worlds_shape_default(tmp_path, monkeypatch):
    _worlds(tmp_path, monkeypatch, "physics")
    j = _client().get("/api/worlds").json()
    assert "worlds" in j and "current" in j
    assert j["current"] is None
    assert any(w["slug"] == "physics" for w in j["worlds"])
    # Every world dict carries a tagline key (welcome/picker story blurb).
    assert all("tagline" in w for w in j["worlds"])
    physics = next(w for w in j["worlds"] if w["slug"] == "physics")
    assert physics["tagline"].startswith("The SI spine")


def test_api_worlds_tagline_roundtrip_and_tolerance(tmp_path):
    from tests.world_bundle_builder import make_bundle
    wd = tmp_path / "worlds"
    wd.mkdir()
    make_bundle(wd, slug="withtag", display_name="With Tag")
    make_bundle(wd, slug="notag", display_name="No Tag",
                drop_face_keys=("tagline",))
    data = tmp_path / "data"; data.mkdir()
    worlds = {w.slug: w for w in wm.list_available_worlds(wd, data_dir=data)}
    assert worlds["withtag"].tagline == "A With Tag World."
    assert worlds["notag"].tagline == ""


def test_api_worlds_current_when_mounted(tmp_path, monkeypatch):
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    wm.mount(wd / "physics", pkb_root=pkb, data_dir=data)
    j = _client().get("/api/worlds").json()
    assert j["current"] == "physics"
    physics = next(w for w in j["worlds"] if w["slug"] == "physics")
    assert physics["mounted"] is True


# ════════════════════════ POST select (happy + Buddy ~30%) ═══════════════════

def test_select_slug_mounts_and_flips_identity(tmp_path, monkeypatch):
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    client = _client()
    r = client.post("/api/worlds/select", json={"slug": "physics"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "current": "physics"}
    # Staged dir present.
    assert (pkb / "sources" / "world-physics").exists()
    # Follow-up render shows the flipped identity.
    body = client.get("/").text
    assert "Physics — Measurement &amp; Units" in body
    assert "◆ Physics World" in body


def test_select_default_unmounts_and_reverts(tmp_path, monkeypatch):
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    client = _client()
    client.post("/api/worlds/select", json={"slug": "physics"})
    r = client.post("/api/worlds/select", json={"slug": "default"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "current": None}
    assert wm.current_mount(data) is None
    body = client.get("/").text
    assert "◇ AI Lab" in body
    assert "◆ Physics World" not in body


def test_switch_a_to_b_refused_record_stays_on_a(tmp_path, monkeypatch):
    # A and B are distinct bundle DIRS (same physics slug — fixtures are sealed
    # copies). In-place switching is removed: the select of B while A is
    # mounted is refused, A's record is untouched, and A's staged dir survives
    # (the anti-rmtree assertion is the point of this test).
    wd, data, pkb = _worlds(
        tmp_path, monkeypatch,
        ("physics", "world-a"), ("physics", "world-b"),
    )
    client = _client()
    client.post("/api/worlds/select", json={"path": str((wd / "world-a").resolve())})
    rec_a = wm.current_mount(data)
    assert rec_a.bundle_dir == str((wd / "world-a").resolve())
    r = client.post("/api/worlds/select", json={"path": str((wd / "world-b").resolve())})
    assert r.status_code == 409
    assert r.json()["error"] == "in_place_switch_removed"
    rec_after = wm.current_mount(data)
    assert rec_after.bundle_dir == str((wd / "world-a").resolve())  # still A
    assert (pkb / "sources" / "world-physics").exists()  # A's staged dir survives


# ════════════════════════════ SECURITY (~20%) ════════════════════════════════

def test_select_tampered_bundle_409_unchanged(tmp_path, monkeypatch):
    # Selected into an UNMOUNTED root, so the in_place_switch_removed guard
    # (which fires first when something else is mounted) doesn't shadow the
    # seal check this test exists to exercise.
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics", "tampered")
    client = _client()
    assert wm.current_mount(data) is None
    r = client.post(
        "/api/worlds/select",
        json={"path": str((wd / "tampered").resolve())},
    )
    assert r.status_code == 409
    assert r.json()["error"] == "mount_refused"
    assert r.json()["message"]
    assert wm.current_mount(data) is None  # still unmounted


def test_select_slug_traversal_rejected(tmp_path, monkeypatch):
    _worlds(tmp_path, monkeypatch, "physics")
    client = _client()
    r = client.post("/api/worlds/select", json={"slug": "../../etc"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_request"


def test_select_absolute_path_outside_jail_rejected(tmp_path, monkeypatch):
    _worlds(tmp_path, monkeypatch, "physics")
    client = _client()
    r = client.post("/api/worlds/select", json={"path": "/etc"})
    assert r.status_code == 400
    assert r.json()["error"] == "bad_request"


def test_api_worlds_lists_hostile_without_executing(tmp_path, monkeypatch):
    # The hostile fixture is DATA; listing it never executes anything.
    _worlds(tmp_path, monkeypatch, "hostile")
    j = _client().get("/api/worlds").json()
    assert isinstance(j["worlds"], list)  # scan completed, no crash


# ════════════════════════════ NAV RENDER (regression) ════════════════════════

def test_nav_renders_switcher_unmounted(tmp_path, monkeypatch):
    _worlds(tmp_path, monkeypatch, "physics")
    body = _client().get("/").text
    assert 'id="world-switcher"' in body
    assert 'id="world-menu"' in body
    assert "◇ AI Lab" in body


def test_nav_renders_active_badge_when_mounted(tmp_path, monkeypatch):
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    wm.mount(wd / "physics", pkb_root=pkb, data_dir=data)
    body = _client().get("/").text
    assert 'id="world-switcher"' in body
    assert "◆ Physics World" in body


# ═══════════════════ IN-PLACE SWITCH REMOVAL (ARCHITECTURE.md WP1) ═══════════

def test_swap_by_slug_while_mounted_refused(tmp_path, monkeypatch):
    # F7: refused when addressed by slug.
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics", "art-history-skill")
    client = _client()
    client.post("/api/worlds/select", json={"slug": "physics"})
    r = client.post("/api/worlds/select", json={"slug": "art-history-skill"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "in_place_switch_removed"
    assert "art-history-skill" in body["message"]
    assert "./arailctl start --world" in body["message"]
    assert wm.current_mount(data).world == "physics"


def test_swap_by_path_while_mounted_refused(tmp_path, monkeypatch):
    # F7: refused when addressed by path (world-a/world-b share the "physics"
    # slug, so the guard must compare resolved bundle dirs, not slugs).
    wd, data, pkb = _worlds(
        tmp_path, monkeypatch,
        ("physics", "world-a"), ("physics", "world-b"),
    )
    client = _client()
    client.post("/api/worlds/select", json={"path": str((wd / "world-a").resolve())})
    r = client.post("/api/worlds/select", json={"path": str((wd / "world-b").resolve())})
    assert r.status_code == 409
    assert r.json()["error"] == "in_place_switch_removed"
    assert wm.current_mount(data).bundle_dir == str((wd / "world-a").resolve())


def test_two_step_swap_unmount_then_mount_allowed(tmp_path, monkeypatch):
    # The explicitly-permitted two-step path: mount A, unmount, mount B.
    wd, data, pkb = _worlds(
        tmp_path, monkeypatch,
        ("physics", "world-a"), ("physics", "world-b"),
    )
    client = _client()
    client.post("/api/worlds/select", json={"path": str((wd / "world-a").resolve())})
    r_unmount = client.post("/api/worlds/select", json={"slug": "default"})
    assert r_unmount.status_code == 200
    assert wm.current_mount(data) is None
    r_mount_b = client.post("/api/worlds/select", json={"path": str((wd / "world-b").resolve())})
    assert r_mount_b.status_code == 200
    assert wm.current_mount(data).bundle_dir == str((wd / "world-b").resolve())


def test_rebind_identical_bundle_allowed(tmp_path, monkeypatch):
    # F6: re-selecting the same already-mounted bundle dir is an idempotent
    # re-index, not a switch — 200, not 409.
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    client = _client()
    client.post("/api/worlds/select", json={"slug": "physics"})
    r = client.post("/api/worlds/select", json={"slug": "physics"})
    assert r.status_code == 200
    assert r.json()["current"] == "physics"


def test_refused_swap_touches_nothing_on_disk(tmp_path, monkeypatch):
    # F4/F7: a refused swap must not mutate the mount record or the staged dir.
    wd, data, pkb = _worlds(
        tmp_path, monkeypatch,
        ("physics", "world-a"), ("physics", "world-b"),
    )
    client = _client()
    client.post("/api/worlds/select", json={"path": str((wd / "world-a").resolve())})
    record_path = data / "world-mount.json"
    before_bytes = record_path.read_bytes()
    staged = pkb / "sources" / "world-physics"
    before_mtime = staged.stat().st_mtime_ns

    r = client.post("/api/worlds/select", json={"path": str((wd / "world-b").resolve())})
    assert r.status_code == 409

    assert record_path.read_bytes() == before_bytes
    assert staged.stat().st_mtime_ns == before_mtime


def test_swap_precedence_instance_live_over_in_place_switch(tmp_path, monkeypatch):
    # Ordering ruling: instance_live is checked before in_place_switch_removed.
    from arail.portal import app as portal_app

    wd, data, pkb = _worlds(
        tmp_path, monkeypatch,
        ("physics", "world-a"), ("physics", "world-b"),
    )
    client = _client()
    client.post("/api/worlds/select", json={"path": str((wd / "world-a").resolve())})

    fake_record = {
        "slug": "world-b",
        "portal_port": 8090,
        "started_at": "2026-07-29T00:00:00Z",
    }
    monkeypatch.setattr(portal_app, "_read_instance_records", lambda: [fake_record])
    monkeypatch.setattr(portal_app, "_instance_record_alive", lambda rec: True)

    r = client.post("/api/worlds/select", json={"path": str((wd / "world-b").resolve())})
    assert r.status_code == 409
    assert r.json()["error"] == "instance_live"


def test_cross_site_swap_attempt_while_mounted_is_403(tmp_path, monkeypatch):
    # F2: the CSRF envelope still short-circuits before the new guard.
    wd, data, pkb = _worlds(
        tmp_path, monkeypatch,
        ("physics", "world-a"), ("physics", "world-b"),
    )
    client = _client()
    client.post("/api/worlds/select", json={"path": str((wd / "world-a").resolve())})
    r = client.post(
        "/api/worlds/select",
        json={"path": str((wd / "world-b").resolve())},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


def test_unmount_with_bundle_dir_deleted_still_frees_root(tmp_path, monkeypatch):
    # F3, the un-brick path: a mounted bundle dir vanishes from disk; unmount
    # (default) must still succeed and free the root.
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    client = _client()
    client.post("/api/worlds/select", json={"slug": "physics"})
    shutil.rmtree(wd / "physics")

    r = client.post("/api/worlds/select", json={"slug": "default"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "current": None}
    assert wm.current_mount(data) is None
