"""Full endpoint test matrix for POST /api/airgap/toggle.

ARCHITECTURE.md §9 test_airgap_toggle_endpoint.py:
Uses fastapi.testclient.TestClient. Each test sets BIND_ADDR and LAB_MODE
via monkeypatch.setenv and points the writer at a temp .env.

Tests:
- test_toggle_happy_two_step
- test_toggle_invalid_target
- test_toggle_missing_target
- test_toggle_bind_gate_lan
- test_toggle_bind_gate_ipv4_lan
- test_toggle_bind_gate_ipv6_loopback_ok
- test_toggle_token_expired
- test_toggle_token_replay
- test_toggle_token_wrong_target
- test_toggle_cross_origin
- test_toggle_writer_failure
- test_toggle_audit_log_shape
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def toggle_setup(tmp_path, monkeypatch):
    """Wire the endpoint to use tmp_path .env and audit log."""
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


def _two_step(client, target: str, extra_headers: dict | None = None) -> tuple:
    """Issue the two-step toggle flow. Returns (r1, r2) tuple."""
    headers = {"Origin": "http://testserver"}
    if extra_headers:
        headers.update(extra_headers)
    r1 = client.post("/api/airgap/toggle", json={"target": target}, headers=headers)
    if r1.status_code != 409:
        return r1, None
    token = r1.json().get("confirm_token")
    r2 = client.post(
        "/api/airgap/toggle",
        json={"target": target, "confirm_token": token},
        headers=headers,
    )
    return r1, r2


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestToggleHappyPath:
    def test_toggle_happy_two_step(self, toggle_setup):
        """POST without token -> 409 + token; POST with token -> 200."""
        client, env_path, audit_path = toggle_setup

        r1, r2 = _two_step(client, "hybrid")

        assert r1.status_code == 409
        b1 = r1.json()
        assert b1["error"] == "need_confirm"
        assert "confirm_token" in b1
        assert b1["expires_in"] == 30

        assert r2 is not None
        assert r2.status_code == 200
        b2 = r2.json()
        assert b2["lab_mode"] == "hybrid"
        assert b2["previous"] == "airgapped"
        assert "env_path" in b2
        assert "took_effect_at" in b2

        # .env rewritten.
        env_text = env_path.read_text()
        assert "LAB_MODE=hybrid" in env_text

        # os.environ updated (monkeypatched env var check via re-reading).
        assert os.getenv("LAB_MODE") == "hybrid"

        # Audit line appended.
        assert audit_path.exists()
        lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines) >= 1
        entry = json.loads(lines[-1])
        assert entry["to"] == "hybrid"
        assert entry["from"] == "airgapped"


# ---------------------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------------------

class TestToggleBadInput:
    def test_toggle_invalid_target(self, toggle_setup):
        client, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "banana"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_target"

    def test_toggle_missing_target(self, toggle_setup):
        client, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 400
        assert r.json()["error"] == "invalid_target"


# ---------------------------------------------------------------------------
# Bind-address gate
# ---------------------------------------------------------------------------

class TestToggleBindGate:
    def test_toggle_bind_gate_lan(self, toggle_setup, monkeypatch):
        """0.0.0.0 bind address is refused with exact spec copy."""
        client, env_path, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "0.0.0.0")
        mtime_before = env_path.stat().st_mtime_ns

        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 403
        body = r.json()
        assert body["error"] == "bind_not_loopback"
        # Exact message from spec.
        assert body["message"] == "Edit `.env` directly — toggle disabled when bound to non-loopback."
        # .env untouched.
        assert env_path.stat().st_mtime_ns == mtime_before

    def test_toggle_bind_gate_ipv4_lan(self, toggle_setup, monkeypatch):
        client, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "192.168.1.10")
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "bind_not_loopback"

    def test_toggle_bind_gate_ipv6_loopback_ok(self, toggle_setup, monkeypatch):
        """::1 is a valid loopback — should pass the bind gate and get to step-1."""
        client, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "::1")
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        # Bind gate passed; should proceed to step-1 (409 with token).
        assert r.status_code == 409
        assert r.json()["error"] == "need_confirm"


# ---------------------------------------------------------------------------
# Token protocol
# ---------------------------------------------------------------------------

class TestToggleTokenProtocol:
    def test_toggle_token_expired(self, toggle_setup, monkeypatch):
        """After TTL expires, re-using the old token issues a fresh 409."""
        import arail.portal.app as app_mod
        client, _, _ = toggle_setup

        # Step 1: get a token.
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r1.status_code == 409
        old_token = r1.json()["confirm_token"]

        # Manually expire the token by patching time.monotonic to return future.
        original_ttl = app_mod._TOGGLE_TOKEN_TTL
        # Force the token to appear expired by setting expires_at to the past.
        with app_mod._TOGGLE_TOKENS_LOCK:
            for k, v in list(app_mod._TOGGLE_TOKENS.items()):
                # Replace with an expired entry.
                import dataclasses
                app_mod._TOGGLE_TOKENS[k] = dataclasses.replace(
                    v, expires_at=time.monotonic() - 1.0
                )

        # Step 2 with the now-expired token: should get 409 + fresh token.
        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": old_token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 409
        body2 = r2.json()
        assert body2["error"] == "need_confirm"
        # A fresh token is issued.
        new_token = body2.get("confirm_token")
        assert new_token and new_token != old_token

    def test_toggle_token_replay(self, toggle_setup):
        """A consumed token cannot be used a second time."""
        client, _, _ = toggle_setup

        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        # First confirm: should succeed.
        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 200

        # Replay: token was deleted, should 409.
        r3 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r3.status_code == 409
        assert r3.json()["error"] == "need_confirm"

    def test_toggle_token_wrong_target(self, toggle_setup):
        """Token issued for 'hybrid' cannot be used for 'airgapped'."""
        client, _, _ = toggle_setup

        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        # Present hybrid token but request airgapped target.
        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "airgapped", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 409
        assert r2.json()["error"] == "need_confirm"


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

class TestToggleCsrf:
    def test_toggle_cross_origin(self, toggle_setup):
        """Requests from a cross-origin Origin header are refused."""
        client, env_path, _ = toggle_setup
        mtime_before = env_path.stat().st_mtime_ns

        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://evil.com"},
        )
        assert r.status_code == 403
        assert r.json()["error"] == "cross_origin"
        # .env untouched.
        assert env_path.stat().st_mtime_ns == mtime_before


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestToggleErrorHandling:
    def test_toggle_writer_failure(self, toggle_setup):
        """EnvWriterError from set_env_var -> 500; path/contents not in body."""
        from arail.env_writer import EnvWriterError
        client, env_path, _ = toggle_setup

        # Step 1: get token.
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        token = r1.json()["confirm_token"]

        # Patch set_env_var to raise EnvWriterError.
        with patch("arail.env_writer.set_env_var",
                   side_effect=EnvWriterError("disk exploded")):
            r2 = client.post(
                "/api/airgap/toggle",
                json={"target": "hybrid", "confirm_token": token},
                headers={"Origin": "http://testserver"},
            )

        assert r2.status_code == 500
        body = r2.json()
        assert body["error"] == "env_write_failed"
        # No path info in body.
        assert "path" not in body
        assert "env" not in str(body).lower() or body == {"error": "env_write_failed"}
        # .env untouched.
        assert env_path.read_bytes() == b"LAB_MODE=airgapped\n"


# ---------------------------------------------------------------------------
# Audit log shape
# ---------------------------------------------------------------------------

class TestToggleAuditLog:
    def test_toggle_audit_log_shape(self, toggle_setup):
        """After a happy-path toggle, audit log has one line with expected fields."""
        client, env_path, audit_path = toggle_setup

        _, r2 = _two_step(client, "hybrid")
        assert r2 is not None and r2.status_code == 200

        assert audit_path.exists()
        lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        entry = json.loads(lines[0])
        assert "ts" in entry
        assert entry["from"] == "airgapped"
        assert entry["to"] == "hybrid"
        assert "source_ip" in entry
        assert entry["confirmed"] is True
        assert "appended" in entry

    def test_toggle_audit_log_mode_600(self, toggle_setup):
        """Audit log is created with 0o600 permissions."""
        import stat
        client, _, audit_path = toggle_setup
        _two_step(client, "hybrid")
        assert audit_path.exists()
        mode = stat.S_IMODE(audit_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# Status endpoint — additive bind_is_loopback field
# ---------------------------------------------------------------------------

class TestAirgapStatusBindField:
    def test_status_has_bind_is_loopback(self, toggle_setup, monkeypatch):
        """GET /api/airgap/status includes bind_is_loopback (additive field)."""
        client, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        r = client.get("/api/airgap/status")
        assert r.status_code == 200
        body = r.json()
        assert "bind_is_loopback" in body
        assert body["bind_is_loopback"] is True

    def test_status_bind_is_loopback_false_for_lan(self, toggle_setup, monkeypatch):
        client, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "0.0.0.0")
        r = client.get("/api/airgap/status")
        assert r.status_code == 200
        assert r.json()["bind_is_loopback"] is False
