"""QA pass — worlds-select-removal (sprint 2026-07-28-worlds-select-removal).

Allocation: 40% regression on the surviving paths, 30% edge cases on the new
guards, 20% security, 10% happy path.

The sprint's invariant under test: **one lab, one World** — no HTTP-reachable
door may mount a *different* World over one already bound in this root, because
``world_mount._sweep_other_worlds()`` ``rmtree``s the other World's staged KB
layer. WP1 + the review-fix pass guarded three doors (``/api/worlds/select``,
``/api/worlds/import``, ``/api/worlds/import-zip``). This file hunts the doors
nobody enumerated and re-pins the survivors.
"""

from __future__ import annotations

import json
import pathlib
import shutil
import time

import pytest
from fastapi.testclient import TestClient

import arail.world_forge as wf
import arail.world_mount as wm
from arail.portal import world_routes as wr

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"

CSRF = {"sec-fetch-site": "same-origin"}
CROSS_SITE = {"sec-fetch-site": "cross-site"}


def _client():
    from arail.portal.app import app
    return TestClient(app)


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    """Isolated worlds/data/pkb roots + a clean forge state machine."""
    worlds = tmp_path / "worlds"
    data = tmp_path / "data"
    pkb = tmp_path / "pkb"
    worlds.mkdir()
    data.mkdir()
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    wr._forge_state = {"state": "idle"}
    wr._forge_result = None
    yield tmp_path, worlds, data, pkb
    wr._forge_state = {"state": "idle"}
    wr._forge_result = None


def _copy_world(worlds: pathlib.Path, src: pathlib.Path, name: str) -> pathlib.Path:
    dst = worlds / name
    shutil.copytree(src, dst)
    return dst


def _staged_world_dirs(pkb: pathlib.Path) -> set[str]:
    src = pkb / "sources"
    if not src.is_dir():
        return set()
    return {p.name for p in src.iterdir() if p.name.startswith("world-")}


# ═════════════════ the fourth door: POST /api/worlds/forge/confirm ═══════════
# QA-1..QA-2. Regression class: same destructive in-place switch as the three
# doors this sprint closed, reachable in one click from the Forge UI
# (worlds.js:552) on a lab that already has a World bound.


def _fake_result(slug: str, subject: str):
    spec = {
        "slug": slug,
        "display_name": subject,
        "categories": [{"id": "a", "label": "A"}],
        "knowledge_sources": [{"kind": "model", "ref": "model:test",
                               "trust": "model-asserted", "holder": "test"}],
    }
    terms = [
        {"slug": "one", "term": "One", "category": "a", "short": "The first thing.",
         "definition": "A thing.", "example": "Like so.", "related": [],
         "source": "model:test"},
    ]
    gate = wf.assert_closed_sourced_graph(terms, {"a"})
    tier, counts = wf.compute_provenance_tier([t["source"] for t in terms])
    return wf.ForgeResult(spec=spec, terms=terms, gate=gate, tier=tier, counts=counts,
                          source_tag="model:test",
                          stats={"calls": 1, "elapsed_s": 0.1, "avg_edges": 0.0,
                                 "defined": 1, "total": 1, "repair_events": 0,
                                 "skill_chars": 400})


@pytest.fixture()
def fake_forge(monkeypatch):
    def _forge(params, *, router=None, progress_cb=None, cancel=None):
        if progress_cb:
            for stage in wf.FORGE_STAGES:
                progress_cb(stage, 1, 1, "")
        return _fake_result(params.slug, params.subject.title())
    monkeypatch.setattr(wr.wf, "forge_world", _forge)
    # The router is resolved before forge_world and, on an unbound lab, reaches
    # for a model hint over the network (blocked in airgapped test envs).
    # Stub it: this file is about the mount seam, not model selection.
    monkeypatch.setattr(wr, "_curation_router",
                        lambda brain="local": type("R", (), {"backend_name": "test"})())


