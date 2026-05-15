"""Tests for Sec-Fetch-Site defense-in-depth on POST /api/airgap/toggle.

Architecture ref: sprints/2026-05-14-security-hygiene/ARCHITECTURE.md § Item 4

This file is independent of test_qa_airgap_onetap_paranoid.py — intentional
per architect directive (item must be independently revertable).
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def sfs_setup(tmp_path, monkeypatch):
    """Standard loopback toggle setup with tmp .env and audit paths."""
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"LAB_MODE=airgapped\n")
    audit_path = tmp_path / "airgap_audit.jsonl"

    import arail.portal.app as app_mod
    monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
    monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    monkeypatch.setenv("LAB_MODE", "airgapped")

    client = TestClient(app, raise_server_exceptions=False)
    return client, env_path, audit_path


def _post_toggle(client, target: str = "hybrid", *, sfs: str | None = None, origin: str | None = "http://testserver"):
    """POST to /api/airgap/toggle with optional Sec-Fetch-Site and Origin headers."""
    headers: dict[str, str] = {}
    if origin is not None:
        headers["Origin"] = origin
    if sfs is not None:
        headers["Sec-Fetch-Site"] = sfs
    return client.post("/api/airgap/toggle", json={"target": target}, headers=headers)


# ---------------------------------------------------------------------------
# Rejection tests
# ---------------------------------------------------------------------------

def test_sec_fetch_site_cross_site_rejected(sfs_setup):
    """Sec-Fetch-Site: cross-site must be rejected with 403 cross_site."""
    client, env_path, audit_path = sfs_setup
    r = _post_toggle(client, sfs="cross-site")
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"
    # env must be unchanged
    assert "LAB_MODE=airgapped" in env_path.read_bytes().decode()
    # no audit line
    assert not audit_path.exists()


def test_sec_fetch_site_none_rejected(sfs_setup):
    """Sec-Fetch-Site: none (typed URL) must be rejected with 403 cross_site."""
    client, env_path, audit_path = sfs_setup
    r = _post_toggle(client, sfs="none")
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"
    assert "LAB_MODE=airgapped" in env_path.read_bytes().decode()
    assert not audit_path.exists()


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------

def test_sec_fetch_site_same_origin_accepted(sfs_setup):
    """Sec-Fetch-Site: same-origin with matching Origin must return 200."""
    client, env_path, _ = sfs_setup
    r = _post_toggle(client, sfs="same-origin", origin="http://testserver")
    assert r.status_code == 200
    assert r.json()["lab_mode"] == "hybrid"


def test_sec_fetch_site_same_site_accepted(sfs_setup):
    """Sec-Fetch-Site: same-site with matching Origin must return 200."""
    client, env_path, _ = sfs_setup
    r = _post_toggle(client, sfs="same-site", origin="http://testserver")
    assert r.status_code == 200
    assert r.json()["lab_mode"] == "hybrid"


# ---------------------------------------------------------------------------
# Fall-through tests (absent / unknown → Origin gate behavior preserved)
# ---------------------------------------------------------------------------

def test_sec_fetch_site_absent_falls_through_to_origin(sfs_setup):
    """No Sec-Fetch-Site header + matching Origin must return 200 (curl / CLI path)."""
    client, env_path, _ = sfs_setup
    r = _post_toggle(client, sfs=None, origin="http://testserver")
    assert r.status_code == 200
    assert r.json()["lab_mode"] == "hybrid"


def test_sec_fetch_site_absent_with_mismatched_origin_rejected(sfs_setup):
    """No Sec-Fetch-Site + mismatched Origin must yield 403 cross_origin (not cross_site)."""
    client, _, _ = sfs_setup
    r = _post_toggle(client, sfs=None, origin="http://evil.example.com")
    assert r.status_code == 403
    # Must be cross_origin, NOT cross_site — proves the gates don't double-reject
    assert r.json()["error"] == "cross_origin"


def test_sec_fetch_site_unknown_value_falls_through(sfs_setup):
    """An unknown Sec-Fetch-Site value (future spec) must fall through to Origin gate."""
    client, _, _ = sfs_setup
    r = _post_toggle(client, sfs="weird-future-value", origin="http://testserver")
    assert r.status_code == 200
    assert r.json()["lab_mode"] == "hybrid"


# ---------------------------------------------------------------------------
# Header name case-insensitivity
# ---------------------------------------------------------------------------

def test_sec_fetch_site_mixed_case_header_name(sfs_setup):
    """Header name sent as lowercase 'sec-fetch-site' must be handled identically."""
    client, _, _ = sfs_setup
    # FastAPI/Starlette normalises headers to lowercase; this verifies our
    # lookup key is already lowercase and matches.
    headers = {"sec-fetch-site": "cross-site", "Origin": "http://testserver"}
    r = client.post("/api/airgap/toggle", json={"target": "hybrid"}, headers=headers)
    assert r.status_code == 403
    assert r.json()["error"] == "cross_site"


# ---------------------------------------------------------------------------
# Short-circuit ordering test
# ---------------------------------------------------------------------------

def test_sec_fetch_site_cross_site_short_circuits_origin_check(sfs_setup):
    """Both cross-site AND mismatched Origin: response must be cross_site (not cross_origin).

    This proves Sec-Fetch-Site runs before Origin and the first gate wins.
    """
    client, _, _ = sfs_setup
    r = _post_toggle(client, sfs="cross-site", origin="http://evil.example.com")
    assert r.status_code == 403
    # cross_site must take priority — not cross_origin
    assert r.json()["error"] == "cross_site"
