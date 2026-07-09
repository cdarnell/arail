"""Local trust-boundary middleware — anti-DNS-rebinding Host allowlist +
blanket CSRF on state-changing methods.

The portal has no auth; loopback is the trust boundary. These tests pin
the two browser-borne attacks the middleware closes:
  1. DNS rebinding (attacker domain rebound to 127.0.0.1) — blocked by the
     positive Host allowlist even though Origin would equal Host.
  2. Plain cross-origin state mutation — blocked by Sec-Fetch-Site / Origin.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    # The autouse conftest fixture already allows Host: testserver.
    return TestClient(app, raise_server_exceptions=False)


# ── Host allowlist (anti DNS-rebinding) ───────────────────────────────

def test_rebinding_host_is_rejected(client):
    """A rebound attacker domain (Host: evil.com, but connected to 127.0.0.1)
    is refused — this is the flip that a per-endpoint Origin==Host check
    would have let through."""
    r = client.post(
        "/api/airgap/toggle",
        json={"target": "hybrid"},
        headers={"Host": "evil.example.com",
                 "Origin": "http://evil.example.com",
                 "Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "untrusted_host"


def test_rebinding_host_blocks_even_get(client):
    r = client.get("/api/jobs/state", headers={"Host": "evil.example.com"})
    assert r.status_code == 403
    assert r.json()["error"] == "untrusted_host"


def test_loopback_host_allowed(client):
    r = client.get("/api/jobs/state", headers={"Host": "127.0.0.1:8080"})
    assert r.status_code == 200


def test_localhost_host_allowed(client):
    r = client.get("/api/jobs/state", headers={"Host": "localhost:8080"})
    assert r.status_code == 200


def test_extra_allowed_hosts_env(client, monkeypatch):
    monkeypatch.setenv("ARAIL_ALLOWED_HOSTS", "testserver, mylab.local")
    r = client.get("/api/jobs/state", headers={"Host": "mylab.local"})
    assert r.status_code == 200


def test_non_loopback_bind_accepts_its_own_host(client, monkeypatch):
    monkeypatch.setenv("BIND_ADDR", "192.168.1.50")
    monkeypatch.setenv("ARAIL_ALLOWED_HOSTS", "")  # rely on bind-host acceptance
    r = client.get("/api/jobs/state", headers={"Host": "192.168.1.50:8080"})
    assert r.status_code == 200


# ── Blanket CSRF on mutating methods ──────────────────────────────────

def test_cross_site_post_blocked_globally(client):
    """A cross-origin POST to a mutator that never opted into the
    per-endpoint gate is still refused by the global middleware."""
    r = client.post("/api/jobs/halt", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


def test_cross_origin_post_blocked_globally(client):
    r = client.post(
        "/api/jobs/halt",
        headers={"Origin": "http://evil.example", "Host": "testserver"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_origin"


def test_null_origin_post_blocked(client):
    r = client.post(
        "/api/window/override",
        json={"window": "heavy"},
        headers={"Origin": "null", "Host": "testserver"},
    )
    assert r.status_code == 403
    assert r.json()["error"] == "cross_origin"


def test_same_origin_post_allowed(client):
    r = client.post(
        "/api/window/override",
        json={"window": "heavy"},
        headers={"Origin": "http://testserver", "Host": "testserver",
                 "Sec-Fetch-Site": "same-origin"},
    )
    assert r.status_code == 200


def test_get_not_subject_to_csrf(client):
    # GET carries no CSRF risk for state; only the Host allowlist applies.
    r = client.get("/api/jobs/state", headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 200
