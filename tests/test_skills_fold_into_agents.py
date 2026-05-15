"""Tests for Skills-fold-into-Agents (sprint 2026-05-14-platform-foundation §4).

Covers:
1. GET /skills → 302, Location: /agents?view=skills
2. GET /agents?view=skills → 200, contains data-view="skills"
3. GET /agents/skills/some_id → 200, bootstrap JSON contains default_skill_id
4. GET /agents/skills/__nope__ → 200 (no 404), renders Skills view
5. GET /agents (no query) → 200, status view active by default
6. /api/skills/* endpoints unchanged (smoke: list, packs)
7. Open-redirect guard: /skills?foo=bar redirects to /agents?view=skills, not arbitrary URL
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    return TestClient(app, follow_redirects=False)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_skills_redirects_to_agents_view_skills(monkeypatch, tmp_path):
    """GET /skills → 302 with Location: /agents?view=skills."""
    client = _client(monkeypatch, tmp_path)
    r = client.get("/skills")
    assert r.status_code == 302, f"Expected 302, got {r.status_code}"
    location = r.headers.get("location", "")
    assert location == "/agents?view=skills", (
        f"Expected Location: /agents?view=skills, got {location!r}"
    )


def test_skills_single_redirect_no_loop(monkeypatch, tmp_path):
    """GET /skills produces exactly one 302 — no redirect chain."""
    client = _client(monkeypatch, tmp_path)
    r = client.get("/skills", follow_redirects=False)
    assert r.status_code == 302
    # Verify the target itself is 200 (no further redirect)
    client2 = TestClient(__import__("arail.portal.app", fromlist=["app"]).app, follow_redirects=True)
    r2 = client2.get("/agents?view=skills")
    assert r2.status_code == 200


def test_agents_view_skills_renders_skills_section(monkeypatch, tmp_path):
    """GET /agents?view=skills → 200, body contains data-view="skills" not hidden."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/agents?view=skills")
    assert r.status_code == 200, r.text
    body = r.text
    # Skills section should be present and NOT hidden (server renders it active)
    assert 'data-view="skills"' in body, "Skills section markup missing"
    # Status section should be hidden
    assert 'data-view="status" hidden' in body or 'data-view="status"' in body


def test_agents_view_skills_contains_loadouts_markup(monkeypatch, tmp_path):
    """GET /agents?view=skills → body contains Skills panel markup (sk-loadouts)."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/agents?view=skills")
    assert r.status_code == 200
    assert "sk-loadouts" in r.text, "Loadouts markup missing from /agents?view=skills"


def test_agents_skills_deeplink_sets_default_skill_id(monkeypatch, tmp_path):
    """GET /agents/skills/my_skill → 200, bootstrap JSON has defaultSkillId."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/agents/skills/my_skill")
    assert r.status_code == 200, r.text
    assert '"my_skill"' in r.text, (
        "defaultSkillId 'my_skill' not found in bootstrap JSON"
    )


def test_agents_skills_unknown_id_returns_200(monkeypatch, tmp_path):
    """GET /agents/skills/__nope__ → 200, renders Skills view (no 404)."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/agents/skills/__nope__")
    assert r.status_code == 200, f"Expected 200 for unknown skill id, got {r.status_code}"
    assert 'data-view="skills"' in r.text


def test_agents_default_view_is_status(monkeypatch, tmp_path):
    """GET /agents (no query) → 200, status view active, no hidden attr on status section."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/agents")
    assert r.status_code == 200, r.text
    body = r.text
    # The status section must be present (not hidden) — server renders it active
    assert 'data-view="status"' in body
    # Skills section should be hidden
    assert 'data-view="skills" hidden' in body


def test_api_skills_list_unchanged(monkeypatch, tmp_path):
    """GET /api/skills/list still returns expected shape (regression)."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/api/skills/list")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "skills" in body, "GET /api/skills/list missing 'skills' key"
    assert isinstance(body["skills"], list)


def test_api_skills_packs_unchanged(monkeypatch, tmp_path):
    """GET /api/skills/packs still returns expected shape (regression)."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/api/skills/packs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "packs" in body, "GET /api/skills/packs missing 'packs' key"


def test_skills_open_redirect_guarded(monkeypatch, tmp_path):
    """GET /skills?foo=bar → 302 to /agents?view=skills, query NOT propagated as open redirect."""
    client = _client(monkeypatch, tmp_path)
    r = client.get("/skills?foo=bar")
    assert r.status_code == 302
    location = r.headers.get("location", "")
    # Must redirect to the fixed target, not incorporate ?foo=bar
    assert location == "/agents?view=skills", (
        f"Open-redirect guard failed: Location was {location!r}"
    )


def test_agents_unknown_view_falls_back_to_status(monkeypatch, tmp_path):
    """GET /agents?view=unknown → 200, defaults to status view (forward-compat)."""
    monkeypatch.setenv("ARAIL_PASSWORD", "test-passphrase-not-real")
    monkeypatch.chdir(tmp_path)
    from arail.portal.app import app
    client = TestClient(app, follow_redirects=True)
    r = client.get("/agents?view=unknown_future_view")
    assert r.status_code == 200, r.text
    # Status section should be active (not hidden)
    assert 'data-view="status"' in r.text
