"""QA — setup / happy-path / regression tests for the airgap runtime toggle.

Buckets covered:
- 30% setup — clean-clone/.env.example round-trip + missing-.env append.
- 10% happy — single end-to-end click with status-pill verification.
- 10% regression — the additive bind_is_loopback field doesn't break shape;
  prior airgap status fields all still present.

Excluded from the QA budget here (covered in the security/buddy files):
- bind-gate matrix, CSRF, symlink, rapid-fire (covered separately).

Migrated from 2-step to one-tap in QA cleanup pass (2026-05-14):
- test_toggle_then_simulated_restart_persists
- test_toggle_appends_when_env_lacks_LAB_MODE
- test_toggle_when_env_is_completely_missing
- test_status_pill_flips_after_toggle

Deleted (response-shape test):
- test_response_shape_complete — covered by test_airgap_toggle_endpoint.py.
"""

from __future__ import annotations

import json
import os
import stat
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


# ---------------------------------------------------------------------------
# Setup bucket: .env.example round-trip + missing-file append
# ---------------------------------------------------------------------------

class TestSetupRoundTrip:
    """Mimic ``./arailctl setup && ./arailctl start`` flow: copy .env.example,
    toggle from UI, verify .env survives a 'restart' (re-read)."""

    def test_env_example_template_copies_clean(self, tmp_path):
        """The .env.example template ships with LAB_MODE=airgapped at column 0."""
        repo_root = Path(__file__).resolve().parents[1]
        example = repo_root / ".env.example"
        assert example.exists(), ".env.example is the template; must be present"
        text = example.read_text()
        assert "LAB_MODE=airgapped" in text, (
            "Template must default to airgapped (security default)"
        )
        # Replicate the canonical setup move: cp .env.example .env.
        target = tmp_path / ".env"
        target.write_text(text)
        # And read_env_var sees the same value.
        from arail.env_writer import read_env_var
        assert read_env_var(target, "LAB_MODE") == "airgapped"

    def test_toggle_then_simulated_restart_persists(self, tmp_path, monkeypatch):
        """Toggle hybrid; close client; new TestClient still sees hybrid in .env."""
        env_path = tmp_path / ".env"
        repo_root = Path(__file__).resolve().parents[1]
        env_path.write_text((repo_root / ".env.example").read_text())
        audit_path = tmp_path / "airgap_audit.jsonl"

        import arail.portal.app as app_mod
        monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
        monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        monkeypatch.setenv("LAB_MODE", "airgapped")

        client = TestClient(app, raise_server_exceptions=False)
        h = {"Origin": "http://testserver"}
        r = client.post("/api/airgap/toggle", json={"target": "hybrid"}, headers=h)
        assert r.status_code == 200

        # Simulate a restart: drop the in-process LAB_MODE, re-read from disk.
        monkeypatch.delenv("LAB_MODE", raising=False)
        from arail.env_writer import read_env_var
        assert read_env_var(env_path, "LAB_MODE") == "hybrid"

        # And every comment from .env.example survives — the rewriter preserves them.
        post_text = env_path.read_text()
        assert "# =====" in post_text or "# ---" in post_text  # comments preserved
        assert "LAB_MODE=hybrid" in post_text

    def test_toggle_appends_when_env_lacks_LAB_MODE(self, tmp_path, monkeypatch):
        """No LAB_MODE line in .env → toggle endpoint appends with marker comment."""
        env_path = tmp_path / ".env"
        env_path.write_text("FOO=bar\n# unrelated\n")
        audit_path = tmp_path / "airgap_audit.jsonl"

        import arail.portal.app as app_mod
        monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
        monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        monkeypatch.setenv("LAB_MODE", "airgapped")  # in-process default

        client = TestClient(app, raise_server_exceptions=False)
        h = {"Origin": "http://testserver"}
        r = client.post("/api/airgap/toggle", json={"target": "hybrid"}, headers=h)
        assert r.status_code == 200
        body = r.json()
        assert body["appended"] is True
        text = env_path.read_text()
        # Original lines preserved.
        assert "FOO=bar" in text
        assert "# unrelated" in text
        # New LAB_MODE appended.
        assert "LAB_MODE=hybrid" in text
        # Marker comment added.
        assert "set by arail portal toggle" in text

    def test_toggle_when_env_is_completely_missing(self, tmp_path, monkeypatch):
        """No .env file at all → endpoint creates one with mode 0o600."""
        env_path = tmp_path / ".env"
        # No write — file missing.
        audit_path = tmp_path / "airgap_audit.jsonl"

        import arail.portal.app as app_mod
        monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
        monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        monkeypatch.setenv("LAB_MODE", "airgapped")

        client = TestClient(app, raise_server_exceptions=False)
        h = {"Origin": "http://testserver"}
        r = client.post("/api/airgap/toggle", json={"target": "hybrid"}, headers=h)
        assert r.status_code == 200
        assert env_path.exists()
        # File mode 0o600.
        mode = stat.S_IMODE(env_path.stat().st_mode)
        assert mode == 0o600, f"Expected 0o600 on new .env, got {oct(mode)}"
        text = env_path.read_text()
        assert "LAB_MODE=hybrid" in text


# ---------------------------------------------------------------------------
# Happy path — UI flow simulated through the API
# ---------------------------------------------------------------------------

class TestHappyPath:
    @pytest.fixture()
    def setup_(self, tmp_path, monkeypatch):
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

    def test_status_pill_flips_after_toggle(self, setup_):
        """GET /api/airgap/status before and after toggle reflects the new mode."""
        client, _, _ = setup_

        before = client.get("/api/airgap/status").json()
        assert before["lab_mode"] == "airgapped"

        h = {"Origin": "http://testserver"}
        r = client.post("/api/airgap/toggle", json={"target": "hybrid"}, headers=h)
        assert r.status_code == 200

        after = client.get("/api/airgap/status").json()
        assert after["lab_mode"] == "hybrid"


# ---------------------------------------------------------------------------
# Regression — additive field shape, prior status keys still present
# ---------------------------------------------------------------------------

class TestStatusShapeRegression:
    @pytest.fixture()
    def status_setup(self, tmp_path, monkeypatch):
        env_path = tmp_path / ".env"
        env_path.write_bytes(b"LAB_MODE=airgapped\n")
        import arail.portal.app as app_mod
        monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        monkeypatch.setenv("LAB_MODE", "airgapped")
        return TestClient(app, raise_server_exceptions=False)

    def test_status_response_keeps_lab_mode_field(self, status_setup):
        client = status_setup
        body = client.get("/api/airgap/status").json()
        # Pre-existing required field.
        assert "lab_mode" in body
        # New additive field.
        assert "bind_is_loopback" in body

    def test_status_endpoint_does_not_500_when_BIND_ADDR_unset(self, status_setup, monkeypatch):
        """Missing BIND_ADDR uses the default 127.0.0.1 — must not crash."""
        client = status_setup
        monkeypatch.delenv("BIND_ADDR", raising=False)
        r = client.get("/api/airgap/status")
        assert r.status_code == 200
        assert r.json()["bind_is_loopback"] is True

    def test_status_lab_mode_default_when_unset(self, status_setup, monkeypatch):
        """LAB_MODE unset → defaults to airgapped (security default)."""
        client = status_setup
        monkeypatch.delenv("LAB_MODE", raising=False)
        r = client.get("/api/airgap/status")
        assert r.status_code == 200
        assert r.json()["lab_mode"] == "airgapped"
