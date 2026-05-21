"""B1 fix-loop integration tests: cloud gallery server↔frontend contract.

Sprint: 2026-05-18-provider-aware-chat-dropdown, fix-loop pass.

The server writes cloud models to gallery.catalog; the frontend was reading
gallery.installed (always [] for cloud) — so the success path always hit the
"No models returned" empty state even when models existed (REVIEW.md B1).

These tests prove the server-side contract: a successful cloud fetch returns
gallery.catalog with ≥1 entry, and gallery.installed is [] (the documented
shape). The local branch (no provider) must be byte-unchanged (R1 remains).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


# ---------------------------------------------------------------------------
# B1-INT-1: cloud success path returns models in gallery.catalog (not .installed)
# ---------------------------------------------------------------------------

def test_cloud_success_models_in_gallery_catalog(monkeypatch):
    """B1 contract: a successful cloud fetch must populate gallery.catalog
    with ≥1 entry. gallery.installed must be [] (server contract per ARCHITECTURE.md A4)."""
    monkeypatch.setenv("LAB_MODE", "hybrid")

    from arail.portal import app as portal_app
    from fastapi.testclient import TestClient

    fake_models = ["claude-opus-4-7", "claude-sonnet-4-20250514", "claude-haiku-3-5"]

    with patch.object(portal_app, "_provider_token", return_value="sk-test-token"), \
         patch.object(portal_app, "_fetch_provider_models", return_value=fake_models):
        client = TestClient(portal_app.app, raise_server_exceptions=False)
        r = client.get("/api/chat/models?provider=claude")

    assert r.status_code == 200
    body = r.json()
    gallery = body.get("gallery", {})

    catalog = gallery.get("catalog", [])
    assert len(catalog) >= 1, (
        f"B1: gallery.catalog must have ≥1 entry on cloud success, got: {catalog!r}"
    )

    # Verify catalog entry shape
    entry = catalog[0]
    assert "id" in entry, f"catalog entry must have 'id' key, got: {entry.keys()}"
    assert entry.get("installed_state") == "available", (
        f"cloud catalog entry installed_state must be 'available', got: {entry.get('installed_state')!r}"
    )
    assert entry.get("source") == "cloud", (
        f"cloud catalog entry source must be 'cloud', got: {entry.get('source')!r}"
    )

    # gallery.installed must be [] for cloud (documented shape)
    installed = gallery.get("installed", "MISSING")
    assert installed == [], (
        f"B1: gallery.installed must be [] for cloud providers, got: {installed!r}"
    )


def test_cloud_success_catalog_ids_match_model_list(monkeypatch):
    """B1 contract: every model id in the top-level 'models' list must appear
    in gallery.catalog as an entry with matching 'id'."""
    monkeypatch.setenv("LAB_MODE", "hybrid")

    from arail.portal import app as portal_app
    from fastapi.testclient import TestClient

    fake_models = ["model-a", "model-b", "model-c"]

    with patch.object(portal_app, "_provider_token", return_value="sk-test-token"), \
         patch.object(portal_app, "_fetch_provider_models", return_value=fake_models):
        client = TestClient(portal_app.app, raise_server_exceptions=False)
        r = client.get("/api/chat/models?provider=claude")

    body = r.json()
    gallery = body.get("gallery", {})
    catalog_ids = {e["id"] for e in gallery.get("catalog", [])}

    for mid in fake_models:
        assert mid in catalog_ids, (
            f"Model {mid!r} from models list not found in gallery.catalog ids: {catalog_ids!r}"
        )


def test_cloud_success_gallery_catalog_not_empty_means_cards_renderable(monkeypatch):
    """B1 contract: if gallery.catalog has entries, the JS can render model cards.
    Prove the server returns the right shape for the JS to iterate over."""
    monkeypatch.setenv("LAB_MODE", "hybrid")

    from arail.portal import app as portal_app
    from fastapi.testclient import TestClient

    fake_models = ["gpt-4o", "gpt-4o-mini"]

    with patch.object(portal_app, "_provider_token", return_value="sk-test-token"), \
         patch.object(portal_app, "_fetch_provider_models", return_value=fake_models):
        client = TestClient(portal_app.app, raise_server_exceptions=False)
        r = client.get("/api/chat/models?provider=nvidia")

    body = r.json()
    gallery = body.get("gallery", {})
    catalog = gallery.get("catalog", [])

    # The JS does: cloudCatalog.map(e => e.id)
    # Every catalog entry must have a non-empty 'id' field
    for entry in catalog:
        assert entry.get("id"), (
            f"catalog entry missing or empty 'id': {entry!r}"
        )
        assert entry.get("runtime") == "nvidia", (
            f"catalog entry 'runtime' must match provider 'nvidia', got: {entry.get('runtime')!r}"
        )


# ---------------------------------------------------------------------------
# B1-INT-2: no-token path must still return empty catalog (not models)
# ---------------------------------------------------------------------------

def test_no_token_returns_empty_catalog_not_models(monkeypatch):
    """B1: on no-token CTA path, gallery.catalog must be [] (empty state is intentional)."""
    monkeypatch.setenv("LAB_MODE", "hybrid")

    from arail.portal import app as portal_app
    from fastapi.testclient import TestClient

    with patch.object(portal_app, "_provider_token", return_value=""):
        client = TestClient(portal_app.app, raise_server_exceptions=False)
        r = client.get("/api/chat/models?provider=claude")

    body = r.json()
    gallery = body.get("gallery", {})
    assert gallery.get("catalog") == [], (
        "No-token path must return empty gallery.catalog, not models"
    )
    assert body.get("cta", {}).get("kind") == "no_token", (
        "No-token path must include cta.kind=='no_token'"
    )


# ---------------------------------------------------------------------------
# B1-INT-3: local (no provider) path still uses gallery.installed (R1 guard)
# ---------------------------------------------------------------------------

def test_local_no_provider_path_gallery_installed_is_list(monkeypatch):
    """B1/R1: local path (no ?provider=) must still return gallery.installed as
    a list. The local branch is byte-unchanged — this confirms no regression."""
    monkeypatch.setenv("LAB_MODE", "airgapped")

    from arail.portal import app as portal_app
    from fastapi.testclient import TestClient

    client = TestClient(portal_app.app, raise_server_exceptions=False)
    r = client.get("/api/chat/models")

    assert r.status_code == 200
    body = r.json()
    gallery = body.get("gallery", {})

    # installed must be a list (legacy shape)
    assert isinstance(gallery.get("installed"), list), (
        f"Local path: gallery.installed must be a list, got: {type(gallery.get('installed'))}"
    )
    # catalog must also be a list (legacy shape)
    assert isinstance(gallery.get("catalog"), list), (
        f"Local path: gallery.catalog must be a list, got: {type(gallery.get('catalog'))}"
    )
    # The airgap field must NOT be true on local path
    assert body.get("airgapped") is not True, (
        "Local path: airgapped must not be true"
    )
