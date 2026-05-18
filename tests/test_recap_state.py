"""Unit tests for arail.agents.recap.state.

Covers:
  - window(): pinning of entry 0; K=1..64 size honored; idempotence.
  - truncate_for_context(): §A policy (drop 2-3, keep 0, reminder re-emitted).
  - ContextNode / ContextTree: parent links, depth math, serialisation round-trip.
"""

from __future__ import annotations

import json

import pytest

from arail.agents.recap.state import (
    WINDOW_K,
    ContextNode,
    ContextTree,
    truncate_for_context,
    window,
)
from arail.agents.recap.prompts import PERIODIC_RULE_REMINDER


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history(n: int) -> list:
    """Return a history list of n dicts; index 0 is the pinned system message."""
    return [{"role": "system" if i == 0 else "user", "content": f"msg-{i}"}
            for i in range(n)]


# ---------------------------------------------------------------------------
# window()
# ---------------------------------------------------------------------------

class TestWindow:
    def test_empty_history(self):
        assert window([]) == []

    def test_pinned_entry_always_present(self):
        history = _make_history(10)
        result = window(history, k=3)
        assert result[0] is history[0]

    def test_size_smaller_than_k(self):
        history = _make_history(5)
        result = window(history, k=WINDOW_K)
        assert result == history

    def test_size_exactly_k(self):
        history = _make_history(WINDOW_K)
        result = window(history, k=WINDOW_K)
        assert result == history

    def test_size_larger_than_k(self):
        history = _make_history(100)
        result = window(history, k=64)
        assert len(result) == 64
        assert result[0] is history[0]
        # Last entry must be the most recent
        assert result[-1] is history[-1]

    @pytest.mark.parametrize("k", range(1, 65))
    def test_k_range_size_honored(self, k):
        history = _make_history(80)
        result = window(history, k=k)
        assert len(result) == k
        assert result[0] is history[0]

    def test_idempotent_when_no_overflow(self):
        history = _make_history(10)
        r1 = window(history, k=20)
        r2 = window(r1, k=20)
        assert r1 == r2

    def test_k_zero_treated_as_k1(self):
        history = _make_history(10)
        result = window(history, k=0)
        assert len(result) == 1
        assert result[0] is history[0]

    def test_single_entry_history(self):
        history = _make_history(1)
        result = window(history, k=64)
        assert result == history

    def test_k1_returns_only_pinned(self):
        history = _make_history(20)
        result = window(history, k=1)
        assert len(result) == 1
        assert result[0] is history[0]


# ---------------------------------------------------------------------------
# truncate_for_context()
# ---------------------------------------------------------------------------

class TestTruncateForContext:
    def _make_big_history(self, n: int, msg_size: int = 100) -> list:
        return [
            {"role": "system" if i == 0 else "user",
             "content": "x" * msg_size}
            for i in range(n)
        ]

    def test_no_truncation_needed(self):
        history = self._make_big_history(3, 10)
        result = truncate_for_context(history, max_chars=10000)
        assert result == history

    def test_drops_indices_2_and_3(self):
        history = _make_history(6)  # indices 0,1,2,3,4,5
        idx2_content = history[2]["content"]
        idx3_content = history[3]["content"]
        # Force truncation by setting a tiny budget
        result = truncate_for_context(history, max_chars=0)
        contents = [m["content"] for m in result]
        assert idx2_content not in contents
        assert idx3_content not in contents

    def test_entry_0_always_kept(self):
        history = self._make_big_history(10, 50)
        result = truncate_for_context(history, max_chars=0)
        assert result[0]["content"] == history[0]["content"]

    def test_periodic_reminder_re_emitted(self):
        history = self._make_big_history(6, 20)
        # Make budget tight enough to force truncation
        result = truncate_for_context(history, max_chars=0)
        contents = [m["content"] for m in result]
        assert PERIODIC_RULE_REMINDER in contents

    def test_further_drops_oldest_if_still_over(self):
        # 10 entries, each 200 chars; budget 400 => only ~2 can fit
        history = self._make_big_history(10, 200)
        result = truncate_for_context(history, max_chars=400)
        total_chars = sum(len(m["content"]) for m in result)
        assert total_chars <= 400 or len(result) == 1  # may bottom out at 1


# ---------------------------------------------------------------------------
# ContextNode / ContextTree
# ---------------------------------------------------------------------------

class TestContextNode:
    def test_default_fields(self):
        node = ContextNode(T="test task")
        assert node.T == "test task"
        assert node.S == []
        assert node.parent is None
        assert node.depth == 0
        assert node.retries == 0
        assert node.plan is None

    def test_add_child_sets_parent_and_depth(self):
        root = ContextNode(T="root", depth=0)
        child = ContextNode(T="child", depth=1)
        root.add_child(child)
        assert child.parent is root
        assert child in root.children

    def test_depth_chain(self):
        nodes = []
        prev = None
        for i in range(5):
            n = ContextNode(T=f"level {i}", depth=i)
            if prev:
                prev.add_child(n)
            nodes.append(n)
            prev = n
        assert nodes[4].depth == 4
        # Walk up the chain
        cur = nodes[4]
        depth_check = 4
        while cur.parent:
            cur = cur.parent
            depth_check -= 1
        assert depth_check == 0

    def test_serialize_round_trip(self):
        root = ContextNode(T="root", depth=0)
        child = ContextNode(T="child", depth=1)
        root.add_child(child)
        data = root.serialize()
        # Must be JSON-serialisable
        serialized = json.dumps(data)
        parsed = json.loads(serialized)
        assert parsed["T"] == "root"
        assert len(parsed["children"]) == 1
        assert parsed["children"][0]["T"] == "child"


class TestContextTree:
    def test_basic_add_and_iteration(self):
        root = ContextNode(T="root")
        tree = ContextTree(root)
        child = ContextNode(T="child", depth=1)
        tree.add(child)
        nodes = list(tree)
        assert len(nodes) == 2
        assert nodes[0] is root

    def test_len(self):
        root = ContextNode(T="root")
        tree = ContextTree(root)
        assert len(tree) == 1
        tree.add(ContextNode(T="c1", depth=1))
        tree.add(ContextNode(T="c2", depth=1))
        assert len(tree) == 3

    def test_serialize_for_debug_is_valid_json(self):
        root = ContextNode(T="root")
        tree = ContextTree(root)
        s = tree.serialize_for_debug()
        parsed = json.loads(s)
        assert "tree" in parsed
        assert parsed["node_count"] == 1
