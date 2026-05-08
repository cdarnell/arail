"""End-to-end test: Buddy's _watch_airgap_events detects a runtime toggle.

ARCHITECTURE.md §9 test_buddy_watcher_after_runtime_toggle.py:
- Set LAB_MODE=airgapped; seed Buddy state.json with airgap_last_lab_mode: airgapped.
- Call the toggle endpoint to flip to hybrid.
- Manually invoke _watch_airgap_events().
- Assert returned Observation is the 'Door's open' mode-toggle one
  and state.json['airgap_last_lab_mode'] == 'hybrid'.

This test validates the wiring without touching _builtin_buddy.py —
the existing watcher already reads lab_mode() from os.environ, which
the toggle endpoint updates as its side-effect.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail.portal.app import app


@pytest.fixture()
def watcher_setup(tmp_path, monkeypatch):
    """Wire toggle endpoint + buddy state to tmp_path."""
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"LAB_MODE=airgapped\n")
    audit_path = tmp_path / "airgap_audit.jsonl"
    state_path = tmp_path / "state.json"

    import arail.portal.app as app_mod
    monkeypatch.setattr(app_mod, "_TOGGLE_ENV_PATH", env_path)
    monkeypatch.setattr(app_mod, "_TOGGLE_AUDIT_PATH", audit_path)
    monkeypatch.setenv("BIND_ADDR", "127.0.0.1")
    monkeypatch.setenv("LAB_MODE", "airgapped")

    # Seed Buddy state with airgap_last_lab_mode=airgapped.
    state_path.write_text(json.dumps({"airgap_last_lab_mode": "airgapped"}))

    import arail.agents._builtin_buddy as buddy_mod
    import arail.egress as egress_mod

    monkeypatch.setattr(buddy_mod, "_state_file", lambda: state_path)
    monkeypatch.setattr(egress_mod, "_lab_data", lambda: tmp_path)

    client = TestClient(app, raise_server_exceptions=False)
    return client, state_path, env_path


class TestBuddyWatcherAfterRuntimeToggle:
    def test_watcher_detects_toggle_to_hybrid(self, watcher_setup):
        """Toggle endpoint flips LAB_MODE; next watcher tick fires Observation."""
        client, state_path, env_path = watcher_setup

        # Step 1: issue token.
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid"},
            headers={"Origin": "http://testserver"},
        )
        assert r1.status_code == 409, f"Expected 409, got {r1.status_code}: {r1.text}"
        token = r1.json()["confirm_token"]

        # Step 2: confirm.
        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "hybrid", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 200, f"Expected 200, got {r2.status_code}: {r2.text}"

        # os.environ["LAB_MODE"] should now be "hybrid".
        import os
        assert os.getenv("LAB_MODE") == "hybrid"

        # Invoke the watcher — it reads lab_mode() from os.environ.
        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()

        assert obs is not None, "Watcher must return an Observation on mode toggle"
        assert obs.watcher == "airgap:mode-toggle"
        # The 'Door's open' fact from _builtin_buddy.py lines 524-525.
        assert "door" in obs.fact.lower() or "open" in obs.fact.lower(), (
            f"Unexpected fact: {obs.fact!r}"
        )

        # state.json must be updated.
        state = json.loads(state_path.read_text())
        assert state.get("airgap_last_lab_mode") == "hybrid", (
            f"state.json not updated: {state}"
        )

    def test_watcher_detects_toggle_back_to_airgapped(self, watcher_setup, monkeypatch):
        """After a hybrid->airgapped toggle, watcher fires 'sealed' Observation."""
        client, state_path, env_path = watcher_setup

        # Seed state with hybrid so a re-toggle to airgapped triggers.
        state_path.write_text(json.dumps({"airgap_last_lab_mode": "hybrid"}))
        monkeypatch.setenv("LAB_MODE", "hybrid")
        env_path.write_bytes(b"LAB_MODE=hybrid\n")

        # Toggle to airgapped.
        r1 = client.post(
            "/api/airgap/toggle",
            json={"target": "airgapped"},
            headers={"Origin": "http://testserver"},
        )
        assert r1.status_code == 409
        token = r1.json()["confirm_token"]

        r2 = client.post(
            "/api/airgap/toggle",
            json={"target": "airgapped", "confirm_token": token},
            headers={"Origin": "http://testserver"},
        )
        assert r2.status_code == 200

        import os
        assert os.getenv("LAB_MODE") == "airgapped"

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()

        assert obs is not None
        assert obs.watcher == "airgap:mode-toggle"
        # The 'Sealed back up' fact from _builtin_buddy.py line 527.
        assert (
            "sealed" in obs.fact.lower()
            or "airgapped" in obs.fact.lower()
            or "public" in obs.fact.lower()
        ), f"Unexpected fact: {obs.fact!r}"

        state = json.loads(state_path.read_text())
        assert state.get("airgap_last_lab_mode") == "airgapped"
