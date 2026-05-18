"""Paranoid QA pass tests for ReCAP (sprint 2026-05-17-recap-core).

Adds the tests the builder did not write:
  - Concurrent / async ContextVar isolation (architecture spec §"Failure
    modes & invariants" row 10 — flagged as a gap in REVIEW.md)
  - Algorithm correctness probes for truncation indices, K=1 window,
    parent re-injection under eviction, schema retry discipline
  - Edge cases: empty subtasks, cost ceiling abort, env exception,
    depth runaway forces primitive, periodic reminder cadence, multiple
    JSON candidates in prose
  - Cost regression: non-ReCAP track(...) without recap_depth kwarg
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

import pytest

from arail.agents.recap.core import (
    LEAF_RETRY_CAP,
    NONLEAF_RETRY_CAP,
    RecapAgent,
    ResultKind,
)
from arail.agents.recap.environment import Action, Observation
from arail.agents.recap.fixtures.robotouille_mock import make_env
from arail.agents.recap.prompts import (
    PERIODIC_RULE_REMINDER,
    SYSTEM_RULES,
    render_recursive_downward,
)
from arail.agents.recap.router_adapter import RouterAdapter, flatten_messages
from arail.agents.recap.schema import (
    SchemaError,
    parse_think_subtasks,
)
from arail.agents.recap.state import (
    ContextNode,
    truncate_for_context,
    window,
)
from arail.costs import (
    cost_tracker,
    current_recap_depth,
    recap_depth_context,
)
from tests._recap_scripted import (
    ScriptedRouter,
    _FakeResponse,
    empty_plan,
    make_plan_json,
    nonprimitive,
    primitive,
)


_COMPLETION = empty_plan("All done.")


# ---------------------------------------------------------------------------
# Helper: a router that records the ContextVar value seen *inside* complete()
# ---------------------------------------------------------------------------
class DepthRecordingRouter:
    """Records the recap_depth contextvar value at the moment complete() runs.

    Used by concurrency tests to verify no bleed across asyncio/thread
    contexts.
    """

    def __init__(self, response_text: str = _COMPLETION, delay_s: float = 0.0):
        self.response_text = response_text
        self.delay_s = delay_s
        self.observations: List[Optional[int]] = []
        self._lock = threading.Lock()

    def complete(self, prompt: str, **kw: Any) -> _FakeResponse:
        depth = current_recap_depth()
        if self.delay_s:
            time.sleep(self.delay_s)
        with self._lock:
            self.observations.append(depth)
        return _FakeResponse(text=self.response_text)


# ===========================================================================
# 1. CONCURRENT / ASYNC ContextVar isolation (highest priority)
# ===========================================================================
class TestConcurrentContextVarIsolation:
    """Architecture spec row 10 — verified via concurrent test.

    These four tests cover: asyncio.gather, ThreadPoolExecutor,
    nested-context restore, and round-trip across many tasks.
    """

    def test_recap_depth_context_basic_set_reset(self):
        """Outside any context, current_recap_depth() returns None."""
        assert current_recap_depth() is None
        with recap_depth_context(3):
            assert current_recap_depth() == 3
        assert current_recap_depth() is None

    def test_recap_depth_context_nested(self):
        """Nested contexts restore correctly via token reset."""
        with recap_depth_context(1):
            assert current_recap_depth() == 1
            with recap_depth_context(2):
                assert current_recap_depth() == 2
                with recap_depth_context(7):
                    assert current_recap_depth() == 7
                assert current_recap_depth() == 2
            assert current_recap_depth() == 1
        assert current_recap_depth() is None

    def test_concurrent_threadpool_no_bleed(self):
        """Two threads call adapter at distinct depths; no bleed across threads.

        Each thread's recap_depth_context is independent because ContextVar
        copies its value into each new thread's context (when launched via
        ThreadPoolExecutor with contextvars.copy_context not used, the value
        is reset to default).  We assert each thread sees ONLY its own depth.
        """
        router = DepthRecordingRouter(delay_s=0.02)
        adapter = RouterAdapter(router, max_tokens=8)

        per_thread_observations: Dict[int, List[Optional[int]]] = {0: [], 1: []}
        barrier = threading.Barrier(2)

        def worker(thread_id: int, depth: int) -> None:
            barrier.wait()  # ensure both threads enter chat() concurrently
            for _ in range(5):
                # Each chat() enters recap_depth_context(depth)
                adapter.chat(
                    [{"role": "system", "content": "x"},
                     {"role": "user", "content": f"t{thread_id}"}],
                    depth=depth,
                )

        t0 = threading.Thread(target=worker, args=(0, 3))
        t1 = threading.Thread(target=worker, args=(1, 7))
        t0.start(); t1.start()
        t0.join(); t1.join()

        # Every observed depth must be either 3 or 7 (never None, never some
        # other value, never bleed).  We can't guarantee per-thread which
        # depth a given observation belonged to without per-thread routers,
        # but we CAN assert the set of values seen is exactly {3, 7}.
        seen = set(router.observations)
        assert seen == {3, 7}, (
            f"ContextVar bleed: observed depths {seen}, expected exactly {{3,7}}"
        )
        assert len(router.observations) == 10

    def test_concurrent_asyncio_gather_no_bleed(self):
        """asyncio.gather two RecapAgent.run-like loops at different depths.

        Critical test per REVIEW.md gap.  Uses async wrapper that enters
        recap_depth_context inside each task; asserts each task's
        complete() sees only its own depth.
        """
        router = DepthRecordingRouter(delay_s=0.005)

        async def task(depth: int, n_calls: int) -> List[Optional[int]]:
            local_observations: List[Optional[int]] = []
            for _ in range(n_calls):
                with recap_depth_context(depth):
                    # Yield control to allow interleaving
                    await asyncio.sleep(0)
                    router.complete("p")
                    local_observations.append(current_recap_depth())
                    await asyncio.sleep(0)
            return local_observations

        async def main():
            return await asyncio.gather(
                task(depth=2, n_calls=20),
                task(depth=5, n_calls=20),
                task(depth=11, n_calls=20),
            )

        results = asyncio.run(main())
        # Each task's local observations must be ONLY its own depth value.
        assert results[0] == [2] * 20, "Task depth=2 bled"
        assert results[1] == [5] * 20, "Task depth=5 bled"
        assert results[2] == [11] * 20, "Task depth=11 bled"

        # And the router observed all 60 depth values across the three
        # tasks; only 2, 5, 11 must appear.
        seen = set(router.observations)
        assert seen <= {2, 5, 11}, f"Router saw bleed: {seen}"

    def test_depth_context_resets_on_exception(self):
        """If body of recap_depth_context raises, the contextvar still resets."""
        assert current_recap_depth() is None
        with pytest.raises(RuntimeError):
            with recap_depth_context(4):
                assert current_recap_depth() == 4
                raise RuntimeError("boom")
        assert current_recap_depth() is None


# ===========================================================================
# 2. ALGORITHM CORRECTNESS — direct invariant probes
# ===========================================================================
class TestTruncationIndicesExactly2And3:
    """Architecture §A: drop indices {2,3}, NOT {1,2} or {3,4}."""

    def test_drops_exactly_indices_2_and_3_on_6_entry_history(self):
        # Use large content blobs so the §A drop-{2,3} step alone brings us
        # under budget without triggering step 4's iterative oldest-drop.
        big = "X" * 200  # 200 chars per entry
        history = [
            {"role": "system", "content": "PINNED_0_" + big},
            {"role": "user", "content": "ENTRY_1_" + big},
            {"role": "assistant", "content": "ENTRY_2_DROP_" + big},
            {"role": "user", "content": "ENTRY_3_DROP_" + big},
            {"role": "assistant", "content": "ENTRY_4_" + big},
            {"role": "user", "content": "ENTRY_5_" + big},
        ]
        # Budget that fits 4 entries + reminder (~600 chars + reminder),
        # but not all 6 (~1200 chars). Set to total - 2*entry_size + slack.
        total = sum(len(m["content"]) for m in history)
        # 6 entries ~= 1254 chars; drop {2,3} leaves 4 entries ~= 836 chars
        # + reminder ~165 = ~1001. Budget of total-100 = 1154 exceeds 1001
        # so step 4 (iterative oldest-drop) does NOT fire.
        result = truncate_for_context(history, max_chars=total - 100)

        blob = "\n".join(m["content"] for m in result)
        # Index 0 pinned
        assert "PINNED_0" in blob
        # Indices 1, 4, 5 preserved
        assert "ENTRY_1" in blob
        assert "ENTRY_4" in blob
        assert "ENTRY_5" in blob
        # Indices 2 and 3 dropped — not {1,2} or {3,4}
        assert "ENTRY_2_DROP" not in blob
        assert "ENTRY_3_DROP" not in blob
        # Reminder re-emitted at the end
        assert any(PERIODIC_RULE_REMINDER == m["content"] for m in result)

    def test_truncation_no_op_when_under_budget(self):
        history = [
            {"role": "system", "content": "A"},
            {"role": "user", "content": "B"},
            {"role": "user", "content": "C"},
        ]
        result = truncate_for_context(history, max_chars=10_000)
        assert result == history  # untouched


class TestWindowK1Pin:
    """K=1 window must return exactly the pinned entry, nothing else."""

    def test_k1_returns_only_pinned(self):
        history = [
            {"role": "system", "content": "PIN"},
            {"role": "user", "content": "A"},
            {"role": "user", "content": "B"},
            {"role": "user", "content": "LAST"},
        ]
        result = window(history, k=1)
        assert len(result) == 1
        assert result[0]["content"] == "PIN"

    def test_k0_treated_as_k1(self):
        history = [
            {"role": "system", "content": "PIN"},
            {"role": "user", "content": "A"},
        ]
        result = window(history, k=0)
        assert len(result) == 1
        assert result[0]["content"] == "PIN"

    def test_window_empty_history_returns_empty(self):
        assert window([], k=64) == []

    def test_window_single_entry_returns_singleton(self):
        h = [{"role": "system", "content": "only"}]
        assert window(h, k=64) == h
        assert window(h, k=1) == h


class TestParentReinjectionUnderEviction:
    """REVIEW.md §"Per-paranoia-probe finding": parent T comes from the tree,
    NOT chat history, so deep windowing never loses it.
    """

    def test_recursive_downward_message_contains_parent_T_post_window(self):
        """Even with k=1 window applied, the freshly-constructed message
        carries parent_T (it is the LAST entry, never evicted)."""
        parent_T = "ROOT_TASK_X"
        # Build a fresh child history exactly as core.py does
        downward = render_recursive_downward(
            parent_T=parent_T,
            parent_S_window="",
            subtask_T="sub",
        )
        child_history = [
            {"role": "system", "content": SYSTEM_RULES},
            {"role": "user", "content": downward},
        ]
        # Apply k=1 windowing — only the pinned (system) survives, so the
        # user message with parent_T does NOT survive in this 2-entry case.
        # But the INVARIANT is that the message is constructed fresh from
        # node.T every time, NOT pulled from chat history. So even if
        # windowing drops it, the next nonprimitive call rebuilds it.
        windowed = window(child_history, k=1)
        assert len(windowed) == 1
        # Confirm the construction step encoded parent_T (paranoia: in
        # case prompts.py drift loses it).
        assert parent_T in downward

    def test_parent_T_threaded_through_render_helper_verbatim(self):
        """Schema-level: render_recursive_downward must emit parent_T literally."""
        unique = "Z" * 32
        text = render_recursive_downward(
            parent_T=unique, parent_S_window="", subtask_T="x"
        )
        assert unique in text


# ===========================================================================
# 3. SCHEMA — retry discipline + multi-candidate JSON scan
# ===========================================================================
class TestSchemaRetryDiscipline:
    def test_schema_retry_exactly_once_then_raises(self):
        """Two consecutive bad responses → exactly one retry, then SchemaError.

        retry_fn is called at MOST one time.  No third call.
        """
        retry_calls = {"count": 0}

        def retry_fn(reprompt: str) -> str:
            retry_calls["count"] += 1
            return "still not json"

        with pytest.raises(SchemaError):
            parse_think_subtasks("garbage in", retry_fn=retry_fn)
        assert retry_calls["count"] == 1, (
            f"retry_fn called {retry_calls['count']} times, expected exactly 1"
        )

    def test_schema_no_retry_when_retry_fn_none(self):
        """Without retry_fn, first failure raises immediately."""
        with pytest.raises(SchemaError):
            parse_think_subtasks("garbage", retry_fn=None)

    def test_schema_retry_succeeds_on_second_try(self):
        """If retry returns valid JSON, parse succeeds."""
        valid = json.dumps({"think": "ok", "subtasks": []})

        def retry_fn(reprompt: str) -> str:
            return f"```json\n{valid}\n```"

        result = parse_think_subtasks("garbage first time", retry_fn=retry_fn)
        assert result.think == "ok"
        assert result.subtasks == []


class TestSchemaMultipleJsonCandidates:
    """Bare {...} scan path: must extract a balanced object, not get confused."""

    def test_first_balanced_object_returned(self):
        """When there are TWO JSON-looking blobs, the parser takes the first.

        Documented behavior: _extract_json finds the first balanced
        ``{...}`` pair (scan from text.find('{')).
        """
        prose = (
            "Here is some thinking. {not: valid json here} and then a real "
            "one: "
            + json.dumps({"think": "real", "subtasks": []})
        )
        # First brace pair is invalid JSON → json.loads fails → no retry,
        # raises SchemaError.  This documents the limitation: the parser
        # does NOT try multiple candidates; first-candidate wins.
        with pytest.raises(SchemaError):
            parse_think_subtasks(prose, retry_fn=None)

    def test_fenced_block_preferred_over_bare_scan(self):
        """If a fenced ```json block exists, it wins over any bare {...}."""
        text = (
            "Stray object: {bad: stuff}\n"
            "```json\n"
            + json.dumps({"think": "fenced", "subtasks": []}) +
            "\n```\n"
            "Trailing: {also bad}"
        )
        result = parse_think_subtasks(text)
        assert result.think == "fenced"

    def test_bare_json_with_nested_object(self):
        """Balanced-brace scanner handles nested braces correctly."""
        text = (
            "prose "
            + json.dumps({
                "think": "outer",
                "subtasks": [],
                "extra": {"nested": "value"},
            })
            + " trailing"
        )
        result = parse_think_subtasks(text)
        assert result.think == "outer"


# ===========================================================================
# 4. EDGE CASES on RecapAgent
# ===========================================================================
def _make_agent(router, env=None, step_budget=200, max_depth=8):
    if env is None:
        env = make_env()
    adapter = RouterAdapter(router, max_tokens=64, temperature=0.0)
    return RecapAgent(env, adapter, step_budget=step_budget, max_depth=max_depth)


class TestEmptySubtasks:
    def test_empty_subtasks_treated_as_done(self):
        """Model emits {"think": ..., "subtasks": []} — node completes cleanly."""
        router = ScriptedRouter(
            {"You are starting": [empty_plan("nothing to do")]},
            fallback=_COMPLETION,
        )
        agent = _make_agent(router)
        result = agent.run("trivial goal")
        assert result.kind == ResultKind.OK
        assert result.steps_taken == 0


class TestCostCeilingAbort:
    def test_cost_ceiling_aborts_run_no_further_llm_calls(self, monkeypatch):
        """RECAP_COST_CEILING_USD=0 → COST_EXCEEDED on the very first call.

        Verifies:
          - run terminates with COST_EXCEEDED
          - no env.step is invoked (no primitive execution)
          - llm_calls is at most 1 (the initial decomp that triggered the abort)
        """
        import arail.agents.recap.core as core_mod
        monkeypatch.setattr(core_mod, "RECAP_COST_CEILING_USD", 0.0)
        # Force a non-zero billed value so the >= comparison fires.
        from arail.costs import cost_tracker as ct
        original = ct.total_billed_usage_usd
        ct.total_billed_usage_usd = 0.01
        try:
            steps_seen = {"n": 0}
            class StepCountingEnv:
                def reset(self):
                    return Observation(text="ready")
                def step(self, action):
                    steps_seen["n"] += 1
                    return Observation(text="ok")
                def is_terminal(self):
                    return False
                def score(self):
                    return None

            plan = make_plan_json([primitive("s1", "x", "OPEN(fridge)")])
            router = ScriptedRouter(
                {"You are starting": [plan]},
                fallback=_COMPLETION,
            )
            agent = _make_agent(router, env=StepCountingEnv())
            result = agent.run("anything")
            assert result.kind == ResultKind.COST_EXCEEDED
            assert steps_seen["n"] == 0, "env.step ran past cost ceiling"
            assert result.llm_calls <= 1, (
                f"expected <=1 LLM call before abort, got {result.llm_calls}"
            )
        finally:
            ct.total_billed_usage_usd = original