def _forge_to_done(c, subject):
    r = c.post("/api/worlds/forge", json={"subject": subject}, headers=CSRF)
    assert r.status_code == 202, r.text
    t0 = time.time()
    while time.time() - t0 < 10:
        if c.get("/api/worlds/forge/status").json().get("state") == "done":
            return
        time.sleep(0.02)
    raise AssertionError("forge never reached 'done'")


@pytest.mark.xfail(
    strict=True,
    reason="QA-1 (HIGH): POST /api/worlds/forge/confirm calls wm.swap() when a "
           "DIFFERENT World is already mounted (world_routes.py:433) — an "
           "unguarded in-place World switch that sweeps the mounted World's "
           "staged KB layer. The three guarded doors were enumerated by hand and "
           "this one was missed. Flip to a plain assert when guarded.",
)
def test_forge_confirm_over_a_mounted_world_is_refused(lab, fake_forge):
    """A forge confirm must not switch the lab out of the World it is bound to."""
    _tmp, worlds, data, pkb = lab
    physics = _copy_world(worlds, PHYSICS, "physics")
    wm.mount(physics, pkb_root=pkb, data_dir=data)
    before = wm.current_mount()
    assert before is not None

    with _client() as c:
        _forge_to_done(c, "botany")
        r = c.post("/api/worlds/forge/confirm", headers=CSRF)

    assert r.status_code == 409, r.text
    assert r.json().get("error") == "in_place_switch_removed"
    cur = wm.current_mount()
    assert cur is not None and cur.world == before.world
    # the anti-rmtree assertion — the whole point of the sprint
    assert "world-physics" in _staged_world_dirs(pkb)


def test_forge_confirm_into_an_empty_root_still_mounts(lab, fake_forge):
    """Happy path / no over-refusal: forging on an unbound lab still binds it."""
    _tmp, _worlds, _data, pkb = lab
    assert wm.current_mount() is None
    with _client() as c:
        _forge_to_done(c, "botany")
        r = c.post("/api/worlds/forge/confirm", headers=CSRF)
    assert r.status_code == 200, r.text
    cur = wm.current_mount()
    assert cur is not None
    assert "world-botany" in _staged_world_dirs(pkb)


# ══════════════ the basename-keyed exemption (REVIEW.md's open INFO) ═════════


@pytest.mark.xfail(
    strict=True,
    reason="QA-2 (MEDIUM): the ASK-1 exemption compares cur.world (a World "
           "name) with target_slug (a DIRECTORY basename), app.py:3487. A "
           "validly-sealed bundle declaring a different slug, in a directory "
           "whose basename matches the mounted World, is mounted with 200 and "
           "_sweep_other_worlds() deletes the bound World's staged layer. "
           "REVIEW.md's open INFO rated this non-destructive; it is not. Flip "
           "to a plain assert when the mount record is canonicalised.",
)
def test_impostor_bundle_in_a_nested_dir_cannot_take_the_mounted_slug(lab):
    """QA-2: the ``cur.world == target_slug`` exemption keys on a *directory
    basename*, not on World identity.

    A bundle whose declared slug is NOT ``physics``, placed at
    ``lab/worlds/backup/physics`` (inside the jail, nested), matches the
    exemption by basename and mounts over the bound ``physics`` — and because
    ``_sweep_other_worlds`` keeps the *declared* slug of the incoming bundle,
    the mounted World's staged layer is deleted. REVIEW.md's INFO reasoned that
    this case "destroys nothing belonging to a different World (the sweep keeps
    that slug)"; this test pins whether that rationale holds. It does not.
    """
    from tests.world_bundle_builder import make_bundle

    _tmp, worlds, data, pkb = lab
    physics = make_bundle(worlds, slug="physics", display_name="Physics")
    wm.mount(physics, pkb_root=pkb, data_dir=data)
    assert "world-physics" in _staged_world_dirs(pkb)

    # A *validly sealed* impostor: declared slug "impostor", directory basename
    # "physics", nested inside the jail.
    nested = worlds / "backup"
    nested.mkdir()
    built = make_bundle(nested, slug="impostor", display_name="Impostor")
    impostor = nested / "physics"
    built.rename(impostor)

    with _client() as c:
        r = c.post("/api/worlds/select", json={"path": str(impostor)}, headers=CSRF)

    # Either the guard refuses it (correct), or the seal check refuses it
    # (also fine — the bundle was tampered with). What must NOT happen is a
    # 200 that sweeps the bound World away.
    assert r.status_code != 200, (
        "an impostor bundle matched the basename-keyed exemption and mounted "
        "over the bound World"
    )
    cur = wm.current_mount()
    assert cur is not None
    assert "world-physics" in _staged_world_dirs(pkb)


