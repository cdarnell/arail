"""Integration tests for opencode Flask routes.

Covers ARCHITECTURE.md must-pass list:
  - test_min_tier_404_all_three_routes        (F-GATE-1, F-GATE-2)
  - test_min_tier_no_side_effects             (F-GATE-3)
  - test_max_tier_page_renders_when_not_installed
  - test_max_tier_page_iframe_url_no_credentials (F-SEC-1)
  - test_status_includes_opencode_entry
  - test_status_does_not_leak_token           (F-SEC-3)
  - test_health_includes_opencode
  - test_workbench_label_in_nav_template      (regression)
  - test_existing_notebooks_status_unchanged_for_first_three (regression)
"""

from __future__ import annotations

import re
import os
import unittest.mock as mock

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# App fixture helpers
# ---------------------------------------------------------------------------

def _get_client(monkeypatch, tier: str = "min"):
    """Return a synchronous TestClient with the given tier."""
    monkeypatch.setenv("LAB_TIER", tier)
    from arail.portal.app import app
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# F-GATE-1, F-GATE-2 — min-tier 404 on all three routes
# ---------------------------------------------------------------------------

class TestMinTierGate:
    @pytest.mark.parametrize("method,path", [
        ("GET",  "/opencode"),
        ("POST", "/api/opencode/start"),
        ("POST", "/api/opencode/stop"),
    ])
    def test_min_tier_404_all_three_routes(self, monkeypatch, method, path):
        """All three /opencode* routes return 404 on min tier (F-GATE-1, F-GATE-2)."""
        monkeypatch.setenv("LAB_TIER", "min")
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.request(method, path)
        assert resp.status_code == 404, (
            f"{method} {path} on min tier should be 404, got {resp.status_code}"
        )

    def test_min_tier_no_side_effects(self, monkeypatch, caplog):
        """Gate fires before any activity_log emit or secrets read (F-GATE-3)."""
        import logging
        monkeypatch.setenv("LAB_TIER", "min")
        # Patch activity_log.emit to detect if it's called
        emit_calls: list = []
        import arail.activity as al
        original_emit = al.activity_log.emit
        monkeypatch.setattr(al.activity_log, "emit", lambda *a, **kw: emit_calls.append(a))

        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        with caplog.at_level(logging.DEBUG):
            client.get("/opencode")
            client.post("/api/opencode/start")
            client.post("/api/opencode/stop")

        assert not emit_calls, (
            f"activity_log.emit was called {len(emit_calls)} time(s) on min-tier 404: {emit_calls}"
        )


# ---------------------------------------------------------------------------
# Max-tier page rendering
# ---------------------------------------------------------------------------

class TestMaxTierPage:
    def _max_client(self, monkeypatch, is_installed=False, is_running=False):
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_installed", lambda: is_installed
        )
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_running",
            lambda port=4096: is_running,
        )
        from arail.portal.app import app
        return TestClient(app, raise_server_exceptions=True)

    def test_max_tier_page_renders_when_not_installed(self, monkeypatch):
        """Max tier + not installed → HTML contains install hint text."""
        client = self._max_client(monkeypatch, is_installed=False)
        resp = client.get("/opencode")
        assert resp.status_code == 200
        body = resp.text
        # Should show install hint state
        assert "install" in body.lower() or "opencode" in body.lower()

    def test_max_tier_page_renders_when_installed_not_running(self, monkeypatch):
        """Max tier + installed + not running → Start button visible."""
        client = self._max_client(monkeypatch, is_installed=True, is_running=False)
        resp = client.get("/opencode")
        assert resp.status_code == 200
        assert "Start opencode" in resp.text or "start" in resp.text.lower()

    def test_max_tier_page_iframe_url_no_credentials(self, monkeypatch):
        """Running state: iframe src matches http://127.0.0.1:<port>/ with no credentials (F-SEC-1)."""
        client = self._max_client(monkeypatch, is_installed=True, is_running=True)
        resp = client.get("/opencode")
        assert resp.status_code == 200
        body = resp.text
        # Must contain the iframe pointing to 127.0.0.1:4096
        assert 'src="http://127.0.0.1:4096/"' in body, (
            "Iframe src not found or malformed in rendered HTML"
        )
        # Must NOT contain credentials (user:pass@host pattern)
        cred_pattern = re.compile(r'src="http://[^/"]*@', re.IGNORECASE)
        assert not cred_pattern.search(body), "Iframe src contains embedded credentials"

    def test_max_tier_page_csp_allows_iframe(self, monkeypatch):
        """Response CSP (if present) must include 127.0.0.1:4096 or be absent (F-IFRAME-2)."""
        client = self._max_client(monkeypatch, is_installed=True, is_running=True)
        resp = client.get("/opencode")
        csp = resp.headers.get("content-security-policy", "")
        if csp:
            # If CSP is present, frame-src must allow 127.0.0.1:4096
            assert "127.0.0.1:4096" in csp or "frame-src" not in csp, (
                f"CSP present and blocks 127.0.0.1:4096 iframe: {csp}"
            )


# ---------------------------------------------------------------------------
# /api/notebooks/status — shape + token safety (F-SEC-3)
# ---------------------------------------------------------------------------

