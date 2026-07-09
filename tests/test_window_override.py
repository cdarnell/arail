"""Window override — boundary math, persistence, endpoint gates.

Covers the work-window pin added for the toggleable status pill:
- next_boundary() edge selection incl. overnight ranges and exact-boundary
- set/get/clear override + expiry + JSON persistence round-trip
- current_window() honours the override; state() reports it
- POST /api/window/override — CSRF/loopback gates (same as airgap toggle),
  invalid body, happy path
- runtime_profile.resolve() picks up an overridden heavy window
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from arail import scheduler


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 14, hour, minute)


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    """Clean env, tmp override file, cleared override state per test."""
    for key in ("LAB_ACTIVE_HOURS", "LAB_HEAVY_HOURS"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "window_override.json"
    monkeypatch.setattr(scheduler, "_override_path", lambda: path)
    scheduler._reset_window_override_for_tests()
    yield
    scheduler._reset_window_override_for_tests()


# ── next_boundary ─────────────────────────────────────────────────────

def test_next_boundary_midday_defaults():
    # Defaults: active 08:00-22:00, heavy 22:00-08:00 → edges 08:00 / 22:00.
    assert scheduler.next_boundary(_at(12)) == _at(22)


def test_next_boundary_late_night_rolls_to_tomorrow():
    assert scheduler.next_boundary(_at(23)) == datetime(2026, 4, 15, 8, 0)


def test_next_boundary_exactly_on_edge_is_strictly_after():
    assert scheduler.next_boundary(_at(22)) == datetime(2026, 4, 15, 8, 0)


def test_next_boundary_custom_ranges(monkeypatch):
    monkeypatch.setenv("LAB_ACTIVE_HOURS", "09:00-17:00")
    monkeypatch.setenv("LAB_HEAVY_HOURS", "01:00-05:00")
    assert scheduler.next_boundary(_at(10)) == _at(17)
    assert scheduler.next_boundary(_at(18)) == datetime(2026, 4, 15, 1, 0)
    assert scheduler.next_boundary(_at(0, 30)) == _at(1)


# ── override lifecycle ────────────────────────────────────────────────

def test_override_wins_and_expires():
    rec = scheduler.set_window_override("heavy", now=_at(12))
    assert rec["expires_at"] == _at(22).isoformat(timespec="seconds")
    assert scheduler.current_window(_at(13)) == "heavy"
    # Past the boundary the schedule resumes (heavy default kicks in at 22).
    assert scheduler.get_window_override(_at(22)) is None
    assert scheduler.current_window(_at(22, 5)) == "heavy"  # scheduled heavy
    assert scheduler._ov is None  # self-cleared


def test_override_to_light_suppresses_heavy_window():
    scheduler.set_window_override("active", now=_at(23))
    assert scheduler.current_window(_at(23, 30)) == "active"


def test_override_rejects_idle():
    with pytest.raises(ValueError):
        scheduler.set_window_override("idle")


def test_clear_override():
    scheduler.set_window_override("heavy", now=_at(12))
    scheduler.clear_window_override()
    assert scheduler.get_window_override(_at(13)) is None
    assert scheduler.current_window(_at(13)) == "active"


def test_override_persists_across_reload():
    scheduler.set_window_override("heavy", now=_at(12))
    path = scheduler._override_path()
    assert json.loads(path.read_text())["window"] == "heavy"
    # Simulate a fresh process: drop in-memory state, force re-load.
    scheduler._ov = None
    scheduler._ov_loaded = False
    ov = scheduler.get_window_override(_at(13))
    assert ov is not None and ov["window"] == "heavy"


def test_expired_override_removes_file():
    scheduler.set_window_override("heavy", now=_at(12))
    assert scheduler.get_window_override(_at(23)) is None
    assert not scheduler._override_path().exists()


def test_state_reports_override():
    # state() evaluates against real now, so pin from real now too.
    scheduler.set_window_override("heavy", now=datetime.now())
    st = scheduler.state()
    assert st["override"]["window"] == "heavy"
    assert st["window"] == "heavy"
    scheduler.clear_window_override()
    assert scheduler.state()["override"] is None


# ── runtime_profile chain ─────────────────────────────────────────────

def test_resolve_picks_throughput_on_overridden_heavy(monkeypatch, tmp_path):
    from arail import runtime_profile as rp
    monkeypatch.setattr(rp, "_STATE_PATH", tmp_path / "runtime_profile.json")
    rp._reset_for_tests()
    scheduler.set_window_override("heavy", now=_at(12))
    profile, source = rp.resolve(_at(13))
    assert (profile, source) == ("throughput", "window")


# ── endpoint gates ────────────────────────────────────────────────────

@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient
    from arail.portal.app import app
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    return TestClient(app, raise_server_exceptions=False)


def test_endpoint_happy_path_and_clear(client):
    r = client.post("/api/window/override", json={"window": "heavy"},
                    headers={"Origin": "http://testserver"})
    assert r.status_code == 200
    body = r.json()
    assert body["window"] == "heavy"
    assert body["override"]["window"] == "heavy"

    r = client.post("/api/window/override", json={"window": None},
                    headers={"Origin": "http://testserver"})
    assert r.status_code == 200
    assert r.json()["override"] is None


def test_endpoint_invalid_window(client):
    r = client.post("/api/window/override", json={"window": "idle"})
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_window"


def test_endpoint_cross_site_rejected(client):
    r = client.post("/api/window/override", json={"window": "heavy"},
                    headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


def test_endpoint_cross_origin_rejected(client):
    r = client.post("/api/window/override", json={"window": "heavy"},
                    headers={"Origin": "http://evil.example"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_origin"


def test_endpoint_non_loopback_bind_rejected(client, monkeypatch):
    monkeypatch.setenv("BIND_ADDR", "0.0.0.0")
    r = client.post("/api/window/override", json={"window": "heavy"})
    assert r.status_code == 403
    assert r.json()["error"] == "bind_not_loopback"