def test_trailing_slash_and_dotdot_paths_do_not_bypass_the_guard(lab):
    """Path-normalisation edge cases on the refusal side (F7 siblings)."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "world-a")
    b = _copy_world(worlds, PHYSICS, "world-b")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    variants = [str(b) + "/", str(b / "." ), str(worlds / "world-a" / ".." / "world-b")]
    with _client() as c:
        for v in variants:
            r = c.post("/api/worlds/select", json={"path": v}, headers=CSRF)
            assert r.status_code == 409, f"{v} -> {r.status_code} {r.text}"
            assert r.json()["error"] == "in_place_switch_removed", v
    assert wm.current_mount().bundle_dir == str(a.resolve())


def test_slug_and_path_together_still_refused(lab):
    """Both keys set: slug wins in _resolve_world_dir; neither may bypass."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "world-a")
    b = _copy_world(worlds, PHYSICS, "world-b")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        r = c.post("/api/worlds/select",
                   json={"slug": "world-b", "path": str(a)}, headers=CSRF)
    assert r.status_code == 409
    assert r.json()["error"] == "in_place_switch_removed"
    assert wm.current_mount().bundle_dir == str(a.resolve())


@pytest.mark.parametrize("bad_slug", [
    "",
    "   ",
    "../physics",
    "phys/../../etc",
    "physics\x00",
    "физика",
    "PHYSICS",
    "p" * 300,
])
def test_malformed_slugs_never_reach_mount_on_a_bound_lab(lab, bad_slug):
    """Security/edge: junk slugs get 400/409, never a mount, never a 500."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "physics")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        r = c.post("/api/worlds/select", json={"slug": bad_slug}, headers=CSRF)
    assert r.status_code in (400, 409), f"{bad_slug!r} -> {r.status_code}"
    assert wm.current_mount().bundle_dir == str(a.resolve())
    assert "world-physics" in _staged_world_dirs(pkb)


def test_non_dict_and_oversized_bodies_are_tolerated(lab):
    """Edge: array body, null body, and a huge path string — no 500, no mount."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "physics")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        for body in ([1, 2, 3], None, {"path": "/" + "a" * 5000}, {"slug": None}):
            r = c.post("/api/worlds/select", json=body, headers=CSRF)
            assert r.status_code in (400, 409), f"{str(body)[:40]} -> {r.status_code}"
    assert wm.current_mount() is not None


@pytest.mark.xfail(
    strict=True,
    reason="QA-3 (MEDIUM): the same basename-keyed exemption on "
           "/api/worlds/import (app.py:3589), where the path is NOT jailed and "
           "comes straight from the nav 'Add a World…' dialog rendered on every "
           "page. Importing a friend's bundle that merely SITS IN a folder named "
           "like the mounted World switches the lab and sweeps its staged layer. "
           "No hand-crafted path required — this is the UI-reachable form of "
           "QA-2. Flip to a plain assert when fixed.",
)
def test_import_of_a_foreign_bundle_in_a_same_named_folder_is_refused(lab, tmp_path):
    """QA-3: the UI-reachable form of the basename exemption."""
    from tests.world_bundle_builder import make_bundle

    _tmp, worlds, data, pkb = lab
    physics = make_bundle(worlds, slug="physics", display_name="Physics")
    wm.mount(physics, pkb_root=pkb, data_dir=data)

    # A friend's World, downloaded into ~/Downloads/physics/ — unrelated bundle,
    # colliding folder name. Nothing here is inside WORLDS_DIR.
    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    friend = make_bundle(downloads, slug="chemistry", display_name="Chemistry")
    friend.rename(downloads / "physics")

    with _client() as c:
        r = c.post("/api/worlds/import",
                   json={"path": str(downloads / "physics")}, headers=CSRF)

    assert r.status_code == 409, r.text
    assert r.json()["error"] == "in_place_switch_removed"
    assert wm.current_mount().world == "physics"
    assert "world-physics" in _staged_world_dirs(pkb)


