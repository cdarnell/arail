"""Full endpoint test matrix for POST /api/airgap/toggle — one-tap protocol.

ARCHITECTURE.md (sprint 2026-05-14-airgap-onetap-toggle) §test strategy.
The 2-step / confirm-token protocol was removed. All tests expect a single
POST to succeed or fail in one round trip.

Tests covered:
  Happy path:
  - test_toggle_one_tap_happy_path
  - test_toggle_no_confirm_token_field (regression: single-shot 200)
  - test_toggle_legacy_confirm_token_field_ignored
  - test_toggle_persists_on_disk_only_path

  Bad input:
  - test_toggle_invalid_target
  - test_toggle_missing_target

  Bind gate:
  - test_toggle_bind_gate_lan
  - test_toggle_bind_gate_ipv4_lan
  - test_toggle_bind_gate_ipv6_loopback_ok

  CSRF:
  - test_toggle_cross_origin_rejected

  Error / path safety:
  - test_toggle_writer_failure_no_path_leak

  Audit log:
  - test_audit_line_emitted_per_flip
  - test_toggle_audit_log_mode_600

  Probe cache:
  - test_probe_cache_invalidated_on_flip

  Status endpoint:
  - test_status_has_bind_is_loopback
  - test_status_bind_is_loopback_false_for_lan
"""

from __future__ import annotations

import json
import os
import stat
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


def _one_tap(client, target: str, extra_headers: dict | None = None):
    """Issue a single one-tap POST. Returns the response."""
    headers = {"Origin": "http://testserver"}
    if extra_headers:
        headers.update(extra_headers)
    return client.post("/api/airgap/toggle", json={"target": target}, headers=headers)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestToggleHappyPath:
    def test_toggle_one_tap_happy_path(self, toggle_setup):
        """Single POST -> 200 with lab_mode, previous, took_effect_at, appended."""
        client, env_path, audit_path = toggle_setup

        r = _one_tap(client, "hybrid")

        assert r.status_code == 200
        body = r.json()
        assert body["lab_mode"] == "hybrid"
        assert body["previous"] == "airgapped"
        assert "took_effect_at" in body
        assert "appended" in body
        # env_path must NOT be in the response (path-leak fix).
        assert "env_path" not in body

        # .env updated.
        assert "LAB_MODE=hybrid" in env_path.read_text()
        # os.environ updated.
        assert os.getenv("LAB_MODE") == "hybrid"
        # Audit line written.
        assert audit_path.exists()
        lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1

    def test_toggle_no_confirm_token_field(self, toggle_setup):
        """POST with only {target} — no confirm_token — returns 200 in one shot."""
        client, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 200
        assert r.json()["lab_mode"] == "hybrid"

    def test_toggle_legacy_confirm_token_field_ignored(self, toggle_setup):
        """POST with stale confirm_token from old client — field silently ignored."""
        client, _, _ = toggle_setup
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": "stale-abc"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 200
        assert r.json()["lab_mode"] == "hybrid"

    def test_toggle_persists_on_disk_only_path(self, tmp_path, monkeypatch):
        """Boot with no .env; POST {target:hybrid}; assert file created chmod 0600."""
        import arail.portal.app as app_mod
        env_path = tmp_path / ".env"
        # no .env at start
        audit_path = tmp_path / "airgap_audit.jsonl"
        monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
        monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        monkeypatch.setenv("LAB_MODE", "airgapped")

        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r.status_code == 200
        assert env_path.exists()
        assert "LAB_MODE=hybrid" in env_path.read_text()
        mode = stat.S_IMODE(env_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"
        body = r.json()
        assert body["appended"] is True


# ---------------------------------------------------------------------------
# Bad input
# ---------------------------------------------------------------------------

class TestToggleBadInput:
    def test_toggle_invalid_target(self, toggle_setup):
        client, _, _ = toggle_setup
        r = _one_tap(client, "banana")
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
        """0.0.0.0 bind address refused with exact spec message."""
        client, env_path, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "0.0.0.0")
        mtime_before = env_path.stat().st_mtime_ns

        r = _one_tap(client, "hybrid")

        assert r.status_code == 403
        body = r.json()
        assert body["error"] == "bind_not_loopback"
        assert body["message"] == "Edit `.env` directly — toggle disabled when bound to non-loopback."
        # .env untouched.
        assert env_path.stat().st_mtime_ns == mtime_before

    def test_toggle_bind_gate_ipv4_lan(self, toggle_setup, monkeypatch):
        client, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "192.168.1.10")
        r = _one_tap(client, "hybrid")
        assert r.status_code == 403
        assert r.json()["error"] == "bind_not_loopback"

    def test_toggle_bind_gate_ipv6_loopback_ok(self, toggle_setup, monkeypatch):
        """::1 is loopback — bind gate passes, 200 returned."""
        client, _, _ = toggle_setup
        monkeypatch.setenv("BIND_ADDR", "::1")
        r = _one_tap(client, "hybrid")
        assert r.status_code == 200
        assert r.json()["lab_mode"] == "hybrid"


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------

