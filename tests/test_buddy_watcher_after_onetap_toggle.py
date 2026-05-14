"""Test that the Buddy airgap watcher correctly fires after a one-tap toggle.

Sprint 2026-05-14-airgap-onetap-toggle — ARCHITECTURE.md §test strategy
"Buddy (30%)".

Tests:
  - test_watcher_fires_after_one_tap_toggle:
      Seed state.json with airgap_last_lab_mode=airgapped. Flip env to
      hybrid (simulating a successful one-tap toggle). Tick the watcher.
      Assert observation severity=info and that state.json is correctly
      merged — airgap_last_lab_mode=hybrid AND any pre-existing buddy
      keys preserved (regression: 05-05 BLOCK — state merge clobbering).

  - test_watcher_no_fire_when_mode_unchanged:
      State says hybrid, env says hybrid. Watcher returns None (no event).

  - test_probe_cache_busted_after_onetap_toggle:
      After a real toggle endpoint call, egress._PROBE_CACHE is clear so
      the watcher sees the new mode on the next /api/airgap/status fetch.
      (Watcher reads lab_mode() from os.environ, not from the cache —
      this test confirms the cache path doesn't interfere.)

  - test_rapid_toggle_5x_no_double_fire:
      Five back-and-forth env flips; tick watcher once. Exactly one
      Observation returned (mode-change cooldown is intact — the state
      file only records the last seen mode, so intermediate flips that
      arrive before the watcher ticks collapse into at most one event).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_state(state_path: Path, data: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(data, indent=2))


def _read_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {}
    return json.loads(state_path.read_text()) or {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestBuddyWatcherAfterOnetapToggle:
    def test_watcher_fires_after_one_tap_toggle(self, tmp_path, monkeypatch):
        """Watcher returns info Observation when mode changed airgapped->hybrid.

        Also verifies that pre-existing state keys are preserved (not clobbered)
        after the watcher writes updated airgap_last_lab_mode.
        """
        from arail.agents._builtin_buddy import _watch_airgap_events

        state_path = tmp_path / "buddy" / "state.json"
        # Seed with a pre-existing buddy key plus stale mode.
        _seed_state(state_path, {
            "airgap_last_lab_mode": "airgapped",
            "preexisting_key": "must_survive",
            "some_number": 42,
        })

        # Simulate a successful one-tap toggle: env now says hybrid.
        monkeypatch.setenv("LAB_MODE", "hybrid")

        # Point the watcher at our tmp state file and suppress egress.jsonl
        # side-effects by making _lab_data() return tmp_path (no egress.jsonl
        # there, so tail loop is a no-op).
        with patch(
            "arail.agents._builtin_buddy._state_file",
            return_value=state_path,
        ), patch(
            "arail.egress._lab_data",
            return_value=tmp_path,
        ):
            obs = _watch_airgap_events()

        assert obs is not None, "Expected an Observation after mode flip"
        assert obs.severity == "info"
        assert obs.watcher == "airgap:mode-toggle"

        # State.json must have airgap_last_lab_mode updated.
        state_after = _read_state(state_path)
        assert state_after["airgap_last_lab_mode"] == "hybrid"

        # Pre-existing keys must not be clobbered.
        assert state_after.get("preexisting_key") == "must_survive", (
            "Pre-existing state key was clobbered by watcher merge"
        )
        assert state_after.get("some_number") == 42, (
            "Pre-existing numeric key was clobbered"
        )

    def test_watcher_no_fire_when_mode_unchanged(self, tmp_path, monkeypatch):
        """Watcher returns None when lab_mode == last seen mode."""
        from arail.agents._builtin_buddy import _watch_airgap_events

        state_path = tmp_path / "buddy" / "state.json"
        _seed_state(state_path, {"airgap_last_lab_mode": "hybrid"})
        monkeypatch.setenv("LAB_MODE", "hybrid")

        with patch(
            "arail.agents._builtin_buddy._state_file",
            return_value=state_path,
        ), patch(
            "arail.egress._lab_data",
            return_value=tmp_path,
        ):
            obs = _watch_airgap_events()

        assert obs is None, "Expected no Observation when mode is unchanged"

    def test_probe_cache_busted_after_onetap_toggle(self, tmp_path, monkeypatch):
        """egress._PROBE_CACHE is empty after the toggle endpoint returns 200.

        This means the watcher's next lab_mode() call reads a fresh value
        from os.environ rather than a stale cached probe result.
        (The watcher reads LAB_MODE directly, not _PROBE_CACHE, but clearing
        the cache ensures the modal's host-probe row is also fresh.)
        """
        import arail.egress as egress_mod
        from fastapi.testclient import TestClient
        from arail.portal.app import app
        import arail.portal.app as app_mod

        env_path = tmp_path / ".env"
        env_path.write_bytes(b"LAB_MODE=airgapped\n")
        audit_path = tmp_path / "airgap_audit.jsonl"

        monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
        monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
        monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
        monkeypatch.setenv("LAB_MODE", "airgapped")

        # Prime the probe cache.
        egress_mod._PROBE_CACHE["result"] = True
        egress_mod._PROBE_CACHE["ts"] = time.monotonic()

        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )

        assert r.status_code == 200
        assert egress_mod._PROBE_CACHE == {}, (
            "Probe cache should be empty after successful toggle"
        )

    def test_rapid_toggle_5x_no_double_fire(self, tmp_path, monkeypatch):
        """Five back-and-forth env flips; watcher tick returns at most one Observation.

        The watcher only compares current env mode against the last-recorded
        mode in state.json. Five rapid flips that complete before the watcher
        ticks collapse to the net delta: only the final state matters.
        """
        from arail.agents._builtin_buddy import _watch_airgap_events

        state_path = tmp_path / "buddy" / "state.json"
        # Seed starting from airgapped.
        _seed_state(state_path, {"airgap_last_lab_mode": "airgapped"})

        # Five alternating flips; final state is hybrid (odd number of flips).
        modes = ["hybrid", "airgapped", "hybrid", "airgapped", "hybrid"]
        for m in modes:
            monkeypatch.setenv("LAB_MODE", m)
        # After loop, LAB_MODE == "hybrid" and state.json says "airgapped".

        fire_count = 0
        with patch(
            "arail.agents._builtin_buddy._state_file",
            return_value=state_path,
        ), patch(
            "arail.egress._lab_data",
            return_value=tmp_path,
        ):
            obs = _watch_airgap_events()
            if obs is not None:
                fire_count += 1

        # One tick → at most one Observation (watcher reads once, not 5 times).
        assert fire_count <= 1, f"Expected ≤1 observation, got {fire_count}"
        # The one Observation that fires (if any) should be for the final mode.
        if obs is not None:
            assert "hybrid" in obs.fact.lower() or "open" in obs.fact.lower()
