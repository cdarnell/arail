"""The generic `user_data` reveal slot (Phase E).

Covers POST /api/system/reveal with slot="user_data" — resolves to
DATA_DIR / "user-import", creates the directory on demand, and refuses
traversal escapes the same as every other slot.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient


def _setup_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LAB_PKB", str(tmp_path / "pkb"))
    monkeypatch.setenv("ARAIL_MODELS_DIR", str(tmp_path / "models"))
    monkeypatch.setenv("ARAIL_HEADLESS", "1")
    monkeypatch.setenv("ARAIL_MODE", "airgapped")
    monkeypatch.setenv("LAB_WIKI_AUTO_REBUILD", "false")
    import arail.config
    monkeypatch.setattr(arail.config, "PKB_ROOT", tmp_path / "pkb")
    monkeypatch.setattr(arail.config, "DATA_DIR", tmp_path / "data")


def test_reveal_user_data_creates_and_returns_path(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post("/api/system/reveal", json={"slot": "user_data"})
    assert r.status_code == 200
    data = r.json()
    assert data["path"].endswith("/user-import")
    assert (tmp_path / "data" / "user-import").is_dir()


def test_reveal_user_data_subpath_for_world_findings(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post(
        "/api/system/reveal",
        json={"slot": "user_data", "subpath": "debt-finance/findings"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["path"].endswith("/user-import/debt-finance/findings")
    assert (tmp_path / "data" / "user-import" / "debt-finance" / "findings").is_dir()


def test_reveal_user_data_traversal_rejected(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post(
        "/api/system/reveal",
        json={"slot": "user_data", "subpath": "../../etc"},
    )
    assert r.status_code == 400
    assert "escapes" in r.json()["error"].lower()


def test_reveal_valid_slots_include_user_data(monkeypatch, tmp_path):
    _setup_env(monkeypatch, tmp_path)
    from arail.portal.app import app

    client = TestClient(app)
    r = client.post("/api/system/reveal", json={"slot": "not-a-slot"})
    assert r.status_code == 400
    assert "user_data" in r.json()["valid"]
