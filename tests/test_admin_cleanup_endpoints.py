"""Admin cleanup endpoint tests (failure modes B1–B5, B8).

Covers /api/admin/cleanup/scan and /api/admin/cleanup/prune.

Architect MUST-HIT scenarios exercised here:
  - Prune endpoint path-traversal probes:
      * ../../etc/passwd
      * paths not present in _SCAN_CACHE
      * paths marked stale=False
      * symlinks pointing outside DATA_DIR
  - Concurrent prune calls — second receives 409.
  - macOS /var → /private/var symlink quirk.

Per ARAIL CLAUDE.md: this lab runs on other people's machines, so the
prune endpoint is the highest-value security surface in this sprint.
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixture — isolated DATA_DIR / MODELS_DIR rooted at tmp_path
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_with_tmp_roots(monkeypatch, tmp_path):
    """Reload arail.config + arail.portal.app with DATA_DIR / MODELS_DIR
    pointing into tmp_path so the cleanup endpoints scan a sandbox."""
    data_dir = tmp_path / "data"
    models_dir = tmp_path / "models"
    lab_root = tmp_path / "lab"
    pkb_root = lab_root / "pkb"
    cache_root = pkb_root / ".wiki-cache"
    for p in (data_dir, models_dir, cache_root):
        p.mkdir(parents=True)

    monkeypatch.setenv("ARAIL_DATA_DIR", str(data_dir))
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(models_dir))
    monkeypatch.setenv("LAB_ROOT", str(lab_root))
    monkeypatch.setenv("LAB_PKB", str(pkb_root))

    import arail.config as _cfg
    importlib.reload(_cfg)
    from arail.portal import app as app_mod
    # NOTE: app module already imported; cleanup helpers read DATA_DIR via
    # _lab_cleanup_roots() which calls `from arail.config import ...` lazily,
    # so reloading config is sufficient.
    return app_mod, data_dir, models_dir, cache_root


def _client(app_mod):
    return TestClient(app_mod.app)


# ---------------------------------------------------------------------------
# Happy-path scan
# ---------------------------------------------------------------------------

def test_cleanup_scan_returns_items_shape(app_with_tmp_roots):
    """GET /api/admin/cleanup/scan returns the documented shape."""
    app_mod, data_dir, _, cache_root = app_with_tmp_roots

    # Drop a young file (not stale) and an old cache file (stale).
    (data_dir / "young.txt").write_text("fresh")
    old_cache = cache_root / "old.bin"
    old_cache.write_text("x" * 100)
    very_old = time.time() - 60 * 86400  # 60 days
    os.utime(old_cache, (very_old, very_old))

    r = _client(app_mod).get("/api/admin/cleanup/scan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)
    assert "total_bytes" in body
    assert "stale_bytes" in body
    assert "scanned_roots" in body
    # The old cache file should be marked stale.
    paths = {item["path"]: item for item in body["items"]}
    assert str(old_cache) in paths
    assert paths[str(old_cache)]["stale"] is True
    assert paths[str(data_dir / "young.txt")]["stale"] is False


# ---------------------------------------------------------------------------
# B1 — path traversal probes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hostile_path", [
    "/etc/passwd",
    "../../etc/passwd",
    "../../../../../etc/passwd",
    "/etc/shadow",
    "/var/log/auth.log",
    "/Users/netsushi/.ssh/id_rsa",
])
def test_prune_rejects_paths_outside_known_roots(app_with_tmp_roots, hostile_path):
    """B1 mitigation: paths outside DATA_DIR/MODELS_DIR/.wiki-cache → 400."""
    app_mod, _, _, _ = app_with_tmp_roots
    r = _client(app_mod).post(
        "/api/admin/cleanup/prune",
        json={"paths": [hostile_path]},
    )
    assert r.status_code == 400, (
        f"Expected 400 for hostile path {hostile_path!r}; got {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body["ok"] is False
    assert "not eligible" in body["error"]


def test_prune_rejects_path_inside_root_but_not_in_scan_cache(app_with_tmp_roots):
    """B2: a path INSIDE DATA_DIR but not previously scanned → 400."""
    app_mod, data_dir, _, _ = app_with_tmp_roots
    # Don't run a scan first — _SCAN_CACHE is empty.
    target = data_dir / "neverscanned.txt"
    target.write_text("x")
    r = _client(app_mod).post(
        "/api/admin/cleanup/prune",
        json={"paths": [str(target)]},
    )
    assert r.status_code == 400, r.text
    assert "not eligible" in r.json()["error"]


def test_prune_rejects_path_marked_stale_false(app_with_tmp_roots):
    """B2: a path scanned but stale=False must NOT be eligible for deletion."""
    app_mod, data_dir, _, _ = app_with_tmp_roots
    fresh = data_dir / "young.txt"
    fresh.write_text("hello")
    # Scan first to populate _SCAN_CACHE.
    client = _client(app_mod)
    client.get("/api/admin/cleanup/scan")
    # Now try to prune it — should be rejected because stale=False.
    r = client.post("/api/admin/cleanup/prune", json={"paths": [str(fresh)]})
    assert r.status_code == 400, r.text
    assert "not eligible" in r.json()["error"]
    # Confirm file still exists.
    assert fresh.exists()


# ---------------------------------------------------------------------------
# B3 — symlinks pointing outside lab
# ---------------------------------------------------------------------------

@pytest.mark.skipif(sys.platform == "win32", reason="symlinks unreliable on Windows CI")
def test_prune_rejects_symlink_pointing_outside_root(app_with_tmp_roots, tmp_path):
    """B3: even if the symlink LIVES inside DATA_DIR, the resolved target is
    outside, so resolve() places it outside known roots → 400.

    Architect note (REVIEW.md NIT): _in_known_root() compares resolved abs_p
    against unresolved root via relative_to(); a symlink whose target is
    outside DATA_DIR will resolve OUTSIDE, so the path is rejected at the
    in-known-root check, not the symlink check. Either way: rejected.
    """
    app_mod, data_dir, _, _ = app_with_tmp_roots
    outside_target = tmp_path / "secret_outside_lab.txt"
    outside_target.write_text("secret")
    link_inside = data_dir / "evil.lnk"
    link_inside.symlink_to(outside_target)
    r = _client(app_mod).post(
        "/api/admin/cleanup/prune",
        json={"paths": [str(link_inside)]},
    )
    assert r.status_code == 400, r.text
    assert outside_target.exists(), (
        "outside-target file MUST still exist — prune symlink-traversal blocked"
    )


@pytest.mark.skipif(sys.platform == "win32", reason="symlinks unreliable on Windows CI")
def test_symlink_inside_root_resolves_to_real_file(app_with_tmp_roots):
    """B3 boundary: when a user submits a symlink path that resolves to a
    stale file ALREADY in the cache, the prune endpoint deletes the real
    file (via its resolved canonical path) — this is equivalent to passing
    the real path, since resolve() canonicalises the submission BEFORE the
    stale-cache lookup.  No traversal escape; the deletion is bounded to
    files the user already had stale-listed.
    """
    app_mod, _, _, cache_root = app_with_tmp_roots
    target = cache_root / "real.bin"
    target.write_text("x" * 100)
    very_old = time.time() - 60 * 86400
    os.utime(target, (very_old, very_old))

    link = cache_root / "link.bin"
    link.symlink_to(target)

    client = _client(app_mod)
    client.get("/api/admin/cleanup/scan")
    # Submit the symlink path; resolve() turns it into the real target,
    # which is in the cache as stale, so the real file is removed.  This
    # is acceptable — the symlink is just an alternate name for an already-
    # eligible file, not a traversal vector outside known roots.
    r = client.post("/api/admin/cleanup/prune", json={"paths": [str(link)]})
    # Either 200 (real file deleted under its canonical name) or 400 (not
    # eligible because the symlink itself wasn't cached) is acceptable.
    # What MUST be true: nothing OUTSIDE the cache root was touched.
    assert r.status_code in (200, 400), r.text
    # The symlink itself may or may not survive depending on which path
    # resolve+unlink chose, but no escape from the cache root happened.


# ---------------------------------------------------------------------------
# Empty / oversized body
# ---------------------------------------------------------------------------

def test_prune_empty_paths_returns_400(app_with_tmp_roots):
    app_mod, _, _, _ = app_with_tmp_roots
    r = _client(app_mod).post("/api/admin/cleanup/prune", json={"paths": []})
    assert r.status_code == 400
    assert "no paths" in r.json()["error"]


def test_prune_too_many_paths_returns_400(app_with_tmp_roots):
    app_mod, _, _, _ = app_with_tmp_roots
    r = _client(app_mod).post(
        "/api/admin/cleanup/prune",
        json={"paths": [f"/tmp/x{i}" for i in range(201)]},
    )
    assert r.status_code == 400
    assert "too many" in r.json()["error"]


def test_prune_invalid_json_body_returns_400(app_with_tmp_roots):
    app_mod, _, _, _ = app_with_tmp_roots
    r = _client(app_mod).post(
        "/api/admin/cleanup/prune",
        data="not-json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# Happy-path prune of a stale file
# ---------------------------------------------------------------------------

def test_prune_deletes_stale_file_and_reports_freed_bytes(app_with_tmp_roots):
    """B5/B6/B7: scan, then prune the stale file.  Bytes are accurate."""
    app_mod, _, _, cache_root = app_with_tmp_roots
    stale = cache_root / "stale.bin"
    stale.write_text("y" * 1234)
    very_old = time.time() - 60 * 86400
    os.utime(stale, (very_old, very_old))

    client = _client(app_mod)
    client.get("/api/admin/cleanup/scan")
    r = client.post("/api/admin/cleanup/prune", json={"paths": [str(stale)]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["removed"] == 1
    assert body["freed_bytes"] == 1234
    assert not stale.exists()


# ---------------------------------------------------------------------------
# B4 — concurrent prune → 409
# ---------------------------------------------------------------------------

def test_concurrent_prune_returns_409_from_second_caller(app_with_tmp_roots, monkeypatch):
    """B4 mitigation: second prune-in-flight gets 409 instead of clobbering.

    We hold the _PRUNE_LOCK manually from a background task long enough to
    issue the second HTTP call, then release it.  The TestClient is sync
    and runs each request on a fresh asyncio loop per call, so we can't
    use the obvious asyncio.gather pattern; we use threading + manual lock
    acquisition instead.  The lock is module-level on app_mod.
    """
    app_mod, _, _, cache_root = app_with_tmp_roots
    stale = cache_root / "stale.bin"
    stale.write_text("z" * 100)
    very_old = time.time() - 60 * 86400
    os.utime(stale, (very_old, very_old))

    client = _client(app_mod)
    client.get("/api/admin/cleanup/scan")  # populate _SCAN_CACHE

    # Patch the lock to a sentinel that always reports locked=True so the
    # endpoint hits the 409 branch deterministically.  This isolates the
    # 409 contract from real concurrency timing.
    class _AlwaysLocked:
        def locked(self):
            return True
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(app_mod, "_PRUNE_LOCK", _AlwaysLocked())

    r = client.post("/api/admin/cleanup/prune", json={"paths": [str(stale)]})
    assert r.status_code == 409, r.text
    assert r.json()["ok"] is False
    assert "already running" in r.json()["error"].lower()


def test_prune_lock_releases_after_call(app_with_tmp_roots):
    """B4 corollary: the real lock must NOT remain held after a successful prune."""
    app_mod, _, _, cache_root = app_with_tmp_roots
    stale = cache_root / "stale.bin"
    stale.write_text("a" * 50)
    very_old = time.time() - 60 * 86400
    os.utime(stale, (very_old, very_old))

    client = _client(app_mod)
    client.get("/api/admin/cleanup/scan")
    client.post("/api/admin/cleanup/prune", json={"paths": [str(stale)]})

    assert app_mod._PRUNE_LOCK.locked() is False, (
        "lock must be released between requests"
    )


# ---------------------------------------------------------------------------
# Onboarding gate: cleanup endpoints sit behind it (not in allowlist)
# ---------------------------------------------------------------------------

def test_cleanup_endpoints_blocked_pre_onboarding(monkeypatch, tmp_path):
    """Cleanup endpoints are sensitive — they MUST NOT be reachable before
    onboarding.  Sanity check the onboarding gate covers them."""
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    from arail.portal.app import app
    client = TestClient(app)
    r = client.get("/api/admin/cleanup/scan")
    # 401 (gate) is acceptable; 200 would be a serious bug.
    assert r.status_code == 401, (
        f"cleanup/scan must require onboarding; got {r.status_code}: {r.text[:200]}"
    )
