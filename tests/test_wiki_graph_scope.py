"""The knowledge-graph brain scope — /api/wiki/graph?scope=brain.

"What the lab knows": mounted World terms (solid substrate) + human-approved
knowledge + agent-output candidates as ghosts, with docgen reference and raw
un-approved material excluded. Classification is computed per request from
the Compiled-KB manifests — approving an item must flip its ghost WITHOUT a
wiki rebuild (the cached graph only supplies structure).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from arail import compiled_kb as ckb
from arail.portal import wiki_routes
from arail.portal.app import app
from arail.portal.wiki_routes import _brain_scope

CSRF = {"sec-fetch-site": "same-origin"}


# ---------------------------------------------------------------------------
# Unit — _brain_scope classification rules
# ---------------------------------------------------------------------------

def _node(id_, path, tags=(), group="x"):
    return {"id": id_, "path": path, "tags": list(tags), "group": group,
            "label": id_, "status": "active"}


def _graph(nodes, edges=()):
    return {"nodes": nodes, "edges": list(edges)}


def test_world_terms_kept_solid():
    g = _graph([_node("t1", "sources/world-ai/terms/agent.md", tags=["world-ai", "architecture"])])
    out = _brain_scope(g, world_slug="ai", approved=set(), rejected=set())
    assert len(out["nodes"]) == 1
    n = out["nodes"][0]
    assert n["group"] == "world"
    assert not n.get("ghost"), "a freshly mounted World must not render all-ghost"
    assert n["kind"] == "world_term"


def test_other_worlds_terms_dropped():
    g = _graph([_node("t1", "sources/world-physics/terms/mass.md", tags=["world-physics"])])
    out = _brain_scope(g, world_slug="ai", approved=set(), rejected=set())
    assert out["nodes"] == []


def test_approved_note_kept_solid():
    g = _graph([_node("n1", "notes/insight.md")])
    out = _brain_scope(g, world_slug=None, approved={"notes/insight.md"}, rejected=set())
    assert out["nodes"][0]["group"] == "approved"
    assert not out["nodes"][0].get("ghost")


def test_raw_unapproved_note_dropped():
    g = _graph([_node("n1", "notes/scratch.md"), _node("s1", "sources/articles/x.md")])
    out = _brain_scope(g, world_slug=None, approved=set(), rejected=set())
    assert out["nodes"] == []


def test_compiled_docgen_dropped_even_if_approved():
    """Rule 1 precedence: reference-manual material never enters the brain."""
    g = _graph([_node("d1", "compiled/docs/modules/wiki.md")])
    out = _brain_scope(g, world_slug=None,
                       approved={"compiled/docs/modules/wiki.md"}, rejected=set())
    assert out["nodes"] == []


def test_agent_output_becomes_ghost():
    g = _graph([_node("r1", "agents/research/2026-01-01_report.md")])
    out = _brain_scope(g, world_slug=None, approved=set(), rejected=set())
    n = out["nodes"][0]
    assert n["group"] == "candidate" and n["ghost"] is True
    assert n["kind"] == "agent_research"


def test_approved_agent_output_solidifies():
    g = _graph([_node("r1", "agents/research/2026-01-01_report.md")])
    out = _brain_scope(g, world_slug=None,
                       approved={"agents/research/2026-01-01_report.md"}, rejected=set())
    n = out["nodes"][0]
    assert n["group"] == "approved" and not n.get("ghost")


def test_rejected_agent_output_dropped():
    g = _graph([_node("r1", "agents/research/2026-01-01_report.md")])
    out = _brain_scope(g, world_slug=None, approved=set(),
                       rejected={"agents/research/2026-01-01_report.md"})
    assert out["nodes"] == []


def test_edges_pruned_and_ghost_flagged():
    g = _graph(
        [
            _node("t1", "sources/world-ai/terms/agent.md", tags=["world-ai"]),
            _node("t2", "sources/world-ai/terms/tool.md", tags=["world-ai"]),
            _node("r1", "agents/research/rep.md"),
            _node("n1", "notes/raw.md"),
        ],
        edges=[
            {"source": "t1", "target": "t2", "type": "link"},   # solid–solid
            {"source": "r1", "target": "t1", "type": "link"},   # ghost–solid
            {"source": "n1", "target": "t1", "type": "link"},   # dropped end
        ],
    )
    out = _brain_scope(g, world_slug="ai", approved=set(), rejected=set())
    edges = {(e["source"], e["target"]): e for e in out["edges"]}
    assert set(edges) == {("t1", "t2"), ("r1", "t1")}, "edges to dropped nodes must vanish"
    assert not edges[("t1", "t2")].get("ghost")
    assert edges[("r1", "t1")]["ghost"] is True


def test_no_world_mounted_world_terms_fall_through():
    """Unmounted lab: staged world-term pages are just raw sources."""
    g = _graph([_node("t1", "sources/world-ai/terms/agent.md", tags=["world-ai"])])
    out = _brain_scope(g, world_slug=None, approved=set(), rejected=set())
    assert out["nodes"] == []


# ---------------------------------------------------------------------------
# Endpoint — approve flips ghost→solid with NO wiki rebuild in between
# ---------------------------------------------------------------------------

@pytest.fixture()
def brain_pkb(tmp_path, monkeypatch):
    root = tmp_path / "pkb"
    (root / "notes").mkdir(parents=True)
    (root / "agents" / "research").mkdir(parents=True)
    (root / "notes" / "raw.md").write_text("# Raw note\nnot approved")
    (root / "agents" / "research" / "finding.md").write_text(
        "# Finding\nan agent research output"
    )
    monkeypatch.setattr(ckb, "_pkb_root", lambda: root)
    monkeypatch.setattr(wiki_routes, "PKB_ROOT", root)
    return root


def test_scope_brain_endpoint_approve_solidifies(brain_pkb):
    with TestClient(app) as c:
        r = c.get("/api/wiki/graph?scope=brain")
        assert r.status_code == 200
        g = r.json()
        assert g.get("scope") == "brain"
        by_path = {n["path"]: n for n in g["nodes"]}
        assert "notes/raw.md" not in by_path, "raw un-approved notes stay out of the brain"
        finding = by_path["agents/research/finding.md"]
        assert finding["group"] == "candidate" and finding["ghost"] is True

        # Approve through the real review API — NO wiki rebuild happens here.
        r = c.post("/api/pkb/promote",
                   json={"paths": ["agents/research/finding.md"]}, headers=CSRF)
        assert r.status_code == 200 and r.json()["count"] == 1

        g2 = c.get("/api/wiki/graph?scope=brain").json()
        finding2 = {n["path"]: n for n in g2["nodes"]}["agents/research/finding.md"]
        assert finding2["group"] == "approved"
        assert not finding2.get("ghost"), (
            "approval must solidify the ghost at request time — if this fails, "
            "approval state got baked into the cached graph"
        )

        # Revoke → back to ghost.
        c.post("/api/pkb/revoke",
               json={"paths": ["agents/research/finding.md"]}, headers=CSRF)
        g3 = c.get("/api/wiki/graph?scope=brain").json()
        finding3 = {n["path"]: n for n in g3["nodes"]}["agents/research/finding.md"]
        assert finding3["ghost"] is True


def test_default_graph_unchanged_without_scope(brain_pkb):
    """Existing consumers (full graph, tag filter) see no shape change."""
    with TestClient(app) as c:
        g = c.get("/api/wiki/graph").json()
        assert "scope" not in g
        paths = {n["path"] for n in g["nodes"]}
        assert "notes/raw.md" in paths, "the unscoped graph still shows everything"
