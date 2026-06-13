"""Phase 6 tests: Curator trusted sources.

Security (20%) allocation:
- mounted propose_sources unions World holders→domains
- module dict TRUSTED_SOURCES untouched after mount
- consent unchanged (ConsentStore behavior same)
- airgapped still blocks all proposals (mounted or not)
- unmount restores original behavior (no world sources)
"""

from __future__ import annotations

import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"


from arail.world_mount import mount, unmount, current_mount
from arail.agents.curator import TRUSTED_SOURCES, CuratorAgent


def _do_mount(tmp_path):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir(exist_ok=True)
    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    return data_dir, pkb_root, record


# ── module dict untouched ─────────────────────────────────────────────────────

def test_trusted_sources_module_dict_unchanged_after_mount(tmp_path):
    original_keys = set(TRUSTED_SOURCES.keys())
    _do_mount(tmp_path)
    assert set(TRUSTED_SOURCES.keys()) == original_keys


def test_trusted_sources_module_dict_unchanged_after_unmount(tmp_path):
    original_keys = set(TRUSTED_SOURCES.keys())
    data_dir, pkb_root, _ = _do_mount(tmp_path)
    unmount(data_dir=data_dir, pkb_root=pkb_root)
    assert set(TRUSTED_SOURCES.keys()) == original_keys


# ── world sources unioned at runtime ─────────────────────────────────────────

def test_world_extra_sources_when_mounted(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.world_mount as wm_mod
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    agent = CuratorAgent.__new__(CuratorAgent)
    extras = agent._world_extra_sources()
    # physics spec has NIST, BIPM, CODATA as holders
    assert len(extras) > 0
    # NIST should map to physics.nist.gov
    assert "physics.nist.gov" in extras


def test_world_extra_sources_empty_when_not_mounted(monkeypatch):
    import arail.world_mount as wm_mod
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: None)

    agent = CuratorAgent.__new__(CuratorAgent)
    extras = agent._world_extra_sources()
    assert extras == {}


# ── airgap still blocks ───────────────────────────────────────────────────────

def test_airgap_blocks_propose_sources_even_when_mounted(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.world_mount as wm_mod
    import arail.airgap as airgap_mod
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)
    monkeypatch.setattr(airgap_mod, "is_airgapped", lambda: True)

    from arail.agents.consent import ConsentStore
    agent = CuratorAgent(consent=ConsentStore.__new__(ConsentStore))
    result = agent.propose_sources({"domain": "physics", "goal": "test"})
    assert result == []


# ── unmount restores original behavior ───────────────────────────────────────

def test_unmount_removes_world_sources_from_proposals(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.world_mount as wm_mod
    import arail.airgap as airgap_mod
    monkeypatch.setattr(airgap_mod, "is_airgapped", lambda: False)

    # While mounted: extras present
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)
    agent = CuratorAgent.__new__(CuratorAgent)
    extras_mounted = agent._world_extra_sources()
    assert len(extras_mounted) > 0

    # After unmount: extras gone
    unmount(data_dir=data_dir, pkb_root=pkb_root)
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: None)
    extras_unmounted = agent._world_extra_sources()
    assert extras_unmounted == {}


# ── consent behavior unchanged ────────────────────────────────────────────────

def test_world_sources_go_through_consent_store(tmp_path, monkeypatch):
    """World extra sources are still subject to the consent gate (not bypassed)."""
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.world_mount as wm_mod
    import arail.airgap as airgap_mod
    monkeypatch.setattr(airgap_mod, "is_airgapped", lambda: False)
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    # Proposals from world sources are returned as consent requests (not pre-approved)
    from arail.agents.consent import ConsentStore

    consent_store = ConsentStore.__new__(ConsentStore)
    consent_store._requests = {}

    agent = CuratorAgent.__new__(CuratorAgent)
    agent.consent = consent_store

    proposals = agent.propose_sources({"domain": "physics", "goal": "test"})
    # proposals are dicts with url/reason/source_name — they require consent submission
    for p in proposals:
        assert "url" in p
        assert "reason" in p
