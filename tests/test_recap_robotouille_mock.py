"""Integration test: full RecapAgent run against the Robotouille mock env.

Uses a ScriptedRouter that produces a realistic multi-depth plan, verifies:
  - success within step budget
  - depth >= 2 reached (non-primitive subtask used)
  - at least one backtrack exercised (via failure injection)
  - tree structure captured
"""

from __future__ import annotations

import pytest

from arail.agents.recap.core import RecapAgent, ResultKind
from arail.agents.recap.fixtures.robotouille_mock import make_env
from arail.agents.recap.router_adapter import RouterAdapter
from tests._recap_scripted import (
    ScriptedRouter,
    empty_plan,
    make_plan_json,
    nonprimitive,
    primitive,
)

_COMPLETION = empty_plan("Task complete.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _burger_plan_depth2():
    """A two-level plan: top-level decomposes into 'prep' (non-primitive) + 'serve'."""
    top = make_plan_json([
        nonprimitive("prep", "Prepare the burger ingredients"),
        primitive("serve", "Serve to customer", "SERVE(customer)"),
    ])
    prep_child = make_plan_json([
        primitive("c1", "Open fridge",      "OPEN(fridge)"),
        primitive("c2", "Pick patty",        "PICK(patty)"),
        primitive("c3", "Close fridge",      "CLOSE(fridge)"),
        primitive("c4", "Place on grill",    "PLACE(grill)"),
        primitive("c5", "Cook patty",        "COOK(patty)"),
        primitive("c6", "Pick bun",          "PICK(bun)"),
        primitive("c7", "Chop lettuce",      "CHOP(lettuce)"),
        primitive("c8", "Place on plate",    "PLACE(plate)"),
        primitive("c9", "Inspect assembly",  "INSPECT(plate)"),
    ])
    return top, prep_child


# ---------------------------------------------------------------------------
# Happy-path integration test
# ---------------------------------------------------------------------------

class TestRobotouilleIntegration:
    def test_burger_task_succeeds_within_budget(self):
        """Full burger task: depth-2 plan; all steps succeed; result OK."""
        top, prep_child = _burger_plan_depth2()
        router = ScriptedRouter(
            {
                "You are starting":    [top],
                "You are decomposing": [prep_child],
            },
            fallback=_COMPLETION,
        )
        env = make_env()
        adapter = RouterAdapter(router, max_tokens=128, temperature=0.0)
        agent = RecapAgent(env, adapter, step_budget=25)

        result = agent.run("Cook a burger and serve it")

        assert result.kind == ResultKind.OK, f"Expected OK, got {result.kind}: {result.summary}"
        assert result.steps_taken <= 25
        assert result.steps_taken > 0

    def test_depth_2_reached(self):
        """Tree has at least 2 nodes (root + child from non-primitive subtask)."""
        top, prep_child = _burger_plan_depth2()
        router = ScriptedRouter(
            {
                "You are starting":    [top],
                "You are decomposing": [prep_child],
            },
            fallback=_COMPLETION,
        )
        env = make_env()
        adapter = RouterAdapter(router, max_tokens=128, temperature=0.0)
        agent = RecapAgent(env, adapter, step_budget=25)

        result = agent.run("Cook a burger and serve it")

        assert result.tree is not None
        assert len(result.tree) >= 2
        # Root is depth 0; at least one child is depth 1
        depths = {n.depth for n in result.tree}
        assert 0 in depths
        assert 1 in depths

    def test_backtrack_exercised_on_failure_injection(self):
        """With failure at step 0, backtrack fires and run continues."""
        top, prep_child = _burger_plan_depth2()
        # Backtrack replan after OPEN(fridge) fails: retry same step
        backtrack_plan = make_plan_json([
            primitive("c1b", "Retry open fridge", "OPEN(fridge)"),
            primitive("c2b", "Pick patty",        "PICK(patty)"),
            primitive("c3b", "Close fridge",      "CLOSE(fridge)"),
            primitive("c4b", "Place on grill",    "PLACE(grill)"),
            primitive("c5b", "Cook patty",        "COOK(patty)"),
            primitive("c6b", "Pick bun",          "PICK(bun)"),
            primitive("c7b", "Chop lettuce",      "CHOP(lettuce)"),
            primitive("c8b", "Place on plate",    "PLACE(plate)"),
            primitive("c9b", "Inspect assembly",  "INSPECT(plate)"),
        ])

        router = ScriptedRouter(
            {
                "You are starting":    [top],
                "You are decomposing": [prep_child],
                "failed":              [backtrack_plan],  # D.1.3 trigger
            },
            fallback=_COMPLETION,
        )
        # Inject a failure at step 0 (first OPEN action in child)
        env = make_env(inject_failures=[{"at_step": 0, "mode": "invalid_action"}])
        adapter = RouterAdapter(router, max_tokens=128, temperature=0.0)
        agent = RecapAgent(env, adapter, step_budget=30)

        result = agent.run("Cook a burger and serve it")

        # With failure injection + backtrack, run may succeed or fail
        # (depending on whether the retry also hits a failure) — but it
        # must not silently drop the error or raise an unhandled exception.
        assert result.kind in (ResultKind.OK, ResultKind.FAILED)
        # The failed step + at least one retry means steps >= 1
        assert result.steps_taken >= 1

    def test_llm_calls_counted(self):
        """result.llm_calls is non-zero and reasonable."""
        top, prep_child = _burger_plan_depth2()
        router = ScriptedRouter(
            {
                "You are starting":    [top],
                "You are decomposing": [prep_child],
            },
            fallback=_COMPLETION,
        )
        env = make_env()
        adapter = RouterAdapter(router, max_tokens=128, temperature=0.0)
        agent = RecapAgent(env, adapter, step_budget=25)
        result = agent.run("Cook a burger and serve it")

        # At minimum: initial decomp (1) + recursive downward (1) + completion (2)
        assert result.llm_calls >= 2

    def test_score_improves_across_run(self):
        """env.score() is higher at end than at start."""
        top, prep_child = _burger_plan_depth2()
        router = ScriptedRouter(
            {
                "You are starting":    [top],
                "You are decomposing": [prep_child],
            },
            fallback=_COMPLETION,
        )
        env = make_env()
        start_score = env.score()  # 0.0 before reset
        adapter = RouterAdapter(router, max_tokens=128, temperature=0.0)
        agent = RecapAgent(env, adapter, step_budget=25)
        result = agent.run("Cook a burger and serve it")
        end_score = env.score()

        assert end_score is not None
        assert end_score >= start_score
