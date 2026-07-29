"""WP6 — GET /api/instance, GET /api/instances, the boot assertion, and
POST /api/worlds/select's 409 instance_live guard.

Covers ARCHITECTURE.md §5.1, §5.2, §6.4 (F14), §5.3 (F11).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient

from arail import world_mount as wm
from arail.portal import app as portal_app

FIXTURES_DIR = __import__("pathlib").Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES_DIR / "physics"


def _client():
    return TestClient(portal_app.app)


def _worlds(tmp_path, monkeypatch, *names):
    wd = tmp_path / "worlds"
    wd.mkdir()
    for n in names:
        shutil.copytree(FIXTURES_DIR / n, wd / n)
    data = tmp_path / "data"
    pkb = tmp_path / "pkb"
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: wd)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    return wd, data, pkb


def _write_registry(tmp_path, monkeypatch, slug, **fields):
    reg_dir = tmp_path / "lab" / "instances" / "registry.d"
    reg_dir.mkdir(parents=True, exist_ok=True)
    rec = {
        "schema": "arail.instance-registry/v1",
        "slug": slug,
        "display_name": f"{slug.title()} World",
        "checkout": str(tmp_path),
        "instance_root": str(tmp_path / "lab" / "instances" / slug),
        "data_dir": str(tmp_path / "lab" / "instances" / slug / "data"),
        "pkb_root": str(tmp_path / "lab" / "instances" / slug / "pkb"),
        "bind": "127.0.0.1",
        "portal_port": 9190,
        "lance_port": 9194,
        "launcher_pid": 999999,
        "portal_pid": 999999,
        "memory_pid": 999999,
        "token": "t",
        "started_at": "2026-07-28T00:00:00Z",
        "arailctl_version": "test",
    }
    rec.update(fields)
    (reg_dir / f"{slug}.json").write_text(json.dumps(rec), encoding="utf-8")
    monkeypatch.setattr(portal_app, "_instance_registry_dir", lambda: reg_dir)
    return reg_dir


# ---------------------------------------------------------------------------
# GET /api/instance
# ---------------------------------------------------------------------------

def test_api_instance_root_lab_shape(monkeypatch):
    monkeypatch.delenv("ARAIL_INSTANCE", raising=False)
    client = _client()
    r = client.get("/api/instance")
    assert r.status_code == 200
    j = r.json()
    assert j["slug"] == "root"
    assert j["world"] is None
    assert "checkout" in j and "data_root" in j and "portal_port" in j


def test_api_instance_world_shape_and_token(monkeypatch):
    monkeypatch.setenv("ARAIL_INSTANCE", "finance")
    monkeypatch.setenv("ARAIL_INSTANCE_TOKEN", "abc123")
    monkeypatch.setenv("PORTAL_PORT", "8090")
    monkeypatch.setenv("LAB_NAME", "Finance World")
    client = _client()
    r = client.get("/api/instance")
    assert r.status_code == 200
    j = r.json()
    assert j["slug"] == "finance"
    assert j["world"] == "finance"
    assert j["token"] == "abc123"
    assert j["portal_port"] == 8090
    assert j["display_name"] == "Finance World"


def test_api_instance_never_touches_disk_beyond_reads(monkeypatch, tmp_path):
    """Read-only — no side effects (§5.1)."""
    monkeypatch.delenv("ARAIL_INSTANCE", raising=False)
    before = set(tmp_path.rglob("*"))
    client = _client()
    client.get("/api/instance")
    after = set(tmp_path.rglob("*"))
    assert before == after


# ---------------------------------------------------------------------------
# GET /api/instances
# ---------------------------------------------------------------------------

def test_api_instances_roster_from_registry(tmp_path, monkeypatch):
    _write_registry(tmp_path, monkeypatch, "finance", portal_port=8090)
    client = _client()
    r = client.get("/api/instances")
    assert r.status_code == 200
    j = r.json()
    assert "instances" in j
    slugs = [row["slug"] for row in j["instances"]]
    assert "finance" in slugs
    finance = next(row for row in j["instances"] if row["slug"] == "finance")
    assert finance["portal_port"] == 8090
    # A registry record whose PID isn't actually running renders not-live —
    # no-network liveness (steps 1-3), no HTTP probe from a handler (§5.2).
    assert finance["live"] is False


def test_api_instances_empty_registry_is_empty_list(tmp_path, monkeypatch):
    reg_dir = tmp_path / "lab" / "instances" / "registry.d"
    monkeypatch.setattr(portal_app, "_instance_registry_dir", lambda: reg_dir)
    client = _client()
    r = client.get("/api/instances")
    assert r.status_code == 200
    assert r.json() == {"instances": []}


def test_api_instances_corrupt_record_skipped_not_crashed(tmp_path, monkeypatch):
    reg_dir = tmp_path / "lab" / "instances" / "registry.d"
    reg_dir.mkdir(parents=True)
    (reg_dir / "broken.json").write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(portal_app, "_instance_registry_dir", lambda: reg_dir)
    client = _client()
    r = client.get("/api/instances")
    assert r.status_code == 200
    assert r.json() == {"instances": []}


# ---------------------------------------------------------------------------
# Read-only: neither endpoint spawns a process (§5.3's "no HTTP endpoint
# spawns a process" — asserted by grep, per ARCHITECTURE.md §9 Security #3).
# ---------------------------------------------------------------------------

def test_instance_endpoints_never_spawn_a_process():
    import inspect
    src_instance = inspect.getsource(portal_app.api_instance)
    src_instances = inspect.getsource(portal_app.api_instances)
    for banned in ("subprocess.Popen", "os.system", "os.spawn", "os.exec"):
        assert banned not in src_instance, f"{banned} found in api_instance"
        assert banned not in src_instances, f"{banned} found in api_instances"


# ---------------------------------------------------------------------------
# Boot assertion (§6.4, F14)
# ---------------------------------------------------------------------------

def test_boot_assertion_passes_for_root_lab():
    """ARAIL_INSTANCE unset — the assertion is a no-op regardless of path
    shape, preserving today's CWD-relative-default behaviour exactly."""
    env = dict(os.environ)
    env.pop("ARAIL_INSTANCE", None)
    env.pop("ARAIL_ENV_FILE", None)
    result = subprocess.run(
        [sys.executable, "-c", "from arail.portal.app import app; print('OK')"],
        cwd=str(__import__("pathlib").Path(__file__).parent.parent),
        env={**env, "PYTHONPATH": "src"},
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OK" in result.stdout


def test_boot_assertion_fires_on_relative_path_in_instance(tmp_path):
    """ARAIL_INSTANCE set + a relative LAB_ROOT (the pack-writer regression
    this assertion exists to catch) -> import raises, naming the key."""
    env = dict(os.environ)
    env["ARAIL_INSTANCE"] = "finance"
    env["LAB_ROOT"] = "lab/instances/finance"  # relative — the regression
    env.pop("ARAIL_ENV_FILE", None)
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "-c", "from arail.portal.app import app"],
        cwd=str(__import__("pathlib").Path(__file__).parent.parent),
        env=env,
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0
    assert "LAB_ROOT" in result.stderr
    assert "boot assertion" in result.stderr.lower()


