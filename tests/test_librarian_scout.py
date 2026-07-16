"""Librarian term scout — mining, ubiquity threshold, rejected-memory,
sidecar schema, and the approve → gate → reseal → swap human gate.

The MCP scenario end-to-end: "Model Context Protocol" starts recurring
across independent lab signals → the scout drafts a proposal (honestly
model-asserted) → the operator approves → the term compiles into the
sealed World and the provenance tier flips to mixed.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from arail import librarian_scout as ls
from arail import world_mount as wm
from arail.portal import world_routes as wr
from arail.portal.app import app
from tests.world_bundle_builder import make_bundle

CSRF = {"sec-fetch-site": "same-origin"}


class DraftRouter:
    """Scripted local brain for the DEFINE step of a proposal draft."""
    backend_name = "fake-local"

    def complete(self, prompt, max_tokens=0, temperature=0, **kw):
        class R:
            model = "fake-local"
            text = ('{"category": "basics", '
                    '"short": "An open protocol for tool-using agents.", '
                    '"definition": "A protocol that standardizes how models '
                    'reach tools and context.", '
                    '"example": "The lab wired its tools over it.", '
                    '"related": ["alpha-term"]}')
        return R()


@pytest.fixture()
def mounted(tmp_path, monkeypatch):
    worlds = tmp_path / "worlds"; data = tmp_path / "data"; pkb = tmp_path / "pkb"
    worlds.mkdir(); data.mkdir(); pkb.mkdir()
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    b = make_bundle(tmp_path / "b", slug="testworld", display_name="Test World")
    wm.mount(b, data_dir=data, pkb_root=pkb, worlds_dir=worlds)
    yield worlds / "testworld", pkb


def _drop_signals(pkb, kinds=("inbox", "sources", "research")):
    """Three sightings across independent signal kinds."""
    for sub in kinds:
        d = pkb / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / "note.md").write_text(
            "Everyone is talking about the Model Context Protocol lately — "
            "agents reach tools over it.")


# ── mining + threshold ──────────────────────────────────────────────────

def test_mine_finds_recurring_phrase(mounted):
    _bundle, pkb = mounted
    _drop_signals(pkb)
    found = ls.mine_candidates(pkb, known_slugs={"alpha-term"}, rejected={})
    slugs = {f["slug"] for f in found}
    assert "model-context-protocol" in slugs
    kinds = {f["kind"] for f in found if f["slug"] == "model-context-protocol"}
    assert kinds == {"pkb", "research"}


def test_mine_skips_known_and_rejected(mounted):
    _bundle, pkb = mounted
    _drop_signals(pkb)
    found = ls.mine_candidates(
        pkb, known_slugs={"model-context-protocol"}, rejected={})
    assert not any(f["slug"] == "model-context-protocol" for f in found)
    found = ls.mine_candidates(
        pkb, known_slugs=set(),
        rejected={"model-context-protocol": {"ts": "x", "by": "operator"}})
    assert not any(f["slug"] == "model-context-protocol" for f in found)


def test_ubiquity_threshold_two_kinds_ripen():
    doc = {"schema": ls.SCHEMA, "candidates": {}, "proposals": [], "rejected": {}}
    now = time.time()
    one_kind = [{"slug": "solo", "term": "Solo", "kind": "pkb",
                 "path": "inbox/a.md", "excerpt": "", "ts": now}]
    two_kinds = [
        {"slug": "mcp", "term": "MCP", "kind": "pkb",
         "path": "inbox/a.md", "excerpt": "", "ts": now},
        {"slug": "mcp", "term": "MCP", "kind": "research",
         "path": "research/b.md", "excerpt": "", "ts": now},
    ]
    ls.merge_evidence(doc, one_kind + two_kinds, now=now)
    ripe = dict(ls.ripe_candidates(doc))
    assert "mcp" in ripe, "two independent signal kinds must ripen"
    assert "solo" not in ripe, "a single sighting must NOT ripen"


def test_evidence_expires_outside_window():
    doc = {"schema": ls.SCHEMA, "candidates": {}, "proposals": [], "rejected": {}}
    now = time.time()
    old = now - (ls.EVIDENCE_WINDOW_DAYS + 5) * 86400
    ls.merge_evidence(doc, [
        {"slug": "stale", "term": "Stale", "kind": "pkb",
         "path": "inbox/x.md", "excerpt": "", "ts": old}], now=now)
    assert "stale" not in doc["candidates"], "expired evidence drops the candidate"


def test_sidecar_roundtrip(mounted):
    bundle, _pkb = mounted
    doc = ls.load_sidecar(bundle)
    assert doc["schema"] == ls.SCHEMA
    doc["last_scan"] = "2026-07-15T00:00:00Z"
    ls.save_sidecar(bundle, doc)
    again = ls.load_sidecar(bundle)
    assert again["last_scan"] == "2026-07-15T00:00:00Z"
    # A sidecar never breaks the seal — it isn't a sealed file.
    assert wm.verify_seal(wm.load_bundle(bundle)).ok


# ── the full pass ───────────────────────────────────────────────────────

def test_scout_pass_files_dreamed_proposal(mounted, monkeypatch):
    bundle, pkb = mounted
    _drop_signals(pkb)
    monkeypatch.setattr(ls, "_try_wikipedia_source", lambda term: None)
    summary = ls.scout_mounted_world(router=DraftRouter(), pkb_root=pkb)
    assert summary["world"] == "testworld" and summary["proposed"] >= 1
    doc = ls.load_sidecar(bundle)
    prop = next(p for p in doc["proposals"]
                if p["slug"] == "model-context-protocol")
    assert prop["status"] == "pending"
    assert prop["source"].startswith("model:"), "locally drafted → dreamed"
    assert prop["tier"] == "model-asserted"
    assert prop["category"] == "basics"
    assert prop["related"] == ["alpha-term"]
    assert len(prop["evidence"]) >= 2


def test_scout_pass_sourced_when_enriched(mounted, monkeypatch):
    bundle, pkb = mounted
    _drop_signals(pkb)
    monkeypatch.setattr(
        ls, "_try_wikipedia_source",
        lambda term: ("https://en.wikipedia.org/wiki/Model_Context_Protocol",
                      "An open protocol standardizing model-tool context."))
    ls.scout_mounted_world(router=DraftRouter(), pkb_root=pkb)
    doc = ls.load_sidecar(bundle)
    prop = next(p for p in doc["proposals"]
                if p["slug"] == "model-context-protocol")
    assert prop["source"].startswith("https://"), "captured URL → sourced tier"
    assert prop["tier"] == "sourced"


# ── the human gate (API) ────────────────────────────────────────────────

def _scouted(mounted, monkeypatch):
    bundle, pkb = mounted
    _drop_signals(pkb)
    monkeypatch.setattr(ls, "_try_wikipedia_source", lambda term: None)
    ls.scout_mounted_world(router=DraftRouter(), pkb_root=pkb)
    return bundle


def test_proposals_endpoint_lists_pending(mounted, monkeypatch):
    _scouted(mounted, monkeypatch)
    with TestClient(app) as c:
        got = c.get("/api/librarian/proposals").json()
        assert got["world"] == "testworld"
        assert any(p["slug"] == "model-context-protocol"
                   for p in got["proposals"])


def test_approve_compiles_term_and_flips_tier(mounted, monkeypatch):
    bundle = _scouted(mounted, monkeypatch)
    doc = ls.load_sidecar(bundle)
    pid = next(p["id"] for p in doc["proposals"]
               if p["slug"] == "model-context-protocol")
    with TestClient(app) as c:
        r = c.post(f"/api/librarian/proposals/{pid}/approve", headers=CSRF)
        assert r.status_code == 200, r.text
        assert r.json()["tier"] == "mixed", (
            "first dreamed term flips a sourced World to mixed — honestly")
    terms = json.loads((bundle / "terms.json").read_bytes())["terms"]
    added = next(t for t in terms if t["slug"] == "model-context-protocol")
    assert added["source"].startswith("model:"), "provenance preserved verbatim"
    assert wm.verify_seal(wm.load_bundle(bundle)).ok, "world resealed"
    doc = ls.load_sidecar(bundle)
    assert all(p["status"] != "pending" or p["slug"] != "model-context-protocol"
               for p in doc["proposals"])


def test_reject_enters_never_repropose_memory(mounted, monkeypatch):
    bundle = _scouted(mounted, monkeypatch)
    _bundle, pkb = mounted
    doc = ls.load_sidecar(bundle)
    pid = next(p["id"] for p in doc["proposals"]
               if p["slug"] == "model-context-protocol")
    with TestClient(app) as c:
        assert c.post(f"/api/librarian/proposals/{pid}/reject",
                      headers=CSRF).status_code == 200
    doc = ls.load_sidecar(bundle)
    assert "model-context-protocol" in doc["rejected"]
    # A fresh scan (files re-touched) never re-proposes it.
    _drop_signals(pkb)
    ls.scout_mounted_world(router=DraftRouter(), pkb_root=pkb)
    doc = ls.load_sidecar(bundle)
    pending = [p for p in doc["proposals"]
               if p["slug"] == "model-context-protocol"
               and p["status"] == "pending"]
    assert not pending, "rejected slugs must never be re-proposed"


def test_proposal_writes_need_csrf(mounted, monkeypatch):
    bundle = _scouted(mounted, monkeypatch)
    doc = ls.load_sidecar(bundle)
    pid = doc["proposals"][0]["id"]
    with TestClient(app) as c:
        r = c.post(f"/api/librarian/proposals/{pid}/approve",
                   headers={"sec-fetch-site": "cross-site"})
        assert r.status_code == 403


def test_status_endpoint_degrades_without_agent(monkeypatch, tmp_path):
    from arail.agents import loader
    monkeypatch.setattr(loader, "load_one", lambda _id: None)
    with TestClient(app) as c:
        got = c.get("/api/librarian/status").json()
        assert got["status"] == "unavailable"


def test_librarian_snapshot_counts_pending(mounted, monkeypatch):
    _scouted(mounted, monkeypatch)
    from arail.agents._builtin_librarian import LibrarianAgent
    snap = LibrarianAgent().snapshot()
    assert snap["world"]["mounted"] is True
    assert snap["scout"]["pending"] >= 1