# ═══════════════════════ survivors (regression, 40%) ═════════════════════════


def test_first_bind_into_an_empty_root(lab):
    _tmp, worlds, _data, pkb = lab
    _copy_world(worlds, PHYSICS, "physics")
    with _client() as c:
        r = c.post("/api/worlds/select", json={"slug": "physics"}, headers=CSRF)
    assert r.status_code == 200, r.text
    assert wm.current_mount() is not None
    assert "world-physics" in _staged_world_dirs(pkb)


def test_unbind_is_allowed_from_any_state_and_is_idempotent(lab):
    """Unmount must never 409 — it is the un-brick path (F1/F3)."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "physics")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        for _ in range(3):
            r = c.post("/api/worlds/select", json={"slug": "default"}, headers=CSRF)
            assert r.status_code == 200, r.text
            assert r.json()["current"] is None
    assert wm.current_mount() is None


def test_unbind_still_works_after_the_bundle_dir_is_deleted(lab):
    """The brick case (F3), re-pinned independently of the sprint's own test."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "physics")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    shutil.rmtree(a)
    with _client() as c:
        r = c.post("/api/worlds/select", json={"slug": "default"}, headers=CSRF)
    assert r.status_code == 200, r.text
    assert wm.current_mount() is None


def test_two_step_swap_is_the_permitted_path(lab):
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "world-a")
    _copy_world(worlds, PHYSICS, "world-b")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        assert c.post("/api/worlds/select", json={"slug": "default"},
                      headers=CSRF).status_code == 200
        r = c.post("/api/worlds/select", json={"slug": "world-b"}, headers=CSRF)
    assert r.status_code == 200, r.text
    assert wm.current_mount() is not None


def test_cross_site_is_refused_before_the_new_guard(lab):
    """Security (F2): the CSRF envelope must still short-circuit first."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "world-a")
    _copy_world(worlds, PHYSICS, "world-b")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        r = c.post("/api/worlds/select", json={"slug": "world-b"}, headers=CROSS_SITE)
        assert r.status_code == 403 and r.json()["error"] == "cross_site"
        r2 = c.post("/api/worlds/select", json={"slug": "world-b"},
                    headers={**CSRF, "origin": "http://evil.example"})
        assert r2.status_code == 403 and r2.json()["error"] == "cross_origin"
    assert wm.current_mount().bundle_dir == str(a.resolve())


def test_refusal_message_names_the_instance_command(lab):
    """The 409 must be actionable — it is the only place the user is told what
    replaced the removed affordance."""
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "world-a")
    _copy_world(worlds, PHYSICS, "world-b")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    with _client() as c:
        r = c.post("/api/worlds/select", json={"slug": "world-b"}, headers=CSRF)
    msg = r.json()["message"]
    assert "./arailctl start --world world-b" in msg
    assert "unmount" in msg.lower()


def test_refused_select_leaves_the_mount_record_byte_identical(lab):
    _tmp, worlds, data, pkb = lab
    a = _copy_world(worlds, PHYSICS, "world-a")
    _copy_world(worlds, PHYSICS, "world-b")
    wm.mount(a, pkb_root=pkb, data_dir=data)
    rec_path = next(p for p in data.rglob("world-mount.json"))
    before = rec_path.read_bytes()
    staged_before = _staged_world_dirs(pkb)
    with _client() as c:
        assert c.post("/api/worlds/select", json={"slug": "world-b"},
                      headers=CSRF).status_code == 409
    assert rec_path.read_bytes() == before
    assert _staged_world_dirs(pkb) == staged_before
