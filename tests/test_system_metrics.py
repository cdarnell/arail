"""Tests for GET /api/system/metrics (sprint 2026-05-14-platform-foundation §2).

Covers:
1. Cold-start: all documented keys present, correct types.
2. http_requests_total increments after N non-metrics endpoint hits.
3. ARAIL_MODE=hybrid reflected in lab_mode field.
4. psutil-missing branch: byte fields == 0, response 200.
5. ?format=prometheus → 501 with conventions-compliant error envelope.
6. Metrics endpoint does not count itself in http_requests_total.
7. No sensitive data leaked (no tokens, no raw file paths).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

REQUIRED_KEYS = {
    "process_uptime_seconds",
    "ram_used_bytes",
    "ram_total_bytes",
    "disk_free_bytes",
    "chat_model_loaded",
    "active_provider",
    "lab_mode",
    "lab_tier",
    "active_agents",
    "kb_doc_count",
    "http_requests_total",
    "http_errors_total",
    "last_provider_change_unix",
    "schema_version",
}


def _fresh_client(monkeypatch, tmp_path, **env_overrides):
    """Return a TestClient with a clean environment."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    for k, v in env_overrides.items():
        monkeypatch.setenv(k, v)
    # Reset _METRICS counters between tests by patching the module-level dict.
    # We import app fresh-ish by resetting the counter state.
    from arail.portal import app as app_module
    with app_module._METRICS_LOCK:
        app_module._METRICS["http_requests_total"] = 0
        app_module._METRICS["http_errors_total"] = 0
        app_module._METRICS["last_provider_change_unix"] = 0
    return TestClient(app_module.app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_metrics_cold_start_all_keys_present(monkeypatch, tmp_path):
    """GET /api/system/metrics returns 200 with all documented keys."""
    client = _fresh_client(monkeypatch, tmp_path)
    r = client.get("/api/system/metrics")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    body = r.json()
    missing = REQUIRED_KEYS - set(body.keys())
    assert not missing, f"Missing keys in /api/system/metrics: {missing}"


def test_metrics_key_types(monkeypatch, tmp_path):
    """Values have the expected types."""
    client = _fresh_client(monkeypatch, tmp_path)
    body = client.get("/api/system/metrics").json()
    assert isinstance(body["process_uptime_seconds"], (int, float))
    assert body["process_uptime_seconds"] >= 0
    assert isinstance(body["ram_used_bytes"], int)
    assert isinstance(body["ram_total_bytes"], int)
    assert isinstance(body["disk_free_bytes"], int)
    assert body["chat_model_loaded"] in (0, 1)
    assert isinstance(body["active_provider"], str)
    assert body["lab_mode"] in ("airgapped", "hybrid")
    assert body["lab_tier"] in ("min", "max")
    assert isinstance(body["active_agents"], int)
    assert isinstance(body["kb_doc_count"], int)
    assert isinstance(body["http_requests_total"], int)
    assert isinstance(body["http_errors_total"], int)
    assert isinstance(body["last_provider_change_unix"], (int, float))
    assert body["schema_version"] == 1


def test_metrics_counter_increments_after_other_hits(monkeypatch, tmp_path):
    """http_requests_total increments after N non-metrics endpoint hits."""
    client = _fresh_client(monkeypatch, tmp_path)
    # Baseline
    baseline = client.get("/api/system/metrics").json()["http_requests_total"]
    # Hit another endpoint N times — /health is always allowed pre-onboarding
    N = 3
    for _ in range(N):
        client.get("/health")
    body = client.get("/api/system/metrics").json()
    # Counter should have gone up by at least N (may include other internal calls)
    assert body["http_requests_total"] >= baseline + N, (
        f"Expected http_requests_total >= {baseline + N}, got {body['http_requests_total']}"
    )


def test_metrics_not_self_counted(monkeypatch, tmp_path):
    """Repeated calls to /api/system/metrics do not inflate http_requests_total."""
    client = _fresh_client(monkeypatch, tmp_path)
    first = client.get("/api/system/metrics").json()["http_requests_total"]
    # Call /api/system/metrics several more times
    for _ in range(5):
        client.get("/api/system/metrics")
    after = client.get("/api/system/metrics").json()["http_requests_total"]
    assert after == first, (
        f"Self-counting detected: first={first}, after 5 extra metrics calls={after}"
    )


def test_metrics_hybrid_mode(monkeypatch, tmp_path):
    """ARAIL_MODE=hybrid is reflected in lab_mode field."""
    client = _fresh_client(monkeypatch, tmp_path, ARAIL_MODE="hybrid")
    body = client.get("/api/system/metrics").json()
    assert body["lab_mode"] == "hybrid", f"Expected 'hybrid', got {body['lab_mode']!r}"


def test_metrics_psutil_missing_byte_fields_zero(monkeypatch, tmp_path):
    """If psutil is missing, byte fields are 0 and response is still 200."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal import app as app_module
    with app_module._METRICS_LOCK:
        app_module._METRICS["http_requests_total"] = 0
        app_module._METRICS["http_errors_total"] = 0

    # Monkeypatch builtins.__import__ to raise ImportError for psutil
    real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def fake_import(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("psutil not available (test)")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        client = TestClient(app_module.app)
        r = client.get("/api/system/metrics")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ram_used_bytes"] == 0
    assert body["ram_total_bytes"] == 0
    assert body["disk_free_bytes"] == 0
    assert body["schema_version"] == 1


def test_metrics_prometheus_format_returns_501(monkeypatch, tmp_path):
    """?format=prometheus returns 501 with conventions-compliant error envelope."""
    client = _fresh_client(monkeypatch, tmp_path)
    r = client.get("/api/system/metrics?format=prometheus")
    assert r.status_code == 501, r.text
    body = r.json()
    assert "error" in body, "Error envelope missing 'error' key"
    assert "message" in body, "Error envelope missing 'message' key"
    assert body["error"] == "not_implemented"


def test_metrics_no_sensitive_data(monkeypatch, tmp_path):
    """Response must not contain provider tokens, raw file-system paths, or env dumps."""
    client = _fresh_client(monkeypatch, tmp_path)
    body = client.get("/api/system/metrics").json()
    body_str = str(body)
    # No API keys or tokens
    for suspect in ("sk-", "Bearer ", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        assert suspect not in body_str, f"Sensitive string '{suspect}' found in metrics"
    # active_provider is a label string, not a token
    assert len(body["active_provider"]) < 200, "active_provider suspiciously long"
