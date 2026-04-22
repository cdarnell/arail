from __future__ import annotations

from pathlib import Path

from oglab import agent_workflows


def test_update_agent_workflow_persists_json(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(agent_workflows, "DATA_DIR", tmp_path)
    snapshot = agent_workflows.update_agent_workflow(
        "researcher",
        status="running",
        objective="Improve retrieval quality",
        current_task="Planning hypotheses",
        next_step="Design experiments",
        completed_steps=["Loaded goal"],
        paused=False,
        chatter={"too_chatty": False},
    )

    assert snapshot["agent_id"] == "researcher"
    path = tmp_path / "agent_workflows.json"
    assert path.exists()
    saved = agent_workflows.get_agent_workflow("researcher")
    assert saved is not None
    assert saved["current_task"] == "Planning hypotheses"
    assert saved["next_step"] == "Design experiments"


def test_workflow_health_reports_snapshot_count(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(agent_workflows, "DATA_DIR", tmp_path)
    agent_workflows.update_agent_workflow(
        "pip",
        status="running",
        objective="Stay helpful without nagging",
        current_task="Watching lab signals",
        next_step="Wait for a watcher to fire",
        completed_steps=[],
        paused=False,
        chatter={"too_chatty": False},
    )

    health = agent_workflows.workflow_health()
    assert health["snapshot_count"] == 1
    assert health["workflow_file_exists"] is True
    assert health["json_dr_enabled"] is True


def test_update_agent_workflow_keeps_json_when_lance_sync_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(agent_workflows, "DATA_DIR", tmp_path)

    def _boom(_rows):
        raise RuntimeError("lance unavailable")

    monkeypatch.setattr(agent_workflows, "_sync_lance_rows", _boom)

    snapshot = agent_workflows.update_agent_workflow(
        "sre",
        status="running",
        objective="Catch incidents",
        current_task="Scanning for incidents",
        next_step="Wait for the next incident",
        completed_steps=["Loaded prior alerts"],
        paused=False,
        chatter={"too_chatty": False},
    )

    assert snapshot["agent_id"] == "sre"
    saved = agent_workflows.get_agent_workflow("sre")
    assert saved is not None
    assert saved["current_task"] == "Scanning for incidents"
    health = agent_workflows.workflow_health()
    assert health["workflow_file_exists"] is True
    assert health["json_dr_enabled"] is True
    assert health["last_lance_sync_error"] == "RuntimeError: lance unavailable"