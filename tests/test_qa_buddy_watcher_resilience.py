"""QA — Buddy airgap watcher resilience under restart + edge inputs.

Under the 30% Buddy bucket. The Loopback 1 fix made ``_save_state``
read-merge-write so the watcher's keys survive across emits. These
tests exercise additional edge cases the existing suite doesn't cover:

  - Multiple BuddyAgent.save_state cycles in a row preserve the keys
    (not just one round-trip).
  - Watcher handles malformed state.json gracefully.
  - Watcher handles malformed lines in egress.jsonl gracefully (one
    bad line shouldn't poison the whole tail).
  - Watcher handles an empty egress.jsonl.
  - Cooldown_sec on the airgap-event Observation matches the
    architecture's stated 5-min value.
  - Watcher offset advancement is monotonic (advances after each tick).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


def _make_block(url_host: str, ts: str | None = None) -> dict:
    return {
        "ts": ts or "2026-05-05T12:00:00Z",
        "url_host": url_host,
        "caller": "test.caller",
        "reason": "airgapped",
        "lab_mode": "airgapped",
    }


def _patch_buddy(monkeypatch, tmp_path: Path):
    import arail.agents._builtin_buddy as buddy_mod
    state_path = tmp_path / "state.json"
    monkeypatch.setattr(buddy_mod, "_state_file", lambda: state_path)
    import arail.egress as egress_mod
    monkeypatch.setattr(egress_mod, "_lab_data", lambda: tmp_path)


# ──────────────────────────────────────────────────────────────────────
# Multiple save cycles preserve airgap keys
# ──────────────────────────────────────────────────────────────────────

class TestRepeatedSaveStateCycles:
    """The original BLOCK fix's regression test runs ONE watcher cycle
    + ONE _save_state call. These tests exercise multiple cycles to
    catch regressions where merge logic only works once."""

    def test_three_save_cycles_preserve_airgap_keys(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        egress_path = tmp_path / "egress.jsonl"

        # Seed an initial block so watcher has something to consume.
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        egress_path.write_text(json.dumps(_make_block("h1.com")) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events, BuddyAgent

        # Cycle 1: watcher writes airgap_last_egress_offset.
        _watch_airgap_events()

        # Manually seed lab_mode key (only written on toggle).
        cur = json.loads(state_path.read_text())
        cur["airgap_last_lab_mode"] = "airgapped"
        state_path.write_text(json.dumps(cur, indent=2))

        agent = BuddyAgent()

        # Three save cycles in a row — keys must survive ALL.
        for i in range(3):
            agent._save_state()
            data = json.loads(state_path.read_text())
            assert "airgap_last_egress_offset" in data, (
                f"Cycle {i+1}: airgap_last_egress_offset clobbered"
            )
            assert "airgap_last_lab_mode" in data, (
                f"Cycle {i+1}: airgap_last_lab_mode clobbered"
            )

    def test_save_state_then_watcher_then_save_state(self, monkeypatch, tmp_path):
        """Reverse order: BuddyAgent saves first, then watcher runs,
        then BuddyAgent saves again. Watcher's writes must not stomp
        BuddyAgent's writes either."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        egress_path = tmp_path / "egress.jsonl"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        egress_path.write_text(json.dumps(_make_block("h2.com")) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events, BuddyAgent

        agent = BuddyAgent()
        agent._utterances = 7  # marker
        agent._save_state()

        _watch_airgap_events()

        agent._save_state()  # second save — should not lose watcher's keys

        data = json.loads(state_path.read_text())
        assert data.get("utterances") == 7
        assert "airgap_last_egress_offset" in data


# ──────────────────────────────────────────────────────────────────────
# Watcher tolerates malformed state.json
# ──────────────────────────────────────────────────────────────────────

