"""API conformance snapshot test (sprint 2026-05-14-platform-foundation §3).

One test that asserts the stable shape (sorted keys, value types) of:
  - /api/system/health
  - /api/system/metrics

If shape drifts (key removed or type changed), this test fails.
Adding new keys is fine — they appear in the snapshot automatically
but do not break it.

Also asserts:
  - snake_case key convention on new endpoints
  - Content-Type: application/json
  - version / schema_version present
  - error envelope shape on deliberately-broken request (?format=prometheus → 501)
"""

from __future__ import annotations

import re
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _shape(obj) -> object:
    """Return a stable, type-only representation of a JSON value.

    dict → {key: _shape(v), ...} (sorted)
    list → [_shape(first_element)] or []
    scalar → type name string
    """
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_shape(obj[0])] if obj else []
    return type(obj).__name__


def _all_keys_snake_case(obj, path: str = "") -> list[str]:
    """Return a list of keys that violate snake_case convention."""
    violations = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if re.search(r"[A-Z]|-", k):
                violations.append(f"{path}.{k}" if path else k)
            violations.extend(_all_keys_snake_case(v, f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            violations.extend(_all_keys_snake_case(item, f"{path}[{i}]"))
    return violations


def _make_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal import app as app_module
    with app_module._METRICS_LOCK:
        app_module._METRICS["http_requests_total"] = 0
        app_module._METRICS["http_errors_total"] = 0
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Stable shape fixtures
# These are hand-authored from the first passing run of step 3.
# If a key is removed from the response, this dict will no longer be a
# subset of the actual shape and the test fails.
# ---------------------------------------------------------------------------

HEALTH_REQUIRED_SHAPE_SUBSET: dict = {
    "platform": "str",
    "arch": "str",
    "version": "str",
    "tier": "str",
    "mode": "str",
    # services and health_summary are dicts — checked structurally below, not by type string
    # service_checks is a list — checked below
}

METRICS_REQUIRED_SHAPE_SUBSET: dict = {
    "process_uptime_seconds": "float",
    "ram_used_bytes": "int",
    "ram_total_bytes": "int",
    "disk_free_bytes": "int",
    "chat_model_loaded": "int",
    "active_provider": "str",
    "lab_mode": "str",
    "lab_tier": "str",
    "active_agents": "int",
    "kb_doc_count": "int",
    "http_requests_total": "int",
    "http_errors_total": "int",
    "last_provider_change_unix": "int",
    "schema_version": "int",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_snapshot_shape(monkeypatch, tmp_path):
    """Shape of /api/system/health top-level keys matches required subset."""
    client = _make_client(monkeypatch, tmp_path)
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        r = client.get("/api/system/health")
    assert r.status_code == 200, r.text
    body = r.json()

    # Content-Type check
    assert r.headers["content-type"].startswith("application/json")

    # version field present and is a string
    assert "version" in body
    assert isinstance(body["version"], str)

    # Shape subset check
    shape = _shape(body)
    for key, expected_type in HEALTH_REQUIRED_SHAPE_SUBSET.items():
        assert key in shape, f"Key '{key}' missing from /api/system/health shape"
        assert shape[key] == expected_type, (
            f"/api/system/health['{key}'] expected type '{expected_type}', "
            f"got '{shape[key]}'"
        )

    # Structural checks for compound fields
    assert isinstance(body["services"], dict), "'services' must be a dict"
    assert isinstance(body["health_summary"], dict), "'health_summary' must be a dict"
    assert isinstance(body["service_checks"], list), "'service_checks' must be a list"
    for key in ("passing_required", "required_total", "passing_total", "total"):
        assert key in body["health_summary"], f"health_summary missing '{key}'"


def test_metrics_snapshot_shape(monkeypatch, tmp_path):
    """Shape of /api/system/metrics matches full required shape."""
    client = _make_client(monkeypatch, tmp_path)
    r = client.get("/api/system/metrics")
    assert r.status_code == 200, r.text
    body = r.json()

    # Content-Type check
    assert r.headers["content-type"].startswith("application/json")

    # schema_version present
    assert "schema_version" in body
    assert body["schema_version"] == 1

    # Shape check — allow process_uptime_seconds to be int or float
    shape = _shape(body)
    for key, expected_type in METRICS_REQUIRED_SHAPE_SUBSET.items():
        assert key in shape, f"Key '{key}' missing from /api/system/metrics"
        if key == "process_uptime_seconds":
            assert shape[key] in ("float", "int"), (
                f"/api/system/metrics['{key}'] expected float or int, got '{shape[key]}'"
            )
        else:
            assert shape[key] == expected_type, (
                f"/api/system/metrics['{key}'] expected type '{expected_type}', "
                f"got '{shape[key]}'"
            )


def test_metrics_error_envelope_on_bad_format(monkeypatch, tmp_path):
    """?format=prometheus returns 501 with conventions-compliant error envelope."""
    client = _make_client(monkeypatch, tmp_path)
    r = client.get("/api/system/metrics?format=prometheus")
    assert r.status_code == 501
    body = r.json()
    assert "error" in body
    assert "message" in body
    assert isinstance(body["error"], str)
    assert isinstance(body["message"], str)
    # Error slug must be snake_case, no spaces
    assert re.match(r"^[a-z][a-z_]*$", body["error"]), (
        f"error slug '{body['error']}' is not snake_case"
    )


def test_metrics_keys_are_snake_case(monkeypatch, tmp_path):
    """All top-level keys in /api/system/metrics are snake_case."""
    client = _make_client(monkeypatch, tmp_path)
    body = client.get("/api/system/metrics").json()
    violations = [k for k in body.keys() if re.search(r"[A-Z]|-", k)]
    assert not violations, f"Non-snake_case keys in /api/system/metrics: {violations}"


def test_health_keys_are_snake_case(monkeypatch, tmp_path):
    """All top-level keys in /api/system/health are snake_case."""
    with patch("arail.portal.app._port_open", new=AsyncMock(return_value=False)), \
         patch("arail.portal.app._container_running", return_value=False), \
         patch("arail.portal.app._docker_available", return_value=False):
        client = _make_client(monkeypatch, tmp_path)
        body = client.get("/api/system/health").json()
    violations = [k for k in body.keys() if re.search(r"[A-Z]|-", k)]
    assert not violations, f"Non-snake_case top-level keys in /api/system/health: {violations}"
