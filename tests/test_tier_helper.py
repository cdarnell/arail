"""Shared tier helper — single source of truth used by portal + agents."""
from __future__ import annotations

from arail import tier


def test_default_is_minimalist(monkeypatch):
    monkeypatch.delenv("LAB_TIER", raising=False)
    assert tier.get_current_tier() == "minimalist"
    assert tier.is_maximus() is False


def test_maximus(monkeypatch):
    monkeypatch.setenv("LAB_TIER", "maximus")
    assert tier.get_current_tier() == "maximus"
    assert tier.is_maximus() is True


def test_legacy_min_max_compat(monkeypatch):
    monkeypatch.setenv("LAB_TIER", "max")
    assert tier.get_current_tier() == "maximus"
    monkeypatch.setenv("LAB_TIER", "min")
    assert tier.get_current_tier() == "minimalist"


def test_unknown_falls_back_to_minimalist(monkeypatch):
    monkeypatch.setenv("LAB_TIER", "frontier-plus-ultra")
    assert tier.get_current_tier() == "minimalist"
    assert tier.is_maximus() is False


def test_whitespace_and_case_insensitive(monkeypatch):
    monkeypatch.setenv("LAB_TIER", "  MAXIMUS ")
    assert tier.get_current_tier() == "maximus"


def test_portal_delegates_to_tier_helper(monkeypatch):
    # app._current_tier must agree with the shared helper (no drift).
    from arail.portal import app as app_mod
    monkeypatch.setenv("LAB_TIER", "maximus")
    assert app_mod._current_tier() == tier.get_current_tier() == "maximus"
