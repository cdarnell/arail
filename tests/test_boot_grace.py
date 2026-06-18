"""Boot-grace startup quiet window (ARAIL_BOOT_GRACE_SEC).

For the first hour after boot (default), the lab must NOT run automatic
"is anything out of date?" background work — the dashboard's quiet
update-check poll and the boot CVE scan — so initial startup stays smooth
and free of subprocess/network contention (git fetch, pip list --outdated,
GitHub release probes, pip-audit).

These tests pin:
  - boot_grace_seconds() parsing (default, override, bad value).
  - The /api/admin/check-updates GET poll returns a deferred no-op (and runs
    NO component subprocess) while inside the window, in hybrid mode.
  - Disabling the window (ARAIL_BOOT_GRACE_SEC=0) restores the probe.
  - Airgapped mode still short-circuits first (no behaviour change).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from arail.portal import app as app_mod


@pytest.fixture()
def client():
    return TestClient(app_mod.app)


# ---------------------------------------------------------------------------
# boot_grace_seconds() parsing
# ---------------------------------------------------------------------------

def test_grace_default_is_one_hour(monkeypatch):
    monkeypatch.delenv("ARAIL_BOOT_GRACE_SEC", raising=False)
    assert app_mod.boot_grace_seconds() == 3600


def test_grace_override(monkeypatch):
    monkeypatch.setenv("ARAIL_BOOT_GRACE_SEC", "120")
    assert app_mod.boot_grace_seconds() == 120


def test_grace_bad_value_falls_back(monkeypatch):
    monkeypatch.setenv("ARAIL_BOOT_GRACE_SEC", "not-a-number")
    assert app_mod.boot_grace_seconds() == 3600


def test_grace_zero_disables(monkeypatch):
    monkeypatch.setenv("ARAIL_BOOT_GRACE_SEC", "0")
    assert app_mod.boot_grace_seconds() == 0
    # _BOOT_PERF is in the past, so "within grace" is immediately False.
    assert app_mod._within_boot_grace() is False


def test_grace_negative_clamped(monkeypatch):
    monkeypatch.setenv("ARAIL_BOOT_GRACE_SEC", "-50")
    assert app_mod.boot_grace_seconds() == 0


# ---------------------------------------------------------------------------
# /api/admin/check-updates — the dashboard's quiet on-load poll
# ---------------------------------------------------------------------------

def test_check_updates_deferred_during_grace_runs_no_subprocess(
    client, monkeypatch
):
    """Inside the window, hybrid mode returns deferred + spawns NO subprocess."""
    monkeypatch.setattr(app_mod, "_lab_mode", lambda: "hybrid")
    monkeypatch.setattr(app_mod, "_within_boot_grace", lambda: True)

    import subprocess as sp

    def _boom(*a, **k):  # any component probe would call subprocess.run
        raise AssertionError("no subprocess should run during boot grace")

    monkeypatch.setattr(sp, "run", _boom)

    r = client.get("/api/admin/check-updates")
    assert r.status_code == 200
    body = r.json()
    assert body["deferred"] is True
    assert body["updates_available"] == 0
    assert body["airgapped"] is False


def test_check_updates_runs_after_grace(client, monkeypatch):
    """Outside the window, hybrid mode proceeds to the component probes."""
    monkeypatch.setattr(app_mod, "_lab_mode", lambda: "hybrid")
    monkeypatch.setattr(app_mod, "_within_boot_grace", lambda: False)

    r = client.get("/api/admin/check-updates")
    assert r.status_code == 200
    body = r.json()
    # Not deferred — it either found a components.json and probed, or reported
    # none found. Either way the grace short-circuit did not fire.
    assert body.get("deferred") is not True


def test_check_updates_airgapped_unaffected(client, monkeypatch):
    """Airgapped short-circuits before grace — unchanged behaviour."""
    monkeypatch.setattr(app_mod, "_lab_mode", lambda: "airgapped")
    monkeypatch.setattr(app_mod, "_within_boot_grace", lambda: True)
    r = client.get("/api/admin/check-updates")
    assert r.status_code == 200
    assert r.json()["airgapped"] is True
