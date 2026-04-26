from __future__ import annotations

from pathlib import Path

from arail import goals
from arail.goals import GoalStore
from arail.swarm_goals import apply_swarm_plan_edits, compile_swarm_plan


def _configure_goal_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(goals, "GOALS_DIR", tmp_path / "goals")
    monkeypatch.setattr(goals, "CURRENT_FILE", goals.GOALS_DIR / "current.json")
    monkeypatch.setattr(goals, "PREVIEW_FILE", goals.GOALS_DIR / "preview.json")
    monkeypatch.setattr(goals, "HISTORY_DIR", goals.GOALS_DIR / "history")


def test_compile_swarm_plan_for_travel_goal_includes_reviewable_workers():
    parsed_goal = {
        "goal": "Plan a family trip to Hokkaido Japan in late September with flights, hotels, and rail routes.",
        "domain": "general",
        "primary_objective": "Plan a practical Hokkaido family trip",
        "sub_objectives": ["Choose flight strategy", "Pick lodging areas", "Avoid crowd spikes"],
        "success_metrics": {"trip_plan": "bookable", "travel_days": "<= 10"},
        "timeline": "late September",
        "constraints": ["3 adults", "2 children"],
        "resources_needed": ["flight data", "lodging options"],
    }

    plan = compile_swarm_plan(parsed_goal, scale="balanced")

    assert plan["goal_archetype"] == "travel"
    assert plan["execution_mode"] == "review_then_run"
    assert plan["memory"]["primary"] == "lancedb"
    worker_ids = [worker["id"] for worker in plan["workers"]]
    assert "seasonality" in worker_ids
    assert "routing" in worker_ids
    assert any(phase["id"] == "challenge" for phase in plan["phases"])
    assert plan["review"]["deliverables"]


def test_apply_swarm_plan_edits_can_disable_workers_and_rewrite_brief():
    parsed_goal = {
        "goal": "Compare local LLM inference engines for code tasks",
        "domain": "ml-research",
        "primary_objective": "Find the best local inference stack",
        "sub_objectives": ["Benchmark latency", "Compare output quality"],
        "success_metrics": {},
        "timeline": "two weeks",
        "constraints": [],
        "resources_needed": [],
    }
    plan = compile_swarm_plan(parsed_goal, scale="balanced")

    edited = apply_swarm_plan_edits(
        plan,
        mission_brief="Bias toward code quality over raw throughput.",
        operator_notes="Keep the plan local-first.",
        enabled_workers=["scout", "literature", "eval"],
    )

    assert edited["mission_brief"] == "Bias toward code quality over raw throughput."
    assert edited["operator_notes"] == "Keep the plan local-first."
    worker_state = {worker["id"]: worker["enabled"] for worker in edited["workers"]}
    assert worker_state["scout"] is True
    assert worker_state["eval"] is True
    disabled = [worker_id for worker_id, enabled in worker_state.items() if not enabled]
    assert disabled


def test_goal_store_preview_confirm_promotes_swarm_goal(tmp_path, monkeypatch):
    _configure_goal_paths(tmp_path, monkeypatch)
    store = GoalStore()

    first = store.set_goal({"goal": "Existing goal", "primary_objective": "Existing goal"})
    assert first["goal_mode"] == "direct"

    parsed_goal = {
        "goal": "Plan a Japan itinerary with kid-friendly routing",
        "domain": "general",
        "primary_objective": "Plan a Japan itinerary",
        "sub_objectives": ["Choose stops", "Choose routing"],
        "success_metrics": {"nights": "<= 12"},
        "timeline": "October",
        "constraints": ["kid-friendly"],
        "resources_needed": ["rail options"],
    }
    swarm = compile_swarm_plan(parsed_goal)
    preview = store.save_preview(parsed_goal["goal"], parsed_goal, swarm)

    assert preview["status"] == "preview"
    assert store.get_current()["id"] == first["id"]

    confirmed = store.confirm_preview()

    assert confirmed is not None
    assert confirmed["goal_text"] == parsed_goal["goal"]
    assert confirmed["goal_mode"] == "swarm"
    assert confirmed["source"] == "preview"
    assert confirmed["swarm"]["goal_archetype"] == "travel"
    assert confirmed["parsed"]["swarm_plan"]["mission_brief"]
    assert store.get_preview() is None

    history = store.list_history()
    assert history
    assert history[0]["id"] == first["id"]