"""Tests for Buddy's _watch_airgap_events watcher.

Per ARCHITECTURE.md §10:
- Fixture writes a fake egress.jsonl with 3 blocks.
- Mock buddy host returning that path.
- Call _watch_airgap_events() once → returns Observation whose fact
  mentions the most recent block's host.
- Advance state.airgap_last_egress_offset; call again → returns None.
- Append a new block; call again → returns Observation for new block.
- Toggle env from airgapped to hybrid; call → returns toggle Observation;
  state.airgap_last_lab_mode updated.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest


# ── Helpers ───────────────────────────────────────────────────────────

def _make_block(url_host: str, ts: str | None = None) -> dict:
    return {
        "ts": ts or "2026-05-05T12:00:00Z",
        "url_host": url_host,
        "caller": "test.caller",
        "reason": "airgapped",
        "lab_mode": "airgapped",
    }


def _write_blocks(path: Path, blocks: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        for b in blocks:
            f.write(json.dumps(b) + "\n")


def _patch_buddy(monkeypatch, tmp_path: Path):
    """Patch _host + _state_file so the watcher uses tmp_path."""
    import arail.agents._builtin_buddy as buddy_mod

    # Patch _state_file to return a tmp state file.
    state_path = tmp_path / "state.json"

    monkeypatch.setattr(buddy_mod, "_state_file", lambda: state_path)

    # Patch _lab_data to return tmp_path so egress.jsonl is there.
    import arail.egress as egress_mod
    monkeypatch.setattr(egress_mod, "_lab_data", lambda: tmp_path)


# ── Tests ─────────────────────────────────────────────────────────────

class TestWatchAirgapEvents:
    def test_returns_observation_for_most_recent_block(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        blocks = [
            _make_block("host1.com", "2026-05-05T10:00:00Z"),
            _make_block("host2.com", "2026-05-05T11:00:00Z"),
            _make_block("most-recent.com", "2026-05-05T12:00:00Z"),
        ]
        _write_blocks(egress_path, blocks)

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()

        assert obs is not None, "Expected an Observation for new blocks"
        assert "most-recent.com" in obs.fact, (
            f"Observation fact must mention most recent host; got: {obs.fact!r}"
        )
        assert obs.watcher == "airgap:block"

    def test_returns_none_when_no_new_blocks(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        blocks = [_make_block("already-seen.com")]
        _write_blocks(egress_path, blocks)

        from arail.agents._builtin_buddy import _watch_airgap_events

        # First call — advances offset to end of file.
        _watch_airgap_events()

        # Second call — no new blocks.
        obs = _watch_airgap_events()
        # No mode toggle, no new blocks → None.
        assert obs is None, "Expected None when no new blocks or mode change"

    def test_returns_observation_for_new_block_after_advance(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        blocks = [_make_block("initial.com")]
        _write_blocks(egress_path, blocks)

        from arail.agents._builtin_buddy import _watch_airgap_events

        # First call — reads initial block.
        _watch_airgap_events()

        # Append a new block.
        with egress_path.open("a") as f:
            f.write(json.dumps(_make_block("new-block.com", "2026-05-05T13:00:00Z")) + "\n")

        obs = _watch_airgap_events()
        assert obs is not None, "Expected Observation for newly appended block"
        assert "new-block.com" in obs.fact

    def test_mode_toggle_airgapped_to_hybrid_fires_observation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        # Seed state with last_lab_mode=airgapped.
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"airgap_last_lab_mode": "airgapped"}))

        from arail.agents._builtin_buddy import _watch_airgap_events

        # Toggle to hybrid.
        monkeypatch.setenv("LAB_MODE", "hybrid")
        obs = _watch_airgap_events()
        assert obs is not None, "Expected Observation on mode toggle"
        assert obs.watcher == "airgap:mode-toggle"
        assert "open" in obs.fact.lower() or "door" in obs.fact.lower()

        # State should be updated.
        saved = json.loads(state_path.read_text())
        assert saved.get("airgap_last_lab_mode") == "hybrid"

    def test_mode_toggle_hybrid_to_airgapped_fires_observation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "hybrid")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"airgap_last_lab_mode": "hybrid"}))

        from arail.agents._builtin_buddy import _watch_airgap_events

        monkeypatch.setenv("LAB_MODE", "airgapped")
        obs = _watch_airgap_events()
        assert obs is not None
        assert obs.watcher == "airgap:mode-toggle"
        assert "sealed" in obs.fact.lower() or "airgapped" in obs.fact.lower() or "public" in obs.fact.lower()

    def test_offset_reset_on_rotation(self, monkeypatch, tmp_path):
        """If last_egress_offset > current file size (rotation happened),
        the watcher must reset the offset to 0 and read from the start."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"

        # Seed state with a large offset that exceeds any file we'll write.
        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"airgap_last_egress_offset": 999999}))

        # Write a fresh (post-rotation) file.
        _write_blocks(egress_path, [_make_block("post-rotation.com")])

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is not None, "Watcher must read from start when offset > file size"
        assert "post-rotation.com" in obs.fact


