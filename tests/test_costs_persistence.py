"""Cost history + cache/recap counters survive restarts (totals always did)."""

from __future__ import annotations

import json

import pytest

from arail import costs as costs_mod


@pytest.fixture
def tracker(monkeypatch, tmp_path):
    import arail.config as config_mod
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    path = tmp_path / "costs.json"

    def _fresh():
        costs_mod.CostTracker._instance = None
        return costs_mod.CostTracker()

    yield _fresh, path
    costs_mod.CostTracker._instance = None


def test_history_and_counters_survive_restart(tracker):
    fresh, path = tracker
    t1 = fresh()
    t1.track("ollama_native", "ai-engineer", 100, 50, 42.0, "agent",
             recap_depth=1, cache_read_input_tokens=7,
             cache_creation_input_tokens=3,
             provider="local", entry_id="tier0-local", tab="research")
    assert len(t1._history) == 1

    t2 = fresh()                                  # "restart"
    assert t2.total_calls == 1
    assert len(t2._history) == 1                  # used to reset to []
    assert t2._history[0]["provider"] == "local"
    assert t2.calls_by_recap_depth == {1: 1}      # used to reset to {}
    assert t2.total_cache_read_tokens == 7
    assert t2.total_cache_creation_tokens == 3


def test_legacy_costs_file_loads(tracker):
    fresh, path = tracker
    path.write_text(json.dumps({
        "total_tokens_in": 10, "total_tokens_out": 5, "total_calls": 2,
        "total_cloud_usd": 1.0, "started_at": 123.0,
    }))
    t = fresh()
    assert t.total_calls == 2
    assert t._history == []                       # absent → default, no crash
    assert t.calls_by_recap_depth == {}
