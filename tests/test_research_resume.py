"""Interrupted-research resume: checkpoint re-entry, halt respect, honesty.

All goal/tracker/run-state paths are redirected to tmp — these tests must
never touch a developer's real lab/data.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from arail import goals as goals_mod
from arail import scheduler
from arail.goals import GoalStore
from arail.skills.experiment_tracker import ExperimentTracker


@pytest.fixture
def lab(monkeypatch, tmp_path):
    """Tmp-scoped goal store + tracker + run-state, wired into the
    researcher singleton."""
    goals_dir = tmp_path / "goals"
    monkeypatch.setattr(goals_mod, "GOALS_DIR", goals_dir)
    monkeypatch.setattr(goals_mod, "CURRENT_FILE", goals_dir / "current.json")
    monkeypatch.setattr(goals_mod, "HISTORY_DIR", goals_dir / "history")
    monkeypatch.setattr(goals_mod, "PREVIEW_FILE", goals_dir / "preview.json")
    monkeypatch.setattr(goals_mod, "run_state_path",
                        lambda: goals_dir / "run_state.json")

    store = GoalStore()
    tracker = ExperimentTracker(experiments_dir=tmp_path / "experiments")

    from arail.agents import researcher as res_mod
    monkeypatch.setattr(res_mod.researcher, "goal_store", store)
    monkeypatch.setattr(res_mod.researcher, "tracker", tracker)
    # Deterministic, offline, instant.
    monkeypatch.setenv("LAB_EXP_RUNTIME_SEC", "1")
    monkeypatch.setattr(res_mod.researcher, "_plan_research",
                        lambda parsed: ["h1", "h2"])
    monkeypatch.setattr(res_mod.researcher, "_generate_observation",
                        lambda exp, domain, intent: "observed")
    monkeypatch.setattr(res_mod.researcher, "_generate_report",
                        lambda parsed, completed: "# report")
    monkeypatch.setattr(res_mod.researcher, "_brief_block", "", raising=False)
    import arail.pkb as pkb
    for fn in ("write_agent_research", "write_agent_experiment",
               "write_agent_recommendation"):
        monkeypatch.setattr(pkb, fn, lambda *a, **k: None, raising=False)
    import arail.wiki as wiki
    monkeypatch.setattr(wiki, "schedule_rebuild", lambda: None)
    return store, tracker, res_mod


def _seed_interrupted_run(store, tracker, *, progress=0.5):
    parsed = {"goal": "test resilience", "domain": "general", "id": "g1"}
    store.set_goal(parsed)
    e_done = tracker.create(hypothesis="done hyp", methodology="m",
                            variables={}, domain="general")
    tracker.start(e_done["id"])
    tracker.complete(e_done["id"], {"metric": 1}, "fine", True)
    e_open = tracker.create(hypothesis="open hyp", methodology="m",
                            variables={}, domain="general")
    store.link_experiment(e_done["id"])
    store.link_experiment(e_open["id"])
    store.update_progress(progress)
    goals_mod.save_run_state({
        "goal_id": "g1", "status": "running", "paused": False,
        "completed_steps": ["Planned research hypotheses",
                            "Designed experiments", "Gathered sources"],
        "current_task": "Running experiment", "next_step": "Analyze results",
        "planning_trace": {"considered": 2},
    })
    return parsed, e_done["id"], e_open["id"]


def test_resume_skips_completed_experiment(lab, monkeypatch):
    store, tracker, res_mod = lab
    parsed, done_id, open_id = _seed_interrupted_run(store, tracker)

    analyzed = []
    monkeypatch.setattr(
        res_mod.researcher, "_analyze_experiment",
        lambda exp, domain, intent: analyzed.append(exp["id"]) or
        {"conclusion": "ok", "success": True, "metric": 2})

    rs = goals_mod.load_run_state()
    asyncio.run(res_mod.researcher._run(parsed, 0, resume_state=rs))

    assert analyzed == [open_id]                 # completed one NOT re-analyzed
    current = store.get_current()
    assert current["progress"] == 1.0            # continued past checkpoint
    assert current.get("report")
    assert res_mod.researcher.status == "completed"
    assert goals_mod.load_run_state() is None    # cleared on completion


def test_resume_below_checkpoint_replans(lab, monkeypatch):
    store, tracker, res_mod = lab
    parsed = {"goal": "fresh", "domain": "general", "id": "g2"}
    store.set_goal(parsed)
    store.update_progress(0.1)
    goals_mod.save_run_state({"goal_id": "g2", "status": "running",
                              "paused": False, "completed_steps": []})
    designed = []
    monkeypatch.setattr(
        res_mod.researcher, "_design_experiment",
        lambda hyp, domain: designed.append(hyp) or
        tracker.create(hypothesis=hyp, methodology="m", variables={},
                       domain=domain))
    monkeypatch.setattr(
        res_mod.researcher, "_analyze_experiment",
        lambda exp, domain, intent: {"conclusion": "ok", "success": True})
    asyncio.run(res_mod.researcher._run(
        parsed, 0, resume_state=goals_mod.load_run_state()))
    assert designed == ["h1", "h2"]              # honest re-plan from the top
    assert store.get_current()["progress"] == 1.0


def test_boot_reconciliation_auto_resumes(lab, monkeypatch):
    store, tracker, res_mod = lab
    parsed, *_ = _seed_interrupted_run(store, tracker)

    import arail.portal.app as app_mod
    started = []
    monkeypatch.setattr(app_mod, "goal_store", store)
    monkeypatch.setattr(
        res_mod.researcher, "start",
        lambda p, *, delay=None, resume_state=None:
        started.append((p["goal"], resume_state["status"])))
    app_mod._reconcile_interrupted_research()
    assert started == [("test resilience", "running")]


def test_boot_reconciliation_respects_halt(lab, monkeypatch):
    store, tracker, res_mod = lab
    _seed_interrupted_run(store, tracker)
    scheduler.halt_all_jobs()

    import arail.portal.app as app_mod
    started = []
    marked = []
    monkeypatch.setattr(app_mod, "goal_store", store)
    monkeypatch.setattr(res_mod.researcher, "start",
                        lambda *a, **k: started.append(1))
    import arail.agent_workflows as wf
    monkeypatch.setattr(wf, "update_agent_workflow",
                        lambda agent_id, **f: marked.append((agent_id, f)))
    app_mod._reconcile_interrupted_research()

    assert started == []                          # halted lab stays halted
    assert goals_mod.load_run_state()["status"] == "interrupted"
    assert any(f.get("status") == "interrupted" for _, f in marked)


def test_no_run_state_means_no_resume(lab, monkeypatch):
    store, tracker, res_mod = lab
    store.set_goal({"goal": "idle goal", "domain": "general"})
    import arail.portal.app as app_mod
    started = []
    monkeypatch.setattr(app_mod, "goal_store", store)
    monkeypatch.setattr(res_mod.researcher, "start",
                        lambda *a, **k: started.append(1))
    app_mod._reconcile_interrupted_research()
    assert started == []