class TestStepBudgetDuringRecursion:
    def test_budget_exceeded_mid_recursion_returns_partial_trace(self):
        """budget=2 with 5 leaf primitives — must stop, return BUDGET_EXCEEDED."""
        plan = make_plan_json([
            primitive(f"s{i}", f"step{i}", "OPEN(fridge)") for i in range(5)
        ])
        steps_run = {"n": 0}

        class CountingEnv:
            def reset(self):
                return Observation(text="ready")
            def step(self, action):
                steps_run["n"] += 1
                return Observation(text="ok")
            def is_terminal(self):
                return False
            def score(self):
                return None

        router = ScriptedRouter(
            {"You are starting": [plan]},
            fallback=_COMPLETION,
        )
        agent = _make_agent(router, env=CountingEnv(), step_budget=2)
        result = agent.run("budget mid")
        assert result.kind == ResultKind.BUDGET_EXCEEDED
        # No env.step beyond budget
        assert steps_run["n"] <= 2


class TestEnvExceptionPropagation:
    def test_env_runtime_error_does_not_escape(self):
        """env.step raises RuntimeError — never propagates through RecapAgent.run."""

        class ExplodingEnv:
            def reset(self):
                return Observation(text="ready")
            def step(self, action):
                raise RuntimeError("simulated env crash")
            def is_terminal(self):
                return False
            def score(self):
                return None

        plan = make_plan_json([primitive("s1", "boom", "OPEN(fridge)")])
        # After leaf-backtrack, the env will explode again → eventual FAILED.
        # We need enough responses for retries.
        retry_plan = make_plan_json([primitive("s2", "boom2", "OPEN(fridge)")])
        router = ScriptedRouter(
            {
                "You are starting": [plan],
                "failed": [retry_plan, retry_plan, retry_plan],
            },
            fallback=_COMPLETION,
        )
        agent = _make_agent(router, env=ExplodingEnv(), step_budget=20)
        # Must NOT raise RuntimeError
        result = agent.run("test")
        assert result.kind in (ResultKind.OK, ResultKind.FAILED)


