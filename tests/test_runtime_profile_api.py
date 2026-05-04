"""Integration tests for /api/runtime/profile."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from arail import runtime_profile as rp


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    monkeypatch.setattr(rp, "_STATE_PATH", tmp_path / "runtime_profile.json")
    rp._reset_for_tests()
    yield
    rp._reset_for_tests()


@pytest.fixture()
def client():
    from arail.portal.app import app
    return TestClient(app)


def test_get_returns_default_balanced(client, monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    r = client.get("/api/runtime/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["profile"] == "balanced"
    assert body["source"] == "default"
    assert body["params"]["airllm_max_tokens_cap"] == 512


def test_post_pin_throughput(client, monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    r = client.post("/api/runtime/profile", json={"profile": "throughput"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["profile"] == "throughput"
    assert body["source"] == "override"
    assert body["override_expires_in_sec"] is not None
    assert body["override_expires_in_sec"] > 0


def test_post_clear_via_auto(client, monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    rp.set_override("interactive")
    r = client.post("/api/runtime/profile", json={"auto": True})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["profile"] == "balanced"
    assert body["source"] == "default"
    assert body["override_expires_in_sec"] is None


def test_post_clear_via_null_profile(client, monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    rp.set_override("interactive")
    r = client.post("/api/runtime/profile", json={"profile": None})
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == "balanced"
    assert body["source"] == "default"


def test_post_invalid_profile_returns_error(client):
    r = client.post("/api/runtime/profile", json={"profile": "aggressive"})
    assert r.status_code == 200  # Mirrors set_mode pattern: 200 + ok=False
    body = r.json()
    assert body["ok"] is False
    assert "must be one of" in body["error"]


def test_post_emits_activity_event(client, monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    from arail.activity import activity_log
    r = client.post("/api/runtime/profile", json={"profile": "throughput"})
    assert r.status_code == 200
    # Buffer is a bounded deque; check the MOST RECENT event is ours,
    # not that the count grew (it caps at maxlen).
    last = list(activity_log._buffer)[-1]
    assert last["source"] == "profile"
    assert "throughput" in last["message"]
    assert last["data"]["profile"] == "throughput"


def test_presence_middleware_stamps_on_operator_hits(client, monkeypatch):
    """Hitting a non-skipped endpoint should mark presence."""
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "heavy")
    # Sanity: no presence yet, heavy window → throughput
    r0 = client.get("/api/runtime/profile")
    # /api/runtime/profile is in the skip list, so it should NOT mark presence
    assert r0.json()["source"] == "window"
    assert r0.json()["last_presence_sec_ago"] is None

    # Hit a non-skipped operator endpoint
    client.get("/api/system/mode")

    # Now the resolver should report presence-driven interactive
    r1 = client.get("/api/runtime/profile")
    assert r1.json()["profile"] == "interactive"
    assert r1.json()["source"] == "presence"
    assert r1.json()["last_presence_sec_ago"] is not None
    assert r1.json()["last_presence_sec_ago"] < 5


def test_presence_middleware_skips_streaming_paths(client, monkeypatch):
    """Skip-list paths must NOT mark presence."""
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    # Hit a path in the skip list a few times
    client.get("/api/runtime/profile")
    client.get("/api/runtime/profile")
    # No presence stamped → resolver still falls through to default
    r = client.get("/api/runtime/profile")
    assert r.json()["last_presence_sec_ago"] is None
    assert r.json()["source"] == "default"


def test_round_trip_pin_then_clear(client, monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "heavy")
    # Pin interactive
    r1 = client.post("/api/runtime/profile", json={"profile": "interactive"})
    assert r1.json()["profile"] == "interactive"
    # GET reflects override
    r2 = client.get("/api/runtime/profile")
    assert r2.json()["profile"] == "interactive"
    assert r2.json()["source"] == "override"
    # Clear via auto
    r3 = client.post("/api/runtime/profile", json={"auto": True})
    # Falls back to throughput because window=heavy
    assert r3.json()["profile"] == "throughput"
    assert r3.json()["source"] == "window"