# ---------------------------------------------------------------------------
# POST /api/worlds/select -> 409 instance_live (§5.3, F11)
# ---------------------------------------------------------------------------

def test_select_refuses_when_target_world_has_a_live_instance(tmp_path, monkeypatch):
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    reg_dir = tmp_path / "lab" / "instances" / "registry.d"
    reg_dir.mkdir(parents=True)
    # A record whose PID IS this test process — genuinely alive, and a real
    # `ps` on this PID will contain "pytest"/"python", not our uvicorn
    # pattern, so drive _instance_record_alive via a direct monkeypatch
    # instead of relying on the real process's actual command line.
    (reg_dir / "physics.json").write_text(json.dumps({
        "slug": "physics", "display_name": "Physics World",
        "portal_port": 8090, "portal_pid": os.getpid(),
    }), encoding="utf-8")
    monkeypatch.setattr(portal_app, "_instance_registry_dir", lambda: reg_dir)
    monkeypatch.setattr(portal_app, "_instance_record_alive", lambda rec: rec.get("slug") == "physics")

    client = _client()
    r = client.post("/api/worlds/select", json={"slug": "physics"})
    assert r.status_code == 409
    assert r.json()["error"] == "instance_live"
    assert "physics" in r.json()["message"]
    # Nothing was mounted.
    assert wm.current_mount(data) is None


def test_select_still_works_when_target_world_has_no_live_instance(tmp_path, monkeypatch):
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    reg_dir = tmp_path / "lab" / "instances" / "registry.d"
    monkeypatch.setattr(portal_app, "_instance_registry_dir", lambda: reg_dir)
    client = _client()
    r = client.post("/api/worlds/select", json={"slug": "physics"})
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_select_instance_live_check_respects_csrf_envelope(tmp_path, monkeypatch):
    """A cross-site request is still blocked with 403 BEFORE the
    instance_live check ever runs — the new guard doesn't weaken CSRF."""
    wd, data, pkb = _worlds(tmp_path, monkeypatch, "physics")
    reg_dir = tmp_path / "lab" / "instances" / "registry.d"
    monkeypatch.setattr(portal_app, "_instance_registry_dir", lambda: reg_dir)
    monkeypatch.setattr(portal_app, "_instance_record_alive", lambda rec: True)
    client = _client()
    r = client.post(
        "/api/worlds/select",
        json={"slug": "physics"},
        headers={"sec-fetch-site": "cross-site"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"
