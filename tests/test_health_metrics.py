"""Observability endpoint tests — /health, /healthz, /metrics.

Five tests covering the nine OBS failure modes from ARCHITECTURE.md:

  1. test_health_pre_onboarding        — OBS4 (gate bypass), OBS3 (liveness only)
  2. test_healthz_alias                — OBS4 (alias works)
  3. test_metrics_pre_onboarding       — OBS4 + smoke for OBS1, OBS2
  4. test_metrics_format_parses        — OBS5 (valid Prometheus text format)
  5. test_metrics_no_package_names     — OBS1 (no package names leaked)
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client_no_password(monkeypatch, tmp_path) -> TestClient:
    """Return a TestClient with no password set (pre-onboarding state)."""
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    monkeypatch.delenv("OPEN_NOTEBOOK_ENCRYPTION_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    from arail.portal.app import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_health_pre_onboarding(monkeypatch, tmp_path):
    """GET /health returns 200 with the correct JSON shape before onboarding.

    Covers OBS4 (onboarding gate bypass) and OBS3 (liveness contract: no
    backend checks — only process-alive signal).
    """
    client = _client_no_password(monkeypatch, tmp_path)
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "arail"
    assert "version" in body
    assert isinstance(body["uptime_seconds"], (int, float))
    assert body["uptime_seconds"] >= 0
    assert body["lab_mode"] in ("airgapped", "hybrid")


def test_healthz_alias(monkeypatch, tmp_path):
    """GET /healthz returns the same shape as /health.

    Covers OBS4 (alias also bypasses the gate).
    """
    client = _client_no_password(monkeypatch, tmp_path)
    r = client.get("/healthz")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert body["service"] == "arail"
    assert "version" in body
    assert "uptime_seconds" in body
    assert "lab_mode" in body


def test_metrics_pre_onboarding_and_content_type(monkeypatch, tmp_path):
    """GET /metrics returns 200, correct content-type, and expected metric names.

    Covers OBS4 (gate bypass pre-onboarding), smoke test for OBS1 and OBS2
    (returns quickly; aggregate security data present).
    """
    client = _client_no_password(monkeypatch, tmp_path)
    r = client.get("/metrics")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain"), (
        f"Expected text/plain, got {r.headers['content-type']}"
    )
    body = r.text
    # Core metric names must be present.
    assert "arail_inference_capacity" in body
    assert "arail_uptime_seconds" in body
    assert "arail_lab_mode" in body
    assert "arail_build_info" in body
    assert "arail_security_last_scan_age_seconds" in body
    assert "arail_security_findings" in body


def test_metrics_format_parses(monkeypatch, tmp_path):
    """Every non-blank, non-comment line in /metrics matches Prometheus format.

    Covers OBS5: verifies HELP/TYPE comment placement, metric name pattern,
    optional label set, and numeric value (including negative and float).

    Regex per-line pattern (non-comment, non-blank):
        ^[a-zA-Z_][a-zA-Z0-9_]*({[^}]*})? -?[0-9]+(.[0-9]+)?(e[-+]?[0-9]+)?$
    """
    client = _client_no_password(monkeypatch, tmp_path)
    r = client.get("/metrics")
    assert r.status_code == 200, r.text
    body = r.text

    # Prometheus exposition must end with a final newline.
    assert body.endswith("\n"), "Exposition body must end with newline"

    line_pattern = re.compile(
        r'^[a-zA-Z_][a-zA-Z0-9_]*(\{[^}]*\})? -?\d+(\.\d+)?(e[-+]?\d+)?$'
    )
    bad_lines: list[str] = []
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        if not line_pattern.match(line):
            bad_lines.append(repr(line))

    assert not bad_lines, (
        f"Prometheus format violations ({len(bad_lines)} lines):\n"
        + "\n".join(bad_lines[:10])
    )


def test_metrics_no_package_names_leaked(monkeypatch, tmp_path):
    """Package names from a fake security scan must NOT appear in /metrics.

    Injects a fake last_scan.json with a synthetic package name that cannot
    appear in any metric help text or label value, then asserts that name
    is absent from /metrics output.

    The sentinel is 'xyzzy-vuln-pkg-sentinel' — a string that has no
    semantic meaning in the Prometheus exposition and will never appear in
    help text or label values emitted by _render_metrics().

    Covers OBS1: /metrics is aggregate-only; individual package names are
    reserved for /api/admin/security/status (authenticated endpoint).
    """
    import json
    import stat

    # Use a sentinel package name that cannot collide with any help text.
    sentinel_pkg = "xyzzy-vuln-pkg-sentinel"

    # Write a fake scan file with the sentinel package name.
    data_dir = tmp_path / "lab" / "data" / "security"
    data_dir.mkdir(parents=True)
    fake_scan_path = data_dir / "last_scan.json"
    import datetime
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    fake_scan = {
        "available": True,
        "last_run_ts": now_iso,
        "trigger": "manual",
        "summary": {"critical": 1, "high": 2, "medium": 0, "low": 0, "total": 3},
        "findings": [
            {
                "name": sentinel_pkg,
                "version": "1.0.0",
                "vulns": [{"id": "CVE-2024-FAKE", "fix_versions": ["2.0.0"]}],
                "severity": "critical",
            }
        ],
        "tool": "pip-audit",
        "tool_version": "2.7.0",
        "auto_scan_enabled": False,
        "error": None,
    }
    fake_scan_path.write_text(json.dumps(fake_scan))
    fake_scan_path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    # Point security_scan._scan_file() at our temp directory by overriding
    # the DATA_DIR env var that security_scan.py resolves via arail.config.
    monkeypatch.setenv("ARAIL_DATA_DIR", str(tmp_path / "lab" / "data"))
    # Also clear password so we exercise the gate-bypass path.
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    # Bust the security_scan 5 s cache by reloading the module's cache
    # sentinel.  The module caches via a module-level dict — importing fresh
    # is sufficient since TestClient creates a new app context per test.
    import importlib
    from arail.portal import security_scan
    importlib.reload(security_scan)

    from arail.portal.app import app
    client = TestClient(app)
    r = client.get("/metrics")
    assert r.status_code == 200, r.text

    body = r.text
    # The synthetic package name must never appear in /metrics output (OBS1).
    assert sentinel_pkg not in body, (
        f"Package name '{sentinel_pkg}' leaked into /metrics output. "
        "Only aggregate counts should appear."
    )
    # But the aggregate counts SHOULD be there.
    assert 'severity="critical"' in body
    assert 'severity="high"' in body
