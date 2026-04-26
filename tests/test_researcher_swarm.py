from __future__ import annotations

import arail.agents.researcher as researcher_mod
from arail.swarm_goals import compile_swarm_plan


def _parsed_goal() -> dict:
    parsed = {
        "goal": "Plan a family trip to Hokkaido Japan with practical routing and lodging",
        "domain": "general",
        "primary_objective": "Plan a practical Hokkaido family trip",
        "sub_objectives": ["Choose routing", "Choose lodging"],
        "success_metrics": {},
        "timeline": "late September",
        "constraints": ["3 adults", "2 children"],
        "resources_needed": ["flight data", "lodging options"],
    }
    parsed["swarm_plan"] = compile_swarm_plan(parsed, scale="balanced")
    return parsed


def test_swarm_prompt_block_exposes_lanes_and_open_questions():
    agent = researcher_mod.ResearcherAgent()

    block = agent._swarm_prompt_block(_parsed_goal())

    assert "Swarm mission brief" in block
    assert "Enabled worker lanes" in block
    assert "Scout" in block
    assert "Open questions" in block


def test_sync_swarm_phase_updates_worker_workflows(monkeypatch):
    captured: list[tuple[str, dict]] = []

    def fake_update(agent_id: str, **fields):
        captured.append((agent_id, fields))
        return {"agent_id": agent_id, **fields}

    monkeypatch.setattr(researcher_mod, "update_agent_workflow", fake_update)
    agent = researcher_mod.ResearcherAgent()
    parsed_goal = _parsed_goal()

    agent._sync_swarm_phase(parsed_goal, "shape")

    swarm_rows = {agent_id: fields for agent_id, fields in captured if agent_id.startswith("swarm-")}
    assert "swarm-scout" in swarm_rows
    assert swarm_rows["swarm-scout"]["status"] == "running"
    assert any(fields["status"] == "planned" for fields in swarm_rows.values())