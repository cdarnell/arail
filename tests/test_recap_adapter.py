"""Unit tests for arail.agents.recap.router_adapter.RouterAdapter."""

from __future__ import annotations

import pytest

from arail.agents.recap.router_adapter import RouterAdapter, flatten_messages
from arail.costs import current_recap_depth, cost_tracker
from tests._recap_scripted import ScriptedRouter


# ---------------------------------------------------------------------------
# flatten_messages
# ---------------------------------------------------------------------------

class TestFlattenMessages:
    def test_single_system(self):
        msgs = [{"role": "system", "content": "rules"}]
        out = flatten_messages(msgs)
        assert "<<SYSTEM>>" in out
        assert "rules" in out

    def test_role_order_preserved(self):
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "next"},
        ]
        out = flatten_messages(msgs)
        idx_sys = out.index("<<SYSTEM>>")
        idx_user = out.index("<<USER>>")
        idx_asst = out.index("<<ASSISTANT>>")
        assert idx_sys < idx_user < idx_asst

    def test_unknown_role_tagged(self):
        msgs = [{"role": "tool", "content": "data"}]
        out = flatten_messages(msgs)
        assert "<<TOOL>>" in out

    def test_empty_messages(self):
        assert flatten_messages([]) == ""

    def test_deterministic(self):
        msgs = [{"role": "user", "content": "test"}]
        assert flatten_messages(msgs) == flatten_messages(msgs)


# ---------------------------------------------------------------------------
# RouterAdapter.chat
# ---------------------------------------------------------------------------

VALID_RESPONSE = '```json\n{"think":"ok","subtasks":[]}\n```'


class TestRouterAdapter:
    def _make_adapter(self, responses=None, fallback=VALID_RESPONSE):
        router = ScriptedRouter(responses or {}, fallback=fallback)
        return RouterAdapter(router, max_tokens=64, temperature=0.0), router

    def test_basic_call_returns_text(self):
        adapter, _ = self._make_adapter()
        result = adapter.chat([{"role": "user", "content": "hello"}])
        assert result == VALID_RESPONSE

    def test_prompt_contains_message_content(self):
        adapter, router = self._make_adapter()
        adapter.chat([{"role": "user", "content": "unique-marker-xyz"}])
        assert any("unique-marker-xyz" in c for c in router.calls)

    def test_recap_depth_contextvar_set_during_call(self):
        """The contextvar must be set inside the router.complete() call."""
        depths_seen = []

        class DepthCapturingRouter:
            calls = []
            def complete(self, prompt, **kw):
                depths_seen.append(current_recap_depth())
                from tests._recap_scripted import _FakeResponse
                return _FakeResponse(text=VALID_RESPONSE)

        adapter = RouterAdapter(DepthCapturingRouter(), max_tokens=64)
        adapter.chat([{"role": "user", "content": "x"}], depth=5)
        assert depths_seen == [5]

    def test_recap_depth_reset_after_call(self):
        adapter, _ = self._make_adapter()
        adapter.chat([{"role": "user", "content": "x"}], depth=3)
        assert current_recap_depth() is None

    def test_prompt_budget_triggers_truncation(self):
        """When flat prompt > budget, truncation must fire."""
        # Create a history with many large entries
        big = "x" * 500
        msgs = [{"role": "system", "content": big}] + [
            {"role": "user", "content": big} for _ in range(20)
        ]
        adapter, router = self._make_adapter()
        adapter.prompt_token_budget = 100  # very small budget
        adapter.chat(msgs)
        # The prompt actually sent must be smaller than a naive flatten of all 21 msgs.
        # Naive flatten = 21 * ~500 = ~10500 chars. Truncation reduces this significantly.
        # Floor is pinned_entry + reminder (can't go lower), so we just check it
        # is substantially smaller than naive.
        sent_prompt = router.calls[-1]
        naive_size = sum(len(m["content"]) for m in msgs)
        assert len(sent_prompt) < naive_size

    def test_window_applied(self):
        """Sliding window K=64 limits history entries passed to router."""
        # Build 100-entry history
        history = [{"role": "system", "content": "pinned"}] + [
            {"role": "user", "content": f"msg-{i}"} for i in range(99)
        ]
        adapter, router = self._make_adapter()
        adapter.chat(history, depth=0)
        sent = router.calls[-1]
        # "pinned" must be present
        assert "pinned" in sent
        # "msg-0" through early messages should be absent (windowed out)
        assert "msg-0" not in sent
        # Most recent messages should be present
        assert "msg-98" in sent

    def test_max_tokens_override(self):
        """max_tokens kwarg overrides instance default."""
        class CapturingRouter:
            calls = []
            def complete(self, prompt, max_tokens=512, **kw):
                self.calls.append(max_tokens)
                from tests._recap_scripted import _FakeResponse
                return _FakeResponse(text=VALID_RESPONSE)

        r = CapturingRouter()
        adapter = RouterAdapter(r, max_tokens=64)
        adapter.chat([{"role": "user", "content": "x"}], max_tokens=256)
        assert r.calls[-1] == 256


# ---------------------------------------------------------------------------
# Cost tracker receives recap_depth
# ---------------------------------------------------------------------------

class TestCostTrackerIntegration:
    def test_recap_depth_recorded_in_history(self):
        """cost_tracker.track() stores recap_depth when called inside the context."""
        from arail.costs import CostTracker, recap_depth_context
        tracker = CostTracker()
        before = len(tracker._history)

        with recap_depth_context(7):
            tracker.track(
                "mlx", "test-model", 10, 5, 1.0, "test",
                recap_depth=7,
            )

        after = tracker._history[before:]
        assert len(after) >= 1
        assert after[-1]["recap_depth"] == 7

    def test_recap_depth_aggregated_in_calls_by_depth(self):
        """calls_by_recap_depth is incremented per depth."""
        from arail.costs import CostTracker
        tracker = CostTracker()
        before = tracker.calls_by_recap_depth.get(99, 0)
        tracker.track("mlx", "m", 1, 1, 1.0, "test", recap_depth=99)
        assert tracker.calls_by_recap_depth.get(99, 0) == before + 1

    def test_non_recap_call_has_none_depth(self):
        """Direct track() call without recap_depth kwarg stores None."""
        from arail.costs import CostTracker
        tracker = CostTracker()
        before = len(tracker._history)
        tracker.track("mlx", "test", 10, 5, 1.0, "test")
        assert tracker._history[before]["recap_depth"] is None

    def test_contextvar_set_during_adapter_chat(self):
        """recap_depth contextvar is set to the depth arg during router.complete()."""
        depths_seen = []

        class CapturingRouter:
            def complete(self, prompt, **kw):
                depths_seen.append(current_recap_depth())
                from tests._recap_scripted import _FakeResponse
                return _FakeResponse(text=VALID_RESPONSE)

        adapter = RouterAdapter(CapturingRouter())
        adapter.chat([{"role": "user", "content": "x"}], depth=4)
        assert depths_seen == [4]
        assert current_recap_depth() is None  # reset after call
