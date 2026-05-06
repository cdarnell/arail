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