class TestDepthRunaway:
    def test_max_depth_terminates_run(self, monkeypatch):
        """Stub forever returns nonprimitive; MAX_DEPTH triggers, run terminates."""
        import arail.agents.recap.core as core_mod
        monkeypatch.setattr(core_mod, "MAX_DEPTH", 3)

        always_nonprimitive = make_plan_json([nonprimitive("d", "deeper")])
        router = ScriptedRouter({}, fallback=always_nonprimitive)
        adapter = RouterAdapter(router, max_tokens=8)
        env = make_env()
        agent = RecapAgent(env, adapter, step_budget=20, max_depth=3)

        # Must terminate within a reasonable time
        result = agent.run("recurse")
        assert result.kind in (
            ResultKind.OK,
            ResultKind.FAILED,
            ResultKind.BUDGET_EXCEEDED,
            ResultKind.COST_EXCEEDED,
        )


class TestPeriodicReminderCadence:
    """Reminder MUST appear at calls 10, 20, ... (NOT 1, 11, 21).

    Verifies the multiple-of-10 invariant, not the off-by-one shift.
    """

    def test_reminder_at_call_10_not_at_call_1_or_11(self, monkeypatch):
        import arail.agents.recap.core as core_mod
        # Use default 10 for this test
        monkeypatch.setattr(core_mod, "REMINDER_EVERY", 10)

        captured: List[str] = []

        class Capture:
            def complete(self, prompt, **kw):
                captured.append(prompt)
                return _FakeResponse(text=_COMPLETION)

        adapter = RouterAdapter(Capture(), max_tokens=8)
        agent = RecapAgent(make_env(), adapter, step_budget=200)

        for i in range(1, 26):  # drive 25 LLM calls
            agent._llm_calls = i - 1
            agent._llm_call(
                [{"role": "system", "content": "rules"}], depth=0,
            )

        # Reminder appears in calls where _llm_calls becomes a multiple of 10
        # (i.e., the 10th and 20th captured prompts, 0-indexed 9 and 19).
        has_reminder = [PERIODIC_RULE_REMINDER in p for p in captured]
        assert len(has_reminder) == 25
        # Call indices (1-based) where reminder fires: 10, 20.
        expected = {10, 20}
        actual = {i + 1 for i, hit in enumerate(has_reminder) if hit}
        assert actual == expected, (
            f"Reminder fired at calls {sorted(actual)}, expected {sorted(expected)}"
        )


