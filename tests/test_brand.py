"""Brand smoke tests — env var loading + template wiring."""

from __future__ import annotations

import pytest

from arail import brand


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    for k in ("LAB_NAME", "LAB_SHORT_NAME", "LAB_TAGLINE", "LAB_LOGO"):
        monkeypatch.delenv(k, raising=False)
    brand.reset_brand_cache()
    yield
    brand.reset_brand_cache()


def test_defaults_are_autoresearch_lab():
    b = brand.load_brand()
    assert b.name == "Autoresearch AI Lab"
    assert b.short_name == "autoresearch-lab"
    assert b.tagline == "A learn-by-doing AI research lab"
    assert b.logo == "⟨Autoresearch⟩"
    assert b.version == "1.0.0"


def test_env_override_custom_name(monkeypatch):
    monkeypatch.setenv("LAB_NAME", "PeanutLab")
    b = brand.load_brand()
    assert b.name == "PeanutLab"
    assert b.short_name == "peanutlab"  # derived from name
    assert b.logo == "⟨PeanutLab⟩"       # derived from name


def test_env_override_all_fields(monkeypatch):
    monkeypatch.setenv("LAB_NAME", "Atlas")
    monkeypatch.setenv("LAB_SHORT_NAME", "atl")
    monkeypatch.setenv("LAB_TAGLINE", "Soil science lab")
    monkeypatch.setenv("LAB_LOGO", "⌂Atlas⌂")
    b = brand.load_brand()
    assert b.name == "Atlas"
    assert b.short_name == "atl"
    assert b.tagline == "Soil science lab"
    assert b.logo == "⌂Atlas⌂"


def test_short_name_slugs_spaces(monkeypatch):
    monkeypatch.setenv("LAB_NAME", "Peanut Research Lab")
    b = brand.load_brand()
    assert b.short_name == "peanut-research-lab"


def test_to_dict_serializable():
    d = brand.load_brand().to_dict()
    assert set(d.keys()) == {"name", "short_name", "tagline", "logo", "version"}
    import json
    json.dumps(d)  # must not raise


def test_cache_reset(monkeypatch):
    monkeypatch.setenv("LAB_NAME", "Before")
    assert brand.cached_brand().name == "Before"
    monkeypatch.setenv("LAB_NAME", "After")
    # Without reset, cache still returns the old value.
    assert brand.cached_brand().name == "Before"
    brand.reset_brand_cache()
    assert brand.cached_brand().name == "After"


def test_portal_templates_expose_brand(monkeypatch):
    """The per-request identity context exposes the operator brand when no World
    is mounted.

    The old module-level Jinja ``brand`` global was REMOVED in the
    2026-06-14 world-identity-flip sprint so the lab identity can flip live with
    a mounted World (a module global would have required a restart). Brand is now
    resolved per request via ``_identity_ctx()`` → ``effective_identity()``;
    routes spread ``**_identity_ctx()`` into the template context. Do NOT
    reintroduce the global — that resurrects the restart bug.
    """
    monkeypatch.setenv("LAB_NAME", "TestLab")
    brand.reset_brand_cache()
    from arail.portal import app as app_module
    ctx = app_module._identity_ctx()  # no World mounted (autouse _no_ambient_world_mount)
    assert "brand" in ctx
    assert ctx["brand"].name == "TestLab"
