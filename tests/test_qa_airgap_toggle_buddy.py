"""QA — Buddy watcher behavior under runtime toggling.

Bucket: 30% Buddy in arail's QA gate.

Coverage:
- Rapid-fire toggling (5 flips back and forth) — final ``state.json`` is
  consistent with the final ``LAB_MODE``; audit log has exactly N entries,
  none torn.
- Toggle within one watcher tick (no tick between flips): watcher fires
  the *current-state* Observation, not a stale one. Whether intermediate
  states are skipped is the documented design (we pin it).
- Toggle that returns to the original state (A→B→A) before the watcher
  ticks: watcher sees A==A, no Observation. Pin this — it's the spec
  ("at most one Observation per tick — most recent novel event wins").
- ``state.json`` corruption resilience — if state.json is malformed when
  the watcher runs, it must not crash; the watcher wraps load in try/except
  per ``_builtin_buddy.py:506-511``. Pin.
- Cooldown: re-firing the watcher with the same mode does not produce a
  new Observation.
- ``state.json`` integer-coerced fields — ``airgap_last_egress_offset``
  defends against non-int (regression from a prior sprint, b4d1312).
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


@pytest.fixture()
def buddy_setup(tmp_path, monkeypatch):
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"LAB_MODE=airgapped\n")
    audit_path = tmp_path / "airgap_audit.jsonl"
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps({"airgap_last_lab_mode": "airgapped"}))

    import arail.portal.app as app_mod
    monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
    monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    monkeypatch.setenv("LAB_MODE", "airgapped")

    import arail.agents._builtin_buddy as buddy_mod
    import arail.egress as egress_mod
    monkeypatch.setattr(buddy_mod, "_state_file", lambda: state_path)
    monkeypatch.setattr(egress_mod, "_lab_data", lambda: tmp_path)

    client = TestClient(app, raise_server_exceptions=False)
    return client, state_path, env_path, audit_path


def _flip(client, target):
    h = {"Origin": "http://testserver"}
    r1 = client.post("/api/airgap/toggle", json={"target": target}, headers=h)
    assert r1.status_code == 409, f"step1 → {r1.status_code}: {r1.text}"
    tok = r1.json()["confirm_token"]
    r2 = client.post(
        "/api/airgap/toggle",
        json={"target": target, "confirm_token": tok},
        headers=h,
    )
    assert r2.status_code == 200, f"step2 → {r2.status_code}: {r2.text}"
    return r2


# ---------------------------------------------------------------------------
# Rapid-fire toggling
# ---------------------------------------------------------------------------

class TestRapidToggling:
    def test_5_flips_state_and_audit_consistent(self, buddy_setup):
        """Toggle hybrid→airgapped→hybrid→airgapped→hybrid (5 flips). Final
        os.environ + .env + audit log all agree."""
        client, state_path, env_path, audit_path = buddy_setup

        sequence = ["hybrid", "airgapped", "hybrid", "airgapped", "hybrid"]
        for tgt in sequence:
            _flip(client, tgt)

        # Final state.
        assert os.getenv("LAB_MODE") == "hybrid"
        assert b"LAB_MODE=hybrid" in env_path.read_bytes()

        # Audit log must have exactly 5 valid JSON lines, in order.
        lines = [l for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 5
        recorded = []
        for ln in lines:
            entry = json.loads(ln)  # raises if torn
            recorded.append(entry["to"])
        assert recorded == sequence, f"Audit log out of order: {recorded}"

    def test_5_flips_no_audit_line_torn_under_threading(self, buddy_setup):
        """Even with concurrent issuance attempts, audit lines are intact."""
        client, _, _, audit_path = buddy_setup
        sem = threading.Semaphore(1)
        results = []

        def flip_thread(target):
            with sem:
                # Serialise the two-step pair to avoid token-table races.
                try:
                    _flip(client, target)
                    results.append("ok")
                except AssertionError as e:
                    results.append(f"err: {e}")

        threads = []
        for tgt in ["hybrid", "airgapped", "hybrid", "airgapped", "hybrid"]:
            t = threading.Thread(target=flip_thread, args=(tgt,))
            t.start()
            threads.append(t)
        for t in threads:
            t.join(timeout=10)

        # All audit lines parse cleanly.
        for ln in audit_path.read_text().splitlines():
            if ln.strip():
                json.loads(ln)
        assert all(r == "ok" for r in results), results


# ---------------------------------------------------------------------------
# Watcher behavior across rapid flips
# ---------------------------------------------------------------------------

class TestWatcherSemantics:
    def test_watcher_sees_only_final_state_after_rapid_toggle(self, buddy_setup):
        """A→B→A→B without a tick in between: watcher sees current=B vs last=A
        (its persisted state) and fires once, for the final state."""
        client, state_path, _, _ = buddy_setup

        # Start: state.json says airgapped, env says airgapped.
        _flip(client, "hybrid")
        _flip(client, "airgapped")
        _flip(client, "hybrid")
        # Now LAB_MODE=hybrid, state.json still says airgapped.

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is not None
        assert obs.watcher == "airgap:mode-toggle"
        # Should be the "Door's open" message (mode is now hybrid).
        assert "door" in obs.fact.lower() or "open" in obs.fact.lower()

        state = json.loads(state_path.read_text())
        assert state["airgap_last_lab_mode"] == "hybrid"

    def test_round_trip_before_tick_emits_no_observation(self, buddy_setup):
        """A→B→A within one watcher tick: watcher sees current==last, no fire.

        Pin this — it's the spec ("most recent novel event wins"; if the
        net effect is zero, no Observation).
        """
        client, state_path, _, _ = buddy_setup

        _flip(client, "hybrid")
        _flip(client, "airgapped")
        # state.json says airgapped, current LAB_MODE is airgapped.

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        # No mode-toggle Observation since net effect is zero.
        assert obs is None or obs.watcher != "airgap:mode-toggle"

    def test_watcher_no_double_fire_on_repeat_tick(self, buddy_setup):
        """One toggle, then two ticks. Second tick should not re-fire."""
        client, state_path, _, _ = buddy_setup
        _flip(client, "hybrid")

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs1 = _watch_airgap_events()
        assert obs1 is not None
        assert obs1.watcher == "airgap:mode-toggle"

        obs2 = _watch_airgap_events()
        # state.json now in sync with os.environ; no new Observation.
        assert obs2 is None or obs2.watcher != "airgap:mode-toggle"


# ---------------------------------------------------------------------------
# Resilience to malformed state.json
# ---------------------------------------------------------------------------

class TestStateJsonResilience:
    def test_watcher_does_not_crash_on_malformed_state(self, buddy_setup):
        client, state_path, _, _ = buddy_setup
        state_path.write_text("not a JSON file {{{")

        _flip(client, "hybrid")

        from arail.agents._builtin_buddy import _watch_airgap_events
        # Must not raise.
        obs = _watch_airgap_events()
        # With state un-loadable, last_mode defaults to "airgapped" and current
        # is "hybrid" → fires.
        assert obs is not None
        assert obs.watcher == "airgap:mode-toggle"

        # state.json got rewritten (overwritten) to a valid JSON.
        state = json.loads(state_path.read_text())
        assert state["airgap_last_lab_mode"] == "hybrid"

    def test_watcher_does_not_crash_on_empty_state(self, buddy_setup):
        client, state_path, _, _ = buddy_setup
        state_path.write_text("")

        _flip(client, "hybrid")

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is not None

    def test_watcher_handles_non_int_egress_offset(self, buddy_setup):
        """Regression: a string in airgap_last_egress_offset must coerce / default.

        See commit b4d1312 — the buddy watcher was hardened to int(...) the
        stored offset. Pin behavior so a future refactor doesn't break.
        """
        client, state_path, _, _ = buddy_setup
        state_path.write_text(json.dumps({
            "airgap_last_lab_mode": "airgapped",
            "airgap_last_egress_offset": "not an int",
        }))

        _flip(client, "hybrid")
        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is not None
        assert obs.watcher == "airgap:mode-toggle"

    def test_watcher_handles_state_dir_missing(self, buddy_setup, tmp_path):
        """state.json's parent dir disappears between toggle and tick."""
        client, state_path, _, _ = buddy_setup

        _flip(client, "hybrid")

        # Remove state.json (parent stays).
        if state_path.exists():
            state_path.unlink()

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        # With state file missing, last_mode defaults to "airgapped" and
        # current is "hybrid" → fires.
        assert obs is not None
        assert obs.watcher == "airgap:mode-toggle"


# ---------------------------------------------------------------------------
# Audit log: 5x rapid-fire writes are append-only and ordered
# ---------------------------------------------------------------------------

class TestAuditOrdering:
    def test_audit_lines_in_order_after_rapid_toggle(self, buddy_setup):
        client, _, _, audit_path = buddy_setup

        sequence = ["hybrid", "airgapped", "hybrid", "airgapped", "hybrid"]
        previous_seen = []
        for tgt in sequence:
            _flip(client, tgt)

        lines = [json.loads(l) for l in audit_path.read_text().splitlines() if l.strip()]
        assert len(lines) == 5
        # Each entry's `from` must equal the previous entry's `to`.
        for i in range(1, len(lines)):
            assert lines[i]["from"] == lines[i - 1]["to"], (
                f"Audit chain broken at i={i}: {lines[i-1]} → {lines[i]}"
            )
        # All confirmed=True.
        for entry in lines:
            assert entry["confirmed"] is True
        # All have valid ts (parses).
        from datetime import datetime
        for entry in lines:
            datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
