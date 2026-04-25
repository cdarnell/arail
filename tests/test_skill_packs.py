"""Tests for the Skills marketplace + per-agent loadouts.

Covers:
  - skill_packs module: manifest loads; install + remove are
    idempotent; force=False preserves user edits; remove leaves
    user-authored skills intact.
  - agent_seed: default AGENT.md scaffolds get written for the
    builtin agents, never overwriting an existing file.
  - /api/skills/<id> save: validates frontmatter, refuses junk.
  - /api/agents/<id>/loadout: round-trips skill list into AGENT.md.
  - /api/skills/packs/install: end-to-end via TestClient.
  - /docs/<path>: serves local markdown, rejects traversal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ── skill_packs module ──────────────────────────────────────────────

def test_manifest_loads_and_every_skill_exists_on_disk():
    from arail.skill_packs import list_packs, _PACKS_DIR

    packs = list_packs()
    assert len(packs) >= 3, "expected at least 3 shipped packs"
    for pack in packs:
        assert pack.id and pack.name
        assert pack.skills, f"pack {pack.id} has no skills"
        for sid in pack.skills:
            src = _PACKS_DIR / pack.id / sid / "SKILL.md"
            assert src.exists(), f"manifest declares {pack.id}/{sid} but file missing"


def test_install_pack_is_idempotent(tmp_path: Path):
    from arail.skill_packs import install_pack

    res1 = install_pack("curation-vetting", pkb_root=tmp_path)
    assert res1["ok"] is True
    assert len(res1["installed"]) == 3
    assert res1["skipped_existing"] == []

    res2 = install_pack("curation-vetting", pkb_root=tmp_path)
    assert res2["ok"] is True
    assert res2["installed"] == []
    assert len(res2["skipped_existing"]) == 3


def test_install_pack_force_overwrites_user_edits(tmp_path: Path):
    from arail.skill_packs import install_pack

    install_pack("curation-vetting", pkb_root=tmp_path)
    edited = tmp_path / "skills" / "vet-source" / "SKILL.md"
    edited.write_text("--- TAINTED ---\n")

    # Without force: user version preserved.
    res = install_pack("curation-vetting", pkb_root=tmp_path)
    assert "--- TAINTED ---" in edited.read_text()
    assert "vet-source" in res["skipped_existing"]

    # With force: user version replaced.
    install_pack("curation-vetting", pkb_root=tmp_path, force=True)
    body = edited.read_text()
    assert "--- TAINTED ---" not in body
    assert "Vetting a Source" in body


def test_remove_pack_preserves_user_skills(tmp_path: Path):
    from arail.skill_packs import install_pack, remove_pack

    install_pack("curation-vetting", pkb_root=tmp_path)
    user = tmp_path / "skills" / "my-custom-skill" / "SKILL.md"
    user.parent.mkdir()
    user.write_text("--- USER ---\n")

    res = remove_pack("curation-vetting", pkb_root=tmp_path)
    assert res["ok"] is True
    assert len(res["removed"]) == 3

    assert user.exists()
    assert user.read_text() == "--- USER ---\n"
    assert not (tmp_path / "skills" / "vet-source").exists()


def test_remove_unknown_pack_returns_error():
    from arail.skill_packs import remove_pack
    res = remove_pack("does-not-exist")
    assert res["ok"] is False
    assert "unknown" in res["error"]


def test_packs_with_status_reflects_install_state(tmp_path: Path):
    from arail.skill_packs import install_pack, packs_with_status

    install_pack("curation-vetting", pkb_root=tmp_path)
    rows = packs_with_status(pkb_root=tmp_path)
    by_id = {p["id"]: p for p in rows}
    assert by_id["curation-vetting"]["installed_count"] == 3
    assert by_id["curation-vetting"]["fully_installed"] is True
    assert by_id["research-methodology"]["installed_count"] == 0


# ── agent_seed module ──────────────────────────────────────────────

def test_ensure_default_loadouts_writes_three_agents(tmp_path: Path):
    from arail.agent_seed import ensure_default_loadouts

    res = ensure_default_loadouts(pkb_root=tmp_path)
    assert res["ok"] is True
    assert sorted(res["written"]) == ["browser", "curator", "researcher"]

    for agent_id in ("researcher", "curator", "browser"):
        agent_md = tmp_path / "agents" / agent_id / "AGENT.md"
        assert agent_md.exists()
        body = agent_md.read_text()
        assert f"id: {agent_id}" in body
        assert "skills:" in body


def test_ensure_default_loadouts_is_idempotent(tmp_path: Path):
    from arail.agent_seed import ensure_default_loadouts

    ensure_default_loadouts(pkb_root=tmp_path)
    res = ensure_default_loadouts(pkb_root=tmp_path)
    assert res["written"] == []
    assert sorted(res["skipped"]) == ["browser", "curator", "researcher"]


def test_ensure_default_loadouts_never_overwrites_user_edits(tmp_path: Path):
    from arail.agent_seed import ensure_default_loadouts

    pre_edited = tmp_path / "agents" / "researcher" / "AGENT.md"
    pre_edited.parent.mkdir(parents=True)
    pre_edited.write_text("--- USER VERSION ---\n")

    ensure_default_loadouts(pkb_root=tmp_path)
    assert pre_edited.read_text() == "--- USER VERSION ---\n"


# ── API: /api/skills/<id> save ─────────────────────────────────────

def _client():
    import arail.portal.app as app_mod
    return TestClient(app_mod.app), app_mod


def test_api_skills_save_validates_frontmatter(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib, arail.config
    importlib.reload(arail.config)
    import arail.portal.app as app_mod
    importlib.reload(app_mod)

    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("placeholder")

    client = TestClient(app_mod.app)
    # Missing required `name` and `domain` frontmatter keys.
    r = client.post("/api/skills/test-skill", json={
        "content": "---\nid: test-skill\n---\n\n# body\n",
    })
    body = r.json()
    assert body["ok"] is False
    assert "missing required keys" in body["error"]


def test_api_skills_save_rejects_id_mismatch(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib, arail.config, arail.portal.app as app_mod
    importlib.reload(arail.config)
    importlib.reload(app_mod)

    skill_dir = tmp_path / "skills" / "good-id"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("placeholder")

    client = TestClient(app_mod.app)
    r = client.post("/api/skills/good-id", json={
        "content": "---\nid: WRONG-ID\nname: x\ndomain: y\n---\n\n# body\n",
    })
    body = r.json()
    assert body["ok"] is False
    assert "does not match" in body["error"]


def test_api_skills_save_writes_when_valid(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib, arail.config, arail.portal.app as app_mod
    importlib.reload(arail.config)
    importlib.reload(app_mod)

    skill_dir = tmp_path / "skills" / "good"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("placeholder")

    client = TestClient(app_mod.app)
    valid = "---\nid: good\nname: Good Skill\ndomain: testing\n---\n\n# body\n"
    r = client.post("/api/skills/good", json={"content": valid})
    body = r.json()
    assert body["ok"] is True
    assert body["bytes"] == len(valid)
    assert (skill_dir / "SKILL.md").read_text() == valid


# ── API: per-agent loadout round-trip ──────────────────────────────

def test_api_agent_loadout_round_trips_into_agent_md(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib, arail.config, arail.portal.app as app_mod
    importlib.reload(arail.config)
    importlib.reload(app_mod)

    agent_dir = tmp_path / "agents" / "tester"
    agent_dir.mkdir(parents=True)
    (agent_dir / "AGENT.md").write_text(
        "---\nid: tester\nname: Tester\nskills:\n  - skill-a\n---\n\n# body\n"
    )

    client = TestClient(app_mod.app)
    r = client.post("/api/agents/tester/loadout", json={
        "skills": ["skill-x", "skill-y"],
    })
    body = r.json()
    assert body["ok"] is True
    assert body["skills"] == ["skill-x", "skill-y"]

    new_text = (agent_dir / "AGENT.md").read_text()
    assert "skill-x" in new_text
    assert "skill-y" in new_text
    assert "skill-a" not in new_text
    # Body section preserved.
    assert "# body" in new_text


# ── API: skill packs ──────────────────────────────────────────────

def test_api_skill_packs_install_and_remove(monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_PKB", str(tmp_path))
    import importlib, arail.config, arail.portal.app as app_mod
    importlib.reload(arail.config)
    importlib.reload(app_mod)

    client = TestClient(app_mod.app)

    # List packs.
    r = client.get("/api/skills/packs")
    assert r.status_code == 200
    packs_by_id = {p["id"]: p for p in r.json()["packs"]}
    assert "curation-vetting" in packs_by_id
    assert packs_by_id["curation-vetting"]["installed_count"] == 0

    # Install.
    r = client.post("/api/skills/packs/install", json={"pack_id": "curation-vetting"})
    body = r.json()
    assert body["ok"] is True
    assert len(body["installed"]) == 3

    # Remove.
    r = client.post("/api/skills/packs/remove", json={"pack_id": "curation-vetting"})
    body = r.json()
    assert body["ok"] is True
    assert len(body["removed"]) == 3


# ── /docs/<path> route ────────────────────────────────────────────

def test_docs_route_serves_local_markdown():
    """The Learn links rely on this — a regression here = on-page 404s."""
    import arail.portal.app as app_mod
    client = TestClient(app_mod.app)
    r = client.get("/docs/agents-explained.md")
    assert r.status_code == 200
    assert "Agents, explained" in r.text


def test_docs_route_rejects_traversal():
    import arail.portal.app as app_mod
    client = TestClient(app_mod.app)
    r = client.get("/docs/../README.md")
    # FastAPI may rewrite ../ in routing; either 404 or 200 with Not-found body
    # is acceptable as long as we don't leak repo root files.
    assert r.status_code == 404 or "Not found" in r.text


def test_docs_route_404s_on_missing_file():
    import arail.portal.app as app_mod
    client = TestClient(app_mod.app)
    r = client.get("/docs/does-not-exist.md")
    assert r.status_code == 404


def test_docs_route_rejects_non_md_extensions():
    import arail.portal.app as app_mod
    client = TestClient(app_mod.app)
    r = client.get("/docs/agents-explained.txt")
    assert r.status_code == 404
