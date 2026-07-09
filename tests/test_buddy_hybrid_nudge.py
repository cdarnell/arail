"""Buddy hybrid-research nudge — fires only while airgapped, mirrors
_suggest_internet_correlation (which fires only in hybrid)."""

from __future__ import annotations

import pytest

from arail.agents import _builtin_buddy as buddy_mod


def test_nudge_fires_airgapped_with_goal(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    obs = buddy_mod._suggest_hybrid_for_research({"id": "g1", "title": "spec decoding study"})
    assert obs is not None
    assert obs.severity == "suggest"
    assert obs.watcher == "airgap:hybrid-nudge"
    assert obs.cooldown_sec >= 24 * 3600
    assert obs.suggestion == {"kind": "airgap", "target": "hybrid", "link": "/"}
    assert "Hybrid" in obs.fact


def test_nudge_silent_in_hybrid(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    assert buddy_mod._suggest_hybrid_for_research({"id": "g1", "title": "x"}) is None


def test_nudge_silent_without_goal_title(monkeypatch):
    monkeypatch.setenv("LAB_MODE", "airgapped")
    assert buddy_mod._suggest_hybrid_for_research({"id": "g1"}) is None


def test_nudge_registered_in_suggesters():
    assert buddy_mod._suggest_hybrid_for_research in buddy_mod.SUGGESTERS
