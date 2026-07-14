"""The lab brief — one shared context for humans and agents.

Covers: curated-first degradation (an empty lab briefs cleanly), the
approved-knowledge digest, the stat-keyed cache, the markdown cap, the
/api/lab/brief endpoint (JSON + ?format=md), and the Buddy/Researcher
injection hooks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail import compiled_kb as ckb
from arail import lab_brief as lb

CSRF = {"sec-fetch-site": "same-origin"}


@pytest.fixture(autouse=True)
def _reset_brief_cache():
    lb._cache.update({"key": None, "expires": 0.0, "brief": None})
    yield
    lb._cache.update({"key": None, "expires": 0.0, "brief": None})


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    """A tmp lab: pkb root + cwd-relative lab/data for goals/redirects."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "pkb"
    (root / "agents" / "research").mkdir(parents=True)
    (root / "notes").mkdir(parents=True)
    (root / "notes" / "insight.md").write_text("# Insight\nan approved note")
    (root / "agents" / "research" / "2026-01-02_report.md").write_text(
        "# Report\nfindings"
    )
    monkeypatch.setattr(ckb, "_pkb_root", lambda: root)
    return root


# ---------------------------------------------------------------------------
# build_brief — degradation + digest
# ---------------------------------------------------------------------------

def test_empty_lab_briefs_cleanly(tmp_path, monkeypatch):
    """Curated-first: a brand-new lab (nothing mounted, no goal, no files)
    produces a complete brief with empty/None sections — never an error."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "empty-pkb"
    monkeypatch.setattr(ckb, "_pkb_root", lambda: root)
    brief = lb.build_brief(root)
    assert brief["schema"] == lb.SCHEMA
    assert brief["world"] is None
    assert brief["goal"] is None
    assert brief["research_program"]["exists"] is False
    assert brief["redirects"] == {}
    assert brief["knowledge"]["approved_total"] == 0
    assert brief["recent_agent_outputs"] == []
    md = lb.brief_markdown(brief)
    assert "# Lab brief" in md and "World: none mounted" in md


def test_brief_digests_goal_and_approvals(lab, tmp_path):
    goals_dir = tmp_path / "lab" / "data" / "goals"
    goals_dir.mkdir(parents=True)
    (goals_dir / "current.json").write_text(json.dumps(
        {"goal_text": "Beat the KV-cache baseline", "progress": 0.4}))

    ckb.approve(["notes/insight.md"], lab)
    brief = lb.build_brief(lab)

    assert brief["goal"]["goal_text"] == "Beat the KV-cache baseline"
    k = brief["knowledge"]
    assert k["approved_total"] == 1
    assert k["approved_by_kind"] == {"note": 1}
    assert k["recent_approved"][0]["title"] == "Insight"
    # the agent report is a candidate, not yet approved
    assert k["pending_total"] >= 1
    outs = brief["recent_agent_outputs"]
    assert outs and outs[0]["path"] == "agents/research/2026-01-02_report.md"
    assert outs[0]["approved"] is False
    assert outs[0]["kind"] == "agent_research"

    md = lb.brief_markdown(brief)
    assert "Beat the KV-cache baseline" in md
    assert "1 approved" in md
    assert len(md.splitlines()) <= lb._MARKDOWN_MAX_LINES


def test_markdown_flags_gate_state(lab, monkeypatch):
    monkeypatch.setenv("ARAIL_APPROVED_ONLY", "off")
    md = lb.brief_markdown(lb.build_brief(lab))
    assert "raw corpus (gate off)" in md


# ---------------------------------------------------------------------------
# Cache — stat-keyed invalidation
# ---------------------------------------------------------------------------

def test_cache_reuses_until_manifest_changes(lab):
    b1 = lb.get_cached_brief(lab)
    b2 = lb.get_cached_brief(lab)
    assert b1 is b2, "unchanged sources within TTL must hit the cache"

    ckb.approve(["notes/insight.md"], lab)  # bumps approved.json mtime
    b3 = lb.get_cached_brief(lab)
    assert b3 is not b1
    assert b3["knowledge"]["approved_total"] == 1


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

def test_api_lab_brief_json_and_markdown(lab):
    from arail.portal.app import app
    with TestClient(app) as c:
        r = c.get("/api/lab/brief")
        assert r.status_code == 200
        body = r.json()
        assert body["schema"] == lb.SCHEMA
        assert "knowledge" in body and "world" in body

        r2 = c.get("/api/lab/brief?format=md")
        assert r2.status_code == 200
        assert r2.headers["content-type"].startswith("text/markdown")
        assert r2.text.startswith("# Lab brief")


# ---------------------------------------------------------------------------
# Agent hooks — Buddy's state block and the Researcher's prompt block
# ---------------------------------------------------------------------------

_FIXED_BRIEF = {
    "schema": lb.SCHEMA,
    "world": {"slug": "ai", "display_name": "AI & Machine Learning",
              "provenance_tier": "sourced", "term_count": 331,
              "category_count": 14},
    "goal": None,
    "research_program": {"exists": True, "objective": "Faster SSD inference",
                         "excerpt": "", "knob_count": 3,
                         "path": "research/program.md"},
    "redirects": {"researcher": {"instruction": "Focus on measurement",
                                 "preset": "", "set_at": ""}},
    "knowledge": {"gate_enabled": True, "approved_total": 3,
                  "approved_by_kind": {"note": 3}, "recent_approved": [],
                  "pending_total": 7},
    "recent_agent_outputs": [],
}


def test_buddy_state_block_includes_brief(monkeypatch):
    monkeypatch.setattr(lb, "get_cached_brief", lambda *a, **k: _FIXED_BRIEF)
    from arail import lab_brain
    block = lab_brain._state_block()
    assert "AI & Machine Learning" in block
    assert "3 approved, 7 pending review" in block
    assert "Operator redirect (researcher): Focus on measurement" in block
    assert "Research program: Faster SSD inference" in block


def test_researcher_brief_prompt_block(monkeypatch):
    monkeypatch.setattr(lb, "get_cached_brief", lambda *a, **k: _FIXED_BRIEF)
    from arail.agents.researcher import _brief_prompt_block
    block = _brief_prompt_block()
    assert block.startswith("# Lab brief")
    assert block.endswith("\n\n"), "prompt blocks are prepended — must self-separate"
    assert "331 terms" in block


def test_researcher_brief_block_never_raises(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("brief backend down")
    monkeypatch.setattr(lb, "get_cached_brief", _boom)
    from arail.agents.researcher import _brief_prompt_block
    assert _brief_prompt_block() == "", "a missing brief must never stall a run"