class TestMalformedStateJson:
    def test_corrupt_state_json_does_not_crash_watcher(
        self, monkeypatch, tmp_path
    ):
        """A corrupt state.json must not crash the watcher."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        state_path.write_text("{not valid json at all")

        # Watcher should treat this as empty state and not raise.
        from arail.agents._builtin_buddy import _watch_airgap_events
        # If this raises, the test fails outright.
        result = _watch_airgap_events()
        # Result may be None (no egress file) — but no crash.
        assert result is None or result is not None

    def test_state_json_with_wrong_types_for_keys(self, monkeypatch, tmp_path):
        """state.json has airgap_last_egress_offset = 'not a number'.
        Watcher should fall back to 0 / 'airgapped'.

        BUG FOUND (low severity): _watch_airgap_events does
        ``int(state_data.get('airgap_last_egress_offset', 0))`` without
        a try/except. If the on-disk value is non-coercible (e.g.
        someone hand-edited state.json or a buggy other writer wrote
        garbage), the watcher raises ValueError and the entire tick
        crashes. This is fail-loud rather than fail-closed — the
        watcher just stops watching.

        Severity: low — requires a corrupted state.json (which itself
        is a degraded-state scenario). But under arail's CLAUDE.md
        product gating, "Buddy quality" is 30% of QA, and a watcher
        that crashes on degraded inputs is a Buddy-quality issue.

        Reproducer: tests/test_qa_buddy_watcher_resilience.py
        ::TestMalformedStateJson::test_state_json_with_wrong_types_for_keys
        """
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({
            "airgap_last_egress_offset": "garbage",
            "airgap_last_lab_mode": ["weird", "list"],
        }))

        # Watcher's int(...) coerce should fail safely.
        from arail.agents._builtin_buddy import _watch_airgap_events
        try:
            _watch_airgap_events()
        except ValueError as e:  # noqa: BLE001
            pytest.fail(
                f"BUG: Watcher must coerce malformed offset gracefully; "
                f"raised {e}. Suggested fix in _builtin_buddy.py around "
                f"line 513: wrap ``int(state_data.get(...))`` with "
                f"try/except ValueError, default to 0."
            )


# ──────────────────────────────────────────────────────────────────────
# Watcher tolerates malformed egress.jsonl lines
# ──────────────────────────────────────────────────────────────────────

class TestMalformedEgressJsonl:
    def test_one_bad_line_does_not_break_tail(self, monkeypatch, tmp_path):
        """A garbage line in the middle of egress.jsonl must NOT prevent
        the watcher from finding the most-recent good block."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        with egress_path.open("w") as f:
            f.write(json.dumps(_make_block("good1.com")) + "\n")
            f.write("not valid json\n")
            f.write(json.dumps(_make_block("good2.com")) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        # Should pick good2.com (most recent valid block).
        assert obs is not None
        assert "good2.com" in obs.fact, (
            f"Watcher should skip bad lines and pick last good; got: {obs.fact}"
        )

    def test_empty_egress_jsonl_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        # Empty file (zero bytes).
        egress_path = tmp_path / "egress.jsonl"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        egress_path.touch()

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is None, "Empty egress.jsonl must yield no Observation"

    def test_only_non_block_entries_returns_none(self, monkeypatch, tmp_path):
        """egress.jsonl with only ``allow:*`` and ``probe`` entries — no
        blocks — must NOT trigger an Observation."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        with egress_path.open("w") as f:
            f.write(json.dumps({
                "ts": "2026-05-05T12:00:00Z", "url_host": "x.com",
                "caller": "t", "reason": "allow:test", "lab_mode": "hybrid",
            }) + "\n")
            f.write(json.dumps({
                "ts": "2026-05-05T12:00:01Z", "url_host": "1.1.1.1:443",
                "caller": "probe", "reason": "probe", "lab_mode": "airgapped",
            }) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is None, (
            f"Non-block entries must not trigger Observation; got: {obs}"
        )


# ──────────────────────────────────────────────────────────────────────
# Watcher offset is monotonic
# ──────────────────────────────────────────────────────────────────────

class TestOffsetMonotonic:
    def test_offset_advances_after_each_tick(self, monkeypatch, tmp_path):
        """Each watcher tick must advance offset to file_size — never
        regress (except after rotation, which is tested separately)."""
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        state_path = tmp_path / "state.json"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        egress_path.write_text(json.dumps(_make_block("a.com")) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events
        _watch_airgap_events()
        offset_1 = json.loads(state_path.read_text()).get(
            "airgap_last_egress_offset", 0
        )
        size_1 = egress_path.stat().st_size
        assert offset_1 == size_1, (
            f"Offset must advance to file_size after first tick; "
            f"got offset={offset_1}, size={size_1}"
        )

        # Append more.
        with egress_path.open("a") as f:
            f.write(json.dumps(_make_block("b.com")) + "\n")
            f.write(json.dumps(_make_block("c.com")) + "\n")

        _watch_airgap_events()
        offset_2 = json.loads(state_path.read_text())["airgap_last_egress_offset"]
        size_2 = egress_path.stat().st_size
        assert offset_2 >= offset_1, "Offset must be monotonic"
        assert offset_2 == size_2


# ──────────────────────────────────────────────────────────────────────
# Cooldown values match architecture spec
# ──────────────────────────────────────────────────────────────────────

class TestCooldownValuesPin:
    """Pin the architectural promise: airgap-watcher Observations have
    a 5-min cooldown so a polling agent's blocks-per-30s collapses to
    one Observation per 5 min."""

    def test_block_observation_cooldown_is_5_minutes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        egress_path.write_text(json.dumps(_make_block("h.com")) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is not None
        assert obs.cooldown_sec == 5 * 60, (
            f"Architecture promised 5-min cooldown; got {obs.cooldown_sec}s"
        )

    def test_mode_toggle_observation_cooldown_is_5_minutes(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        state_path = tmp_path / "state.json"
        state_path.write_text(json.dumps({"airgap_last_lab_mode": "airgapped"}))

        monkeypatch.setenv("LAB_MODE", "hybrid")
        from arail.agents._builtin_buddy import _watch_airgap_events
        obs = _watch_airgap_events()
        assert obs is not None
        assert obs.cooldown_sec == 5 * 60


# ──────────────────────────────────────────────────────────────────────
# Watcher's persisted-offset survives a simulated restart
# ──────────────────────────────────────────────────────────────────────

class TestRestartSurvives:
    """Simulate: tick 1 → save → "restart" (re-import / new watcher
    invocation) → tick 2 should not re-emit the same block."""

    def test_offset_survives_simulated_restart(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LAB_MODE", "airgapped")
        _patch_buddy(monkeypatch, tmp_path)

        egress_path = tmp_path / "egress.jsonl"
        egress_path.parent.mkdir(parents=True, exist_ok=True)
        egress_path.write_text(json.dumps(_make_block("once.com")) + "\n")

        from arail.agents._builtin_buddy import _watch_airgap_events
        obs1 = _watch_airgap_events()
        assert obs1 is not None
        # Now state.json has the offset. "Restart" — simply call again.
        obs2 = _watch_airgap_events()
        assert obs2 is None, (
            "After restart, no new blocks should mean no Observation. "
            "If we emit twice, the offset wasn't persisted across the "
            "simulated restart."
        )
