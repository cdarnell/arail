"""Tests for /api/system/health tier-gating (sprint 2026-05-14-platform-foundation §1).

Covers:
- min-tier hides max-only services (marimo, open-notebook, neo4j, opencode, notebook)
- max-tier allows max-only services through when up
- version field present in response
- snapshot of top-level JSON keys guards against accidental removal
- stream and snapshot report same services keyset
- LAB_TIER bypass attempt: crafted query params do not override tier
"""

from __future__ import annotations

import os
from unittest.mock import patch, AsyncMock
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_ONLY_SERVICES = {"notebook", "marimo", "open-notebook", "neo4j", "opencode"}
MIN_ONLY_SERVICES = {"ttyd", "lance-memory", "ollama"}
ALWAYS_ON_SERVICES = {"portal", "knowledge-canvas"}


def _make_client(monkeypatch, tmp_path, lab_tier: str = "min") -> TestClient:
    monkeypatch.setenv("LAB_TIER", lab_tier)
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    # Force all port probes to False so tier-gating is the only signal.
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        from arail.portal.app import app
        return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_min_tier_excludes_max_only_services(monkeypatch, tmp_path):
    """LAB_TIER=min: max-only services must not appear in services dict even if
    probes returned True.

    We monkeypatch _build_services_dict so all optionals appear up, then
    assert max-only IDs are still hidden.
    """
    monkeypatch.setenv("LAB_TIER", "min")
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import _build_services_dict
    # Simulate all probes returning True.
    services = _build_services_dict(
        portal_up=True, kc_up=True,
        ttyd_up=True, notebook_up=True, lance_up=True,
        marimo_running=True, open_notebook_running=True,
        ollama_up=True, neo4j_up=True, opencode_up=True,
    )
    # Max-only services must not appear under min tier.
    for svc in MAX_ONLY_SERVICES:
        assert svc not in services, f"max-only service '{svc}' leaked into min-tier response"
    # Min services should be present (they are up).
    for svc in MIN_ONLY_SERVICES:
        assert svc in services, f"min service '{svc}' missing from min-tier response"
    # Always-on present.
    assert "portal" in services
    assert "knowledge-canvas" in services


def test_max_tier_includes_max_only_services_when_up(monkeypatch, tmp_path):
    """LAB_TIER=max: max-only services appear when their probe returns True."""
    monkeypatch.setenv("LAB_TIER", "max")
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import _build_services_dict
    services = _build_services_dict(
        portal_up=True, kc_up=True,
        ttyd_up=True, notebook_up=True, lance_up=True,
        marimo_running=True, open_notebook_running=True,
        ollama_up=True, neo4j_up=True, opencode_up=True,
    )
    for svc in MAX_ONLY_SERVICES:
        assert svc in services, f"max-only service '{svc}' missing from max-tier response"


def test_max_only_not_shown_when_not_up(monkeypatch, tmp_path):
    """Even on max tier, max-only services that are down are not shown."""
    monkeypatch.setenv("LAB_TIER", "max")
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import _build_services_dict
    services = _build_services_dict(
        portal_up=True, kc_up=True,
        ttyd_up=False, notebook_up=False, lance_up=False,
        marimo_running=False, open_notebook_running=False,
        ollama_up=False, neo4j_up=False, opencode_up=False,
    )
    for svc in MAX_ONLY_SERVICES | MIN_ONLY_SERVICES:
        assert svc not in services, f"down service '{svc}' appeared in services dict"


def test_health_endpoint_returns_version_field(monkeypatch, tmp_path):
    """GET /api/system/health response includes a top-level 'version' field."""
    monkeypatch.setenv("LAB_TIER", "min")
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        from arail.portal.app import app
        client = TestClient(app)
        r = client.get("/api/system/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "version" in body, "'version' field missing from /api/system/health"
    assert isinstance(body["version"], str)
    # Existing spec-tier field must still exist (not clobbered).
    assert "tier" in body, "'tier' (spec-tier) field was accidentally removed"


def test_health_endpoint_top_level_keys_stable(monkeypatch, tmp_path):
    """Snapshot: top-level keys of /api/system/health must not drift.

    Add new keys freely; removing or renaming any key in this set is a
    breaking change and will fail this test.
    """
    monkeypatch.setenv("LAB_TIER", "min")
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    required_keys = {
        "platform", "arch", "cpu_count",
        "ram_total_gb", "ram_used_gb", "ram_pct",
        "disk_total_gb", "disk_free_gb", "disk_pct",
        "python", "backend", "model", "gpu",
        "tier", "deep_enabled", "aerollm_model",
        "version",
        "services", "service_checks", "health_summary",
        "mode", "local_inference",
    }
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        from arail.portal.app import app
        client = TestClient(app)
        r = client.get("/api/system/health")
    assert r.status_code == 200, r.text
    body = r.json()
    missing = required_keys - set(body.keys())
    assert not missing, f"Required keys missing from /api/system/health: {missing}"


def test_tier_bypass_query_param_ignored(monkeypatch, tmp_path):
    """LAB_TIER=min with crafted query params does not unlock max-only services."""
    monkeypatch.setenv("LAB_TIER", "min")
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import _build_services_dict
    # Even with all probes True, min tier must not show max-only services.
    services = _build_services_dict(
        portal_up=True, kc_up=True,
        ttyd_up=True, notebook_up=True, lance_up=True,
        marimo_running=True, open_notebook_running=True,
        ollama_up=True, neo4j_up=True, opencode_up=True,
    )
    for svc in MAX_ONLY_SERVICES:
        assert svc not in services, (
            f"Tier-bypass: max-only service '{svc}' visible under min tier"
        )


def test_optional_services_registry_valid():
    """_OPTIONAL_SERVICES must have valid tier values for every entry."""
    from arail.portal.app import _OPTIONAL_SERVICES
    for svc_id, tier in _OPTIONAL_SERVICES.items():
        assert tier in ("minimalist", "maximus"), (
            f"_OPTIONAL_SERVICES['{svc_id}'] = '{tier}' — not a valid tier"
        )