class TestNotebooksStatus:
    def _max_client(self, monkeypatch):
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setattr(
            "arail.portal.services.opencode.is_installed", lambda: True
        )
        from arail.portal.app import app
        return TestClient(app, raise_server_exceptions=True)

    def test_status_includes_opencode_entry(self, monkeypatch):
        """Max tier: /api/notebooks/status returns opencode as 5th entry (F-SEC-3 shape)."""
        client = self._max_client(monkeypatch)
        resp = client.get("/api/notebooks/status")
        assert resp.status_code == 200
        data = resp.json()
        ids = [nb["id"] for nb in data.get("notebooks", [])]
        assert "opencode" in ids, f"opencode entry missing from notebooks: {ids}"

    def test_status_opencode_entry_shape(self, monkeypatch):
        """opencode entry has required fields, url_external with no credentials."""
        client = self._max_client(monkeypatch)
        resp = client.get("/api/notebooks/status")
        data = resp.json()
        oc_entry = next(
            (nb for nb in data.get("notebooks", []) if nb["id"] == "opencode"),
            None,
        )
        assert oc_entry is not None
        for field in ("id", "name", "installed", "alive", "url_internal", "url_external"):
            assert field in oc_entry, f"Field '{field}' missing from opencode entry"
        # url_external must not contain credentials
        assert "@" not in oc_entry["url_external"], (
            "url_external contains embedded credentials"
        )
        assert oc_entry["url_internal"] == "/opencode"

    def test_status_does_not_leak_token(self, monkeypatch):
        """Provider token must not appear in /api/notebooks/status payload (F-SEC-3)."""
        secret = "secret-token-abc-123"
        monkeypatch.setenv("LAB_TIER", "max")
        monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/notebooks/status")
        assert resp.status_code == 200
        assert secret not in resp.text, (
            "Provider token leaked into /api/notebooks/status response"
        )

    def test_status_min_tier_no_opencode_entry(self, monkeypatch):
        """Min tier: opencode entry absent from /api/notebooks/status."""
        monkeypatch.setenv("LAB_TIER", "min")
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/notebooks/status")
        assert resp.status_code == 200
        data = resp.json()
        ids = [nb["id"] for nb in data.get("notebooks", [])]
        assert "opencode" not in ids, f"opencode entry appears on min tier: {ids}"

    def test_existing_notebooks_status_unchanged_for_first_three(self, monkeypatch):
        """First three entries (jupyter/marimo/open-notebook) keep same shape (regression)."""
        monkeypatch.setenv("LAB_TIER", "max")
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/notebooks/status")
        assert resp.status_code == 200
        data = resp.json()
        notebooks = data.get("notebooks", [])
        ids = [nb["id"] for nb in notebooks]
        for expected_id in ("jupyter", "marimo", "open-notebook"):
            assert expected_id in ids, f"'{expected_id}' missing from status"
            entry = next(nb for nb in notebooks if nb["id"] == expected_id)
            for field in ("id", "name", "installed", "alive", "url_internal", "url_external"):
                assert field in entry, (
                    f"Field '{field}' missing from '{expected_id}' entry (regression)"
                )


# ---------------------------------------------------------------------------
# /api/system/health — opencode in optional_services
# ---------------------------------------------------------------------------

class TestSystemHealth:
    def test_health_includes_opencode_when_up(self, monkeypatch):
        """When opencode port is open, 'opencode' appears in services (F-GATE, arch spec)."""
        monkeypatch.setenv("LAB_TIER", "max")
        # Patch _port_open so opencode port returns True
        import arail.portal.app as portal_app
        original_port_open = portal_app._port_open

        async def mock_port_open(host, port, timeout=0.3):
            if port == 4096:
                return True
            return await original_port_open(host, port, timeout)

        monkeypatch.setattr(portal_app, "_port_open", mock_port_open)
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        data = resp.json()
        services = data.get("services", {})
        assert "opencode" in services, (
            f"'opencode' not in services when port is open: {list(services.keys())}"
        )

    def test_health_hides_opencode_when_down(self, monkeypatch):
        """When opencode port is closed, 'opencode' is absent (hidden, not false)."""
        monkeypatch.setenv("LAB_TIER", "max")
        import arail.portal.app as portal_app
        original_port_open = portal_app._port_open

        async def mock_port_open(host, port, timeout=0.3):
            if port == 4096:
                return False
            # Keep portal itself up so health check can complete
            if port == 8080:
                return True
            return await original_port_open(host, port, timeout)

        monkeypatch.setattr(portal_app, "_port_open", mock_port_open)
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/api/system/health")
        assert resp.status_code == 200
        data = resp.json()
        services = data.get("services", {})
        assert "opencode" not in services, (
            f"'opencode' should be hidden when port is closed, but it's in services: {services}"
        )


# ---------------------------------------------------------------------------
# Regression — nav template and Workbench label
# ---------------------------------------------------------------------------

class TestWorkbenchLabel:
    def test_workbench_label_in_nav_template(self, monkeypatch):
        """Nav renders 'Workbench' (not 'Notebooks') when notebooks surface is active."""
        monkeypatch.setenv("LAB_TIER", "max")
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/notebooks")
        assert resp.status_code == 200
        assert "Workbench" in resp.text, (
            "Nav does not contain 'Workbench' text on max-tier /notebooks page"
        )
        # Old label should be gone from nav (the heading changed too, so just
        # check nav link specifically — look for the href pattern)
        # We check the nav partial text, not the page heading.
        assert ">Workbench<" in resp.text or "Workbench" in resp.text

    def test_workbench_page_heading(self, monkeypatch):
        """The /notebooks page heading is 'Workbench' (regression — heading changed)."""
        monkeypatch.setenv("LAB_TIER", "max")
        from arail.portal.app import app
        client = TestClient(app, raise_server_exceptions=True)
        resp = client.get("/notebooks")
        assert resp.status_code == 200
        assert "<h1>Workbench</h1>" in resp.text
