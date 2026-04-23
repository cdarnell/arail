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
    assert b.version == "0.1.0"


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
    """Imported portal app injects brand into the Jinja globals."""
    monkeypatch.setenv("LAB_NAME", "TestLab")
    brand.reset_brand_cache()
    # Re-import app to pick up the new env (module load time captures it).
    import importlib
    from arail.portal import app as app_module
    importlib.reload(app_module)
    globals_dict = app_module.templates.env.globals
    assert "brand" in globals_dict
    assert globals_dict["brand"].name == "TestLab"
