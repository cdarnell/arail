"""Router airgap gate — cloud backends refused while airgapped.

The gate lives in ModelRouter.__init__ / switch_backend and raises
CloudBackendBlocked BEFORE the backend class is constructed, so these
tests need no SDKs, keys, or network.

Also covers the router-cache changes in the portal: LAB_MODE is part of
_router_signature() and the airgap toggle clears the cache.
"""

from __future__ import annotations

import pytest

from arail.router.core import (CloudBackendBlocked, ModelRouter,
                               _check_cloud_allowed)


@pytest.mark.parametrize("name", ["claude", "huggingface", "openrouter"])
def test_cloud_backend_refused_airgapped(monkeypatch, name):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    with pytest.raises(CloudBackendBlocked) as exc:
        ModelRouter(backend=name)
    assert name in str(exc.value)
    assert "Airgapped" in str(exc.value) or "airgapped" in str(exc.value)


def test_cloud_backend_blocked_is_runtime_error():
    assert issubclass(CloudBackendBlocked, RuntimeError)


def test_check_passes_in_hybrid(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    _check_cloud_allowed("claude")  # must not raise


def test_check_passes_for_local_backends_airgapped(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    for name in ("mlx", "ollama", "cpu"):
        _check_cloud_allowed(name)  # must not raise


def test_switch_backend_gate(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    router = ModelRouter.__new__(ModelRouter)  # skip __init__/backend build
    with pytest.raises(CloudBackendBlocked):
        router.switch_backend("openrouter")


# ── portal router cache ───────────────────────────────────────────────

def test_router_signature_includes_lab_mode(monkeypatch):
    import arail.portal.app as app_mod
    monkeypatch.setenv("LAB_MODE", "airgapped")
    sig_a = app_mod._router_signature()
    monkeypatch.setenv("LAB_MODE", "hybrid")
    sig_b = app_mod._router_signature()
    assert sig_a != sig_b


def test_invalidate_router_cache_clears_globals():
    import arail.portal.app as app_mod
    app_mod._ROUTER_CACHE = object()
    app_mod._ROUTER_CACHE_SIGNATURE = ("x",)
    app_mod._invalidate_router_cache()
    assert app_mod._ROUTER_CACHE is None
    assert app_mod._ROUTER_CACHE_SIGNATURE is None
