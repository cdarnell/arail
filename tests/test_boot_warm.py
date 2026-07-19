"""Boot warm: _warm_primary_router issues a real 1-token completion so
"warmed" means weights-resident, and /api/ready reports tier-0 honestly."""

from __future__ import annotations

import asyncio

import pytest


class _FakeRouter:
    backend_name = "ollama_native"

    def __init__(self):
        self.calls = []

    def complete(self, prompt, max_tokens=512, *a, **k):
        self.calls.append((prompt, max_tokens))

        class _R:
            text = "ok"
        return _R()


@pytest.fixture
def wired(monkeypatch, tmp_path):
    from arail.registry import core as reg_core
    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE",
                       str(tmp_path / "model_registry.json"))
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "ai-engineer:latest")
    monkeypatch.delenv("MODEL_API_BASE", raising=False)
    reg_core.reset_registry()

    import arail.portal.app as app_mod
    fake = _FakeRouter()
    monkeypatch.setattr(app_mod, "_get_primary_router", lambda: fake)
    yield app_mod, fake
    reg_core.reset_registry()


def test_boot_warm_issues_one_token_completion(wired, monkeypatch):
    app_mod, fake = wired
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert fake.calls == [("ok", 1)]
    assert app_mod._MODEL_WARM is True
    # Ran under the inference slot with its own label.
    from arail.portal import scheduler
    snap = scheduler.per_label_snapshot()
    assert "model-warm" in snap


def test_boot_warm_disabled_by_env(wired, monkeypatch):
    app_mod, fake = wired
    monkeypatch.setenv("ARAIL_TIER0_BOOT_WARM", "0")
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert fake.calls == []
    assert app_mod._MODEL_WARM is True


def test_boot_warm_failure_still_flips_warm(wired, monkeypatch):
    app_mod, fake = wired

    def _boom(*a, **k):
        raise ConnectionError("ollama down")
    monkeypatch.setattr(fake, "complete", _boom)
    app_mod._MODEL_WARM = False
    asyncio.run(app_mod._warm_primary_router())
    assert app_mod._MODEL_WARM is True     # overlay must never trap the user


def test_ready_reports_tier0_status(wired):
    app_mod, _ = wired
    from fastapi.testclient import TestClient
    with TestClient(app_mod.app) as client:
        body = client.get("/api/ready").json()
        assert "tier0" in body
        assert body["tier0"] in ("unknown", "healthy", "cold", "warming",
                                 "unhealthy", "not_installed", None)
