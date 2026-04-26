"""Tests for Buddy's goal-aware suggesters.

Each suggester is exercised in isolation with a stub goal record and
the relevant external dependency monkey-patched. The suggesters must:

- Return None when there's nothing to propose.
- Return an Observation with severity="suggest" and a structured
  ``suggestion`` payload when they fire.
- Use a stable per-target ``watcher`` key so the cooldown layer can
  rotate through candidates without thrashing.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from arail.agents import _builtin_buddy as buddy_mod


# ── Phase suggester ───────────────────────────────────────────────

def test_phase_suggester_quiet_below_first_threshold():
    goal = {"id": "g1", "progress": 0.1}
    assert buddy_mod._suggest_phase_action(goal) is None


@pytest.mark.parametrize(
    "progress,expected_phase",
    [
        (0.3, "experiments"),
        (0.5, "sources"),
        (0.7, "run"),
        (0.95, "analyze"),
    ],
)
def test_phase_suggester_fires_at_each_threshold(progress, expected_phase):
    goal = {"id": "g1", "progress": progress}
    obs = buddy_mod._suggest_phase_action(goal)
    assert obs is not None
    assert obs.severity == "suggest"
    assert obs.suggestion == {
        "kind": "phase",
        "target": expected_phase,
        "link": "/research",
    }
    assert obs.watcher.startswith(f"phase:g1:{expected_phase}")


def test_phase_suggester_skips_when_goal_id_missing():
    assert buddy_mod._suggest_phase_action({"progress": 0.5}) is None


# ── Pending-review suggester ───────────────────────────────────────

class _StubExperimentTracker:
    """Drop-in replacement that returns a fixed list."""

    def __init__(self, experiments: List[Dict[str, Any]]) -> None:
        self._experiments = experiments

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._experiments)


def _patch_tracker(monkeypatch, experiments):
    """Replace the ExperimentTracker import inside the buddy module."""
    import arail.skills.experiment_tracker as et_module

    class _StubClass:
        def __init__(self, *args, **kwargs):
            self._experiments = experiments

        def list_all(self):
            return list(self._experiments)

    monkeypatch.setattr(et_module, "ExperimentTracker", _StubClass)


def test_pending_review_quiet_when_nothing_completed(monkeypatch):
    _patch_tracker(monkeypatch, [])
    assert buddy_mod._suggest_pending_review({}) is None


def test_pending_review_quiet_when_too_recent(monkeypatch):
    import datetime
    today = datetime.date.today()
    _patch_tracker(monkeypatch, [{
        "id": "e1",
        "status": "completed",
        "hypothesis_supported": True,
        "hypothesis": "x",
        "end_date": today.isoformat(),
    }])
    assert buddy_mod._suggest_pending_review({}) is None


def test_pending_review_fires_for_stale_experiment(monkeypatch):
    import datetime
    stale_date = (datetime.date.today() - datetime.timedelta(days=4)).isoformat()
    _patch_tracker(monkeypatch, [{
        "id": "e42",
        "status": "completed",
        "hypothesis_supported": False,
        "hypothesis": "throughput improves with batch size",
        "end_date": stale_date,
    }])
    obs = buddy_mod._suggest_pending_review({})
    assert obs is not None
    assert obs.severity == "suggest"
    assert obs.watcher == "review:e42"
    assert obs.suggestion["kind"] == "review"
    assert obs.suggestion["target"] == "e42"


# ── Skill-for-goal suggester ───────────────────────────────────────

def _patch_skill_list(monkeypatch, skills):
    import arail.skills_loader as sl

    monkeypatch.setattr(sl, "list_installed_skills", lambda: list(skills))


class _StubSkill:
    def __init__(self, sid: str, name: str, domain: str) -> None:
        self.id = sid
        self.name = name
        self.domain = domain
        self.version = "1.0.0"


def test_skill_suggester_quiet_when_no_skills(monkeypatch):
    _patch_skill_list(monkeypatch, [])
    assert buddy_mod._suggest_skill_for_goal({"parsed": {"domain": "ai"}}) is None


def test_skill_suggester_fires_on_domain_match(monkeypatch):
    _patch_skill_list(monkeypatch, [
        _StubSkill("evaluate-llm", "Evaluate LLM", "ai"),
        _StubSkill("vet-source", "Vet Source", "research"),
    ])
    obs = buddy_mod._suggest_skill_for_goal({"parsed": {"domain": "ai"}})
    assert obs is not None
    assert obs.severity == "suggest"
    assert obs.watcher == "skill:evaluate-llm"
    assert obs.suggestion["kind"] == "skill"
    assert obs.suggestion["target"] == "evaluate-llm"


def test_skill_suggester_includes_meta_domain_skills(monkeypatch):
    _patch_skill_list(monkeypatch, [
        _StubSkill("observe-lab", "Observe Lab", "meta"),
    ])
    obs = buddy_mod._suggest_skill_for_goal({"parsed": {"domain": "ml"}})
    # ``meta`` is domain-agnostic, so it matches any goal domain.
    assert obs is not None
    assert obs.watcher == "skill:observe-lab"


# ── Next-experiment suggester ──────────────────────────────────────

def test_next_experiment_quiet_when_no_sub_objectives(monkeypatch):
    _patch_tracker(monkeypatch, [])
    assert buddy_mod._suggest_next_experiment({"parsed": {}}) is None


def test_next_experiment_kicks_off_when_no_experiments_yet(monkeypatch):
    _patch_tracker(monkeypatch, [])
    obs = buddy_mod._suggest_next_experiment({
        "parsed": {"sub_objectives": ["raise tokens-per-minute on AeroLLM"]},
    })
    assert obs is not None
    assert obs.severity == "suggest"
    assert obs.watcher == "next:first"
    assert obs.suggestion["kind"] == "experiment"


def test_next_experiment_flags_uncovered_term(monkeypatch):
    _patch_tracker(monkeypatch, [{
        "id": "e1",
        "status": "completed",
        "hypothesis": "increasing batch size raises throughput",
        "methodology": "ablation across batch sizes",
        "variables": ["batch_size"],
    }])
    obs = buddy_mod._suggest_next_experiment({
        "parsed": {"sub_objectives": ["explore quantization tradeoffs"]},
    })
    assert obs is not None
    # The first 5+-char term not in the haystack should win — "quantization".
    assert obs.watcher.startswith("next:")
    assert "quantization" in obs.fact


def test_next_experiment_quiet_when_all_terms_covered(monkeypatch):
    _patch_tracker(monkeypatch, [{
        "id": "e1",
        "status": "completed",
        "hypothesis": "quantization preserves quality at int8",
        "methodology": "evaluate quality across batch sizes",
        "variables": ["quantization", "batch"],
    }])
    obs = buddy_mod._suggest_next_experiment({
        "parsed": {"sub_objectives": ["evaluate quantization quality"]},
    })
    assert obs is None


# ── Observation rank ordering ──────────────────────────────────────

def test_observation_rank_ordering():
    praise = buddy_mod.Observation("w", "praise", "f")
    warn = buddy_mod.Observation("w", "warn", "f")
    info = buddy_mod.Observation("w", "info", "f")
    suggest = buddy_mod.Observation("w", "suggest", "f")
    assert praise.rank() > warn.rank() > info.rank()
    # Suggest ties with info — it's a low-urgency proposal, not a wake-up.
    assert suggest.rank() == info.rank()
