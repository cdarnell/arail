"""Production Readiness admin section render + endpoint regression tests.

Verifies:
  - The admin.html template ships the three PR card mounts (#pr-perf,
    #pr-cleanup, #pr-security).
  - The Quick Actions block has the 7th button (Publish Guide).
  - Pre-existing admin endpoints (/api/admin/components,
    /api/admin/check-updates, /api/system/health) still respond — i.e.
    the new endpoint inserts didn't break neighbours.
  - /api/admin/perf/queue returns the scheduler.snapshot() shape.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ADMIN_HTML = (
    Path(__file__).resolve().parent.parent
    / "src" / "arail" / "portal" / "templates" / "admin.html"
)


@pytest.fixture(scope="module")
def admin_html_text() -> str:
    return ADMIN_HTML.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Template structure
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mount_id", ["pr-perf", "pr-cleanup", "pr-security"])
def test_pr_card_mount_present(admin_html_text, mount_id):
    """Each Production Readiness card has its DOM mount."""
    assert f'id="{mount_id}"' in admin_html_text, (
        f"Missing #{mount_id} mount in admin.html"
    )


def test_publish_guide_quick_action_present(admin_html_text):
    """Quick Actions has the 7th button linking to /docs/PUBLISH.md."""
    assert "/docs/PUBLISH.md" in admin_html_text, (
        "Quick Actions block must have a button linking to /docs/PUBLISH.md"
    )


def test_loadperf_loadcleanup_loadsecurity_drivers_present(admin_html_text):
    """JS drivers wired up."""
    for fn in ("loadPerf", "loadCleanup", "loadSecurity"):
        assert fn in admin_html_text, f"JS driver {fn}() missing from admin.html"


def test_perf_polling_pauses_on_visibility_hidden(admin_html_text):
    """F4 mitigation: setInterval pauses when document.hidden."""
    # The architect specified `if (!document.hidden)` guard.
    assert "document.hidden" in admin_html_text, (
        "Perf polling must guard on document.hidden (F4)"
    )


# ---------------------------------------------------------------------------
# Endpoint regression — pre-existing admin endpoints still respond
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    from arail.portal.app import app
    return TestClient(app)


def test_api_system_health_still_returns(client):
    """Pre-existing /api/system/health must still return JSON, not 5xx."""
    r = client.get("/api/system/health")
    assert r.status_code == 200, r.text
    body = r.json()
    # Existing shape — at minimum has system info (we don't pin the whole shape
    # because it's an existing endpoint with many fields).
    assert isinstance(body, dict)


def test_api_admin_components_still_returns(client):
    r = client.get("/api/admin/components")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), (list, dict))


def test_api_admin_check_updates_still_returns(client):
    r = client.get("/api/admin/check-updates")
    # check-updates may take a moment but must respond cleanly.
    assert r.status_code == 200, r.text


def test_api_admin_perf_queue_returns_snapshot_shape(client):
    """Happy path: /api/admin/perf/queue returns the documented snapshot dict."""
    r = client.get("/api/admin/perf/queue")
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("capacity", "in_flight", "pending", "completed_5m",
              "wait_ms", "run_ms", "fast_path_ms"):
        assert k in body, f"perf/queue missing {k}"
    assert isinstance(body["wait_ms"], dict)
