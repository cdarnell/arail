"""First-run onboarding flow — passphrase detection + /welcome endpoint.

Verifies:
  - _lab_password_set() recognizes real values, rejects placeholders
  - HTML routes redirect to /welcome when no password is set
  - API routes return 401 when no password is set
  - /api/welcome/setup writes the password to .env, lab.conf, and
    code-server config; refuses to overwrite an existing password
  - The middleware unblocks once the password is set
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Don't import app at module level — we need to control the env var
# before the middleware checks it on the first request.


@pytest.fixture
def fresh_lab(monkeypatch, tmp_path):
    """Run each test in a temp working dir with no ARAIL_PASSWORD.

    Overrides the autouse fixture from conftest.py so we exercise the
    no-password path. Also chdir's into a temp dir so .env / lab.conf
    writes don't pollute the real repo.
    """
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    monkeypatch.delenv("OPEN_NOTEBOOK_ENCRYPTION_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    # Point HOME at the tmp dir so the code-server write doesn't touch
    # the real ~/.config.
    monkeypatch.setenv("HOME", str(tmp_path))
    yield tmp_path


def _new_client():
    from arail.portal.app import app
    return TestClient(app)


def test_lab_password_set_recognizes_real_value(monkeypatch):
    from arail.portal.app import _lab_password_set
    monkeypatch.setenv("ARAIL_PASSWORD", "a-real-passphrase-32-chars-here-x")
    assert _lab_password_set() is True


def test_lab_password_set_rejects_empty(monkeypatch, tmp_path):
    from arail.portal.app import _lab_password_set
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env to fall back to
    assert _lab_password_set() is False


def test_lab_password_set_rejects_placeholder(monkeypatch, tmp_path):
    from arail.portal.app import _lab_password_set
    monkeypatch.setenv("ARAIL_PASSWORD", "__needs_setup__")
    monkeypatch.chdir(tmp_path)
    assert _lab_password_set() is False


def test_lab_password_set_falls_back_to_env_file(monkeypatch, tmp_path):
    """Env var empty but .env on disk has a real password — should
    detect it (and pull it into os.environ for downstream callers)."""
    from arail.portal.app import _lab_password_set
    monkeypatch.delenv("ARAIL_PASSWORD", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("ARAIL_PASSWORD=hello-from-env-file\n")
    assert _lab_password_set() is True
    # Should also have populated os.environ.
    assert os.environ.get("ARAIL_PASSWORD") == "hello-from-env-file"


def test_html_route_redirects_to_welcome_when_unset(fresh_lab):
    client = _new_client()
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/welcome"


def test_api_route_returns_401_when_unset(fresh_lab):
    client = _new_client()
    r = client.get("/api/jobs/state")
    assert r.status_code == 401
    assert r.json().get("error") == "lab_not_onboarded"


def test_welcome_page_renders_when_unset(fresh_lab):
    client = _new_client()
    r = client.get("/welcome")
    assert r.status_code == 200
    assert "Welcome" in r.text
    assert "Passphrase" in r.text


def test_welcome_setup_writes_credentials(fresh_lab):
    client = _new_client()
    r = client.post("/api/welcome/setup", json={
        "passphrase": "a-real-passphrase-here",
        "confirm":    "a-real-passphrase-here",
        "lab_name":   "Test Lab",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True

    env_text = (fresh_lab / ".env").read_text()
    assert "ARAIL_PASSWORD=a-real-passphrase-here" in env_text
    assert "OPEN_NOTEBOOK_ENCRYPTION_KEY=a-real-passphrase-here" in env_text
    assert "LAB_NAME=Test Lab" in env_text

    lab_conf = (fresh_lab / "lab.conf").read_text()
    assert "IDE_PASSWORD=a-real-passphrase-here" in lab_conf

    cs_cfg = (fresh_lab / ".config" / "code-server" / "config.yaml").read_text()
    assert "password: a-real-passphrase-here" in cs_cfg


def test_welcome_setup_rejects_short_passphrase(fresh_lab):
    client = _new_client()
    r = client.post("/api/welcome/setup", json={
        "passphrase": "short",
        "confirm":    "short",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "8 characters" in body["error"]


def test_welcome_setup_rejects_mismatched_confirm(fresh_lab):
    client = _new_client()
    r = client.post("/api/welcome/setup", json={
        "passphrase": "a-real-passphrase-here",
        "confirm":    "different-passphrase-here",
    })
    body = r.json()
    assert body["ok"] is False
    assert "match" in body["error"]


def test_welcome_setup_refuses_overwrite_when_already_onboarded(monkeypatch, tmp_path):
    """Once a real password exists, /api/welcome/setup must 409 to
    prevent an unauthenticated overwrite."""
    monkeypatch.setenv("ARAIL_PASSWORD", "already-set-passphrase")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    client = _new_client()
    r = client.post("/api/welcome/setup", json={
        "passphrase": "trying-to-overwrite-here",
        "confirm":    "trying-to-overwrite-here",
    })
    assert r.status_code == 409
    body = r.json()
    assert body["ok"] is False


def test_dashboard_unblocks_after_onboarding(fresh_lab):
    """End-to-end: blocked → onboard → dashboard reachable."""
    client = _new_client()
    # First request: blocked.
    assert client.get("/", follow_redirects=False).status_code == 302
    # Onboard.
    r = client.post("/api/welcome/setup", json={
        "passphrase": "shiny-new-passphrase",
        "confirm":    "shiny-new-passphrase",
    })
    assert r.json()["ok"] is True
    # Dashboard now reachable.
    assert client.get("/", follow_redirects=False).status_code == 200