class TestSaveStatePreservesAirgapKeys:
    """Regression guard for the BLOCK fix: BuddyAgent._save_state must
    use read-merge-write semantics so the airgap watcher's keys survive
    a subsequent _save_state call.

    Sequence under test:
      1. Watcher writes airgap_last_egress_offset + airgap_last_lab_mode.
      2. BuddyAgent._save_state() writes its five keys.
      3. state.json must contain ALL seven keys.
    """

    def test_save_state_after_watcher_preserves_airgap_keys(
        self, monkeypatch, tmp_path
    ):
        """Critical: BuddyAgent._save_state must NOT clobber the airgap
        keys the watcher just persisted.

        Sequence:
          1. Seed state.json with both airgap watcher keys (simulating a
             prior watcher cycle that wrote an offset + mode).
          2. Run the watcher again with a new block (advances offset).
          3. Call BuddyAgent._save_state().
          4. Assert ALL seven keys survive: 5 Buddy keys + 2 airgap keys.
        """
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        egress_path = tmp_path / "egress.jsonl"

        # Seed an initial block so the watcher has something to consume.
        _write_blocks(egress_path, [_make_block("first-host.com")])

        # Step 1: first watcher run — writes airgap_last_egress_offset.
        # We also manually seed airgap_last_lab_mode to simulate a prior
        # mode-toggle write (the watcher only writes that key on toggle).
        from arail.agents._builtin_buddy import _watch_airgap_events
        _watch_airgap_events()
        after_first = json.loads(state_path.read_text())
        # Inject the mode key (written by watcher on mode-toggle events).
        after_first["airgap_last_lab_mode"] = "airgapped"
        state_path.write_text(json.dumps(after_first, indent=2))

        assert "airgap_last_egress_offset" in after_first, (
            "Watcher must persist airgap_last_egress_offset before the test is meaningful"
        )

        # Step 2: construct a BuddyAgent and call _save_state().
        # We do NOT pass a stub host — that would mutate the module-level
        # _host and break other tests.  _save_state only touches the file;
        # it never calls _host, so the existing default host is fine here.
        import arail.agents._builtin_buddy as buddy_mod

        agent = buddy_mod.BuddyAgent()
        agent._save_state()

        # Step 3: both key families must survive on disk.
        final = json.loads(state_path.read_text())

        # BuddyAgent's own keys.
        for key in ("last_said", "last_global", "last_suggest_check",
                    "utterances", "suggestions"):
            assert key in final, f"BuddyAgent key '{key}' missing after _save_state"

        # Watcher's keys must NOT have been clobbered.
        assert "airgap_last_egress_offset" in final, (
            "airgap_last_egress_offset was clobbered by _save_state — "
            "read-merge-write fix required"
        )
        assert "airgap_last_lab_mode" in final, (
            "airgap_last_lab_mode was clobbered by _save_state — "
            "read-merge-write fix required"
        )