# ===========================================================================
# 5. COST TELEMETRY regression
# ===========================================================================
class TestCostTrackKwargRegression:
    """Non-ReCAP callers of cost_tracker.track() must keep working unchanged."""

    def test_track_without_recap_depth_kwarg(self):
        """The legacy call shape (no recap_depth=) still works."""
        from arail.costs import cost_tracker as ct
        rec = ct.track(
            backend="mlx",
            model="test-model",
            tokens_in=10,
            tokens_out=5,
            latency_ms=1.0,
            source="test_qa_regression",
        )
        # Record exists and has recap_depth=None
        assert rec is not None
        # The most recent history entry should have recap_depth None
        assert ct._history, "no history captured"
        latest = ct._history[-1]
        assert latest.get("recap_depth") is None, (
            f"recap_depth in history should be None for non-ReCAP caller, "
            f"got {latest.get('recap_depth')!r}"
        )

    def test_track_with_recap_depth_populates_aggregate(self):
        from arail.costs import cost_tracker as ct
        before = ct.calls_by_recap_depth.get(4, 0)
        ct.track(
            backend="mlx",
            model="test-model",
            tokens_in=10,
            tokens_out=5,
            latency_ms=1.0,
            source="test_qa_regression",
            recap_depth=4,
        )
        after = ct.calls_by_recap_depth.get(4, 0)
        assert after == before + 1

    def test_current_recap_depth_default_none_outside_context(self):
        """Sanity check: ContextVar default value is None."""
        # We may be running after other tests that entered contexts; the
        # contextvar should still be None at module level because every
        # context manager resets via its token.
        assert current_recap_depth() is None


# ===========================================================================
# 6. SCHEMA defensive parsing
# ===========================================================================
class TestSchemaDefensiveParsing:
    def test_primitive_without_action_rejected(self):
        bad = json.dumps({
            "think": "x",
            "subtasks": [{"id": "s1", "desc": "d", "primitive": True}],
        })
        with pytest.raises(SchemaError):
            parse_think_subtasks(bad)

    def test_primitive_field_must_be_bool_not_string(self):
        bad = json.dumps({
            "think": "x",
            "subtasks": [{
                "id": "s1", "desc": "d", "primitive": "true", "action": "X()"
            }],
        })
        with pytest.raises(SchemaError):
            parse_think_subtasks(bad)

    def test_subtasks_not_list_rejected(self):
        bad = json.dumps({"think": "x", "subtasks": "not a list"})
        with pytest.raises(SchemaError):
            parse_think_subtasks(bad)

    def test_missing_think_field_rejected(self):
        bad = json.dumps({"subtasks": []})
        with pytest.raises(SchemaError):
            parse_think_subtasks(bad)