class TestToggleCsrf:
    def test_toggle_cross_origin_rejected(self, toggle_setup):
        """Cross-origin Origin header -> 403 cross_origin; .env and env unchanged."""
        client, env_path, _ = toggle_setup
        mtime_before = env_path.stat().st_mtime_ns
        lab_mode_before = os.getenv("LAB_MODE")

        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://evil.example:9999"},
        )

        assert r.status_code == 403
        assert r.json()["error"] == "cross_origin"
        # No side effects.
        assert env_path.stat().st_mtime_ns == mtime_before
        assert os.getenv("LAB_MODE") == lab_mode_before
        # No audit line.
        audit_path = toggle_setup[2]  # third element
        assert not audit_path.exists()


# ---------------------------------------------------------------------------
# Error handling + path-leak safety
# ---------------------------------------------------------------------------

class TestToggleErrorHandling:
    def test_toggle_writer_failure_no_path_leak(self, toggle_setup):
        """EnvWriterError -> 500; body is exactly {error:env_write_failed}; no side effects."""
        from arail.env_writer import EnvWriterError

        client, env_path, audit_path = toggle_setup
        lab_mode_before = os.getenv("LAB_MODE")
        env_before = env_path.read_bytes()

        with patch("arail.env_writer.set_env_var",
                   side_effect=EnvWriterError("/secret/.env: permission denied")):
            r = _one_tap(client, "hybrid")

        assert r.status_code == 500
        body = r.json()
        # Body must be exactly this — no path, no exception string.
        assert body == {"error": "env_write_failed"}, f"Got: {body}"
        # os.environ unchanged.
        assert os.getenv("LAB_MODE") == lab_mode_before
        # .env unchanged.
        assert env_path.read_bytes() == env_before
        # No audit line.
        assert not audit_path.exists()


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

class TestToggleAuditLog:
    def test_audit_line_emitted_per_flip(self, toggle_setup):
        """Each successful flip appends one audit line. Three flips = three lines."""
        client, env_path, audit_path = toggle_setup

        # Flip 1: airgapped -> hybrid
        r = _one_tap(client, "hybrid")
        assert r.status_code == 200

        lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 1
        e = json.loads(lines[0])
        assert e["from"] == "airgapped"
        assert e["to"] == "hybrid"
        assert "ts" in e
        assert "source_ip" in e
        assert e["confirmed"] is True

        # Flip 2: hybrid -> airgapped (same direction as env says now)
        import arail.portal.app as app_mod
        import os as _os
        _os.environ["LAB_MODE"] = "hybrid"  # reflect current state
        r2 = _one_tap(client, "airgapped")
        assert r2.status_code == 200
        lines2 = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines2) == 2

        # Flip 3: airgapped -> hybrid again
        _os.environ["LAB_MODE"] = "airgapped"
        r3 = _one_tap(client, "hybrid")
        assert r3.status_code == 200
        lines3 = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines3) == 3

    def test_toggle_audit_log_mode_600(self, toggle_setup):
        """Audit log is created with 0o600 permissions."""
        client, _, audit_path = toggle_setup
        _one_tap(client, "hybrid")
        assert audit_path.exists()
        mode = stat.S_IMODE(audit_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# Probe cache invalidation (regression)
# ---------------------------------------------------------------------------

class TestProbeCacheInvalidation:
    def test_probe_cache_invalidated_on_flip(self, toggle_setup):
        """After a successful flip, egress._PROBE_CACHE is cleared."""
        import arail.egress as egress_mod
        # Prime the cache.
        egress_mod._PROBE_CACHE["result"] = True
        egress_mod._PROBE_CACHE["ts"] = time.monotonic()

        client, _, _ = toggle_setup
        r = _one_tap(client, "hybrid")
        assert r.status_code == 200

        assert egress_mod._PROBE_CACHE == {}, (
            f"Expected empty cache after toggle, got: {egress_mod._PROBE_CACHE}"
        )


# ---------------------------------------------------------------------------
# Status endpoint — additive bind_is_loopback field
# ---------------------------------------------------------------------------

class TestAirgapStatusBindField:
    def test_status_has_bind_is_loopback(self, toggle_setup, monkeypatch):
        """GET /api/airgap/status includes bind_is_loopback field."""
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
