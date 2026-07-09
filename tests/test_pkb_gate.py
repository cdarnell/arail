"""WK-10: the retrieval gate — agents (search_for_agents) build ONLY on the
approved Compiled KB; raw browse (search) still sees everything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from arail import compiled_kb as ckb
from arail import pkb as pkb_mod


def _mk(root: Path, rel: str, text: str):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


@pytest.fixture()
def pkb(tmp_path):
    root = tmp_path / "pkb"
    root.mkdir()
    _mk(root, "notes/approved-note.md", "# Photosynthesis\nchlorophyll converts light")
    _mk(root, "notes/raw-note.md", "# Photosynthesis draft\nchlorophyll unverified draft")
    return root


def test_approved_only_scopes_results(pkb):
    # regex fallback path (no lancedb needed): raw sees both, gated sees one
    raw = {r["path"] for r in pkb_mod.search("chlorophyll", pkb)}
    assert "notes/approved-note.md" in raw and "notes/raw-note.md" in raw

    ckb.approve(["notes/approved-note.md"], pkb)
    gated = {r["path"] for r in pkb_mod.search("chlorophyll", pkb, approved_only=True)}
    assert gated == {"notes/approved-note.md"}, "gate must exclude unapproved raw"


def test_gate_returns_nothing_when_nothing_approved(pkb):
    # hard gate: an empty Compiled KB yields no agent-visible knowledge,
    # rather than silently leaking the raw corpus
    assert pkb_mod.search("chlorophyll", pkb, approved_only=True) == []


def test_search_for_agents_honors_env(pkb, monkeypatch):
    ckb.approve(["notes/approved-note.md"], pkb)
    monkeypatch.setenv("ARAIL_APPROVED_ONLY", "on")
    gated = {r["path"] for r in pkb_mod.search_for_agents("chlorophyll", pkb)}
    assert gated == {"notes/approved-note.md"}

    monkeypatch.setenv("ARAIL_APPROVED_ONLY", "off")
    ungated = {r["path"] for r in pkb_mod.search_for_agents("chlorophyll", pkb)}
    # gate off → the raw (unapproved) note is visible again
    assert "notes/raw-note.md" in ungated
    assert "notes/approved-note.md" in ungated
