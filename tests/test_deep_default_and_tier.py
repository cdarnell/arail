"""AeroLLM is the default 2nd inference + tier gating surfaces in deep_info."""
from __future__ import annotations

import importlib.util

import pytest
from fastapi.testclient import TestClient


def _aerollm_present() -> bool:
    return importlib.util.find_spec("aerollm_api") is not None


def test_resolver_prefers_aerollm_when_importable(monkeypatch):
    monkeypatch.delenv("ARAIL_DEEP_BACKEND", raising=False)
    if not _aerollm_present():
        pytest.skip("aerollm_api not installed in this env")
    from arail.portal import app as app_mod
    assert app_mod._resolve_default_deep_backend() == "aerollm"


def test_deep_info_minimalist_shows_upgrade_nudge(monkeypatch):
    monkeypatch.setenv("LAB_TIER", "minimalist")
    from arail.portal import app as app_mod
    r = TestClient(app_mod.app).get("/api/chat/models")
    assert r.status_code == 200, r.text
    deep = r.json().get("deep") or {}
    assert deep.get("available_in_tier") is False
    assert "upgrade" in (deep.get("upgrade_command") or "").lower()
    assert deep.get("tier") == "minimalist"
    assert "frontier" in deep  # flag present regardless of value


def test_deep_info_maximus_available(monkeypatch):
    monkeypatch.setenv("LAB_TIER", "maximus")
    from arail.portal import app as app_mod
    r = TestClient(app_mod.app).get("/api/chat/models")
    assert r.status_code == 200, r.text
    deep = r.json().get("deep") or {}
    assert deep.get("available_in_tier") is True
    assert deep.get("tier") == "maximus"
