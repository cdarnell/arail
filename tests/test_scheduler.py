"""Scheduler smoke tests — window parsing + halt flag."""

from __future__ import annotations

import os
from datetime import datetime

import pytest

from oglab import scheduler


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 4, 14, hour, minute)


@pytest.fixture(autouse=True)
def _reset_env(monkeypatch):
    """Each test gets a clean env and a cleared halt flag."""
    for key in ("LAB_ACTIVE_HOURS", "LAB_HEAVY_HOURS", "LAB_STARTUP_DELAY_SEC"):
        monkeypatch.delenv(key, raising=False)
    scheduler.resume_all_jobs()
    yield
    scheduler.resume_all_jobs()


def test_defaults_cover_full_day():
    """Default 08:00-22:00 active + 22:00-08:00 heavy leaves no idle gap."""
    for h in range(24):
        w = scheduler.current_window(_at(h))
        assert w in ("active", "heavy"), f"hour {h} fell through to {w}"


def test_active_window_default():
    assert scheduler.current_window(_at(9)) == "active"
    assert scheduler.current_window(_at(12)) == "active"
    assert scheduler.current_window(_at(21, 59)) == "active"


def test_heavy_window_default():
    assert scheduler.current_window(_at(22)) == "heavy"
    assert scheduler.current_window(_at(3)) == "heavy"
    assert scheduler.current_window(_at(7, 59)) == "heavy"


def test_wrap_around_range(monkeypatch):
    """22:00-08:00 must wrap around midnight."""
    monkeypatch.setenv("LAB_HEAVY_HOURS", "22:00-08:00")
    assert scheduler.current_window(_at(23)) == "heavy"
    assert scheduler.current_window(_at(2)) == "heavy"
    assert scheduler.current_window(_at(7, 59)) == "heavy"


def test_idle_gap(monkeypatch):
    """Non-overlapping windows with a gap must report 'idle' in the gap."""
    monkeypatch.setenv("LAB_ACTIVE_HOURS", "09:00-17:00")
    monkeypatch.setenv("LAB_HEAVY_HOURS", "01:00-05:00")
    assert scheduler.current_window(_at(18)) == "idle"
    assert scheduler.current_window(_at(7)) == "idle"
    assert scheduler.current_window(_at(12)) == "active"
    assert scheduler.current_window(_at(3)) == "heavy"


def test_heavy_precedence_over_active(monkeypatch):
    """When ranges overlap, heavy wins (so the GPU burns during the overlap)."""
    monkeypatch.setenv("LAB_ACTIVE_HOURS", "00:00-23:59")
    monkeypatch.setenv("LAB_HEAVY_HOURS", "22:00-23:00")
    assert scheduler.current_window(_at(22, 30)) == "heavy"
    assert scheduler.current_window(_at(12)) == "active"


def test_malformed_range_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("LAB_ACTIVE_HOURS", "not-a-range")
    monkeypatch.setenv("LAB_HEAVY_HOURS", "also-bad")
    # Default ranges still apply
    assert scheduler.current_window(_at(12)) == "active"
    assert scheduler.current_window(_at(3)) == "heavy"


def test_halt_flag_roundtrip():
    assert scheduler.jobs_halted() is False
    scheduler.halt_all_jobs()
    assert scheduler.jobs_halted() is True
    scheduler.resume_all_jobs()
    assert scheduler.jobs_halted() is False


def test_startup_delay_default_and_override(monkeypatch):
    assert scheduler.startup_delay_seconds() == 300
    monkeypatch.setenv("LAB_STARTUP_DELAY_SEC", "42")
    assert scheduler.startup_delay_seconds() == 42
    monkeypatch.setenv("LAB_STARTUP_DELAY_SEC", "-5")
    assert scheduler.startup_delay_seconds() == 0
    monkeypatch.setenv("LAB_STARTUP_DELAY_SEC", "not-an-int")
    assert scheduler.startup_delay_seconds() == 300


def test_state_snapshot_shape():
    s = scheduler.state()
    assert set(s.keys()) >= {
        "window", "label", "halted",
        "active_hours", "heavy_hours", "startup_delay_sec",
    }
    assert s["window"] in ("active", "heavy", "idle")
    assert s["halted"] is False
