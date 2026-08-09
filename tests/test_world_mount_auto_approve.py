"""QA-6: world_mount.mount() step 3.5 auto-approves the staged World's term
pages into the Compiled KB. This is the integration test for the mount-time
half of the bootstrap sprint — I1/I3-style from ARCHITECTURE.md.
"""

from __future__ import annotations

import json
import pathlib

from arail import compiled_kb as ckb
from arail.world_mount import mount

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"


def _term_slugs(bundle_dir: pathlib.Path) -> set[str]:
    terms = json.loads((bundle_dir / "terms.json").read_text())["terms"]
    return {t["slug"] for t in terms}


def test_mount_auto_approves_all_term_pages(tmp_path, monkeypatch):
    monkeypatch.delenv("ARAIL_AUTO_APPROVE_WORLD_TERMS", raising=False)
    monkeypatch.delenv("ARAIL_APPROVED_ONLY", raising=False)
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    approved = ckb.approved_paths(pkb_root)
    expected = {f"sources/world-physics/terms/{s}.md" for s in _term_slugs(PHYSICS)}
    assert approved == expected
    assert ckb.gate_state(pkb_root)["state"] == "populated"


def test_mount_auto_approval_never_reaches_non_term_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("ARAIL_AUTO_APPROVE_WORLD_TERMS", raising=False)
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    assert all(p.startswith("sources/world-physics/terms/")
               for p in ckb.approved_paths(pkb_root))


def test_mount_auto_approval_respects_env_off(tmp_path, monkeypatch):
    monkeypatch.setenv("ARAIL_AUTO_APPROVE_WORLD_TERMS", "off")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    assert ckb.approved_paths(pkb_root) == set()


def test_mount_auto_approval_respects_sentinel(tmp_path, monkeypatch):
    monkeypatch.delenv("ARAIL_AUTO_APPROVE_WORLD_TERMS", raising=False)
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    sentinel_dir = pkb_root / "compiled" / "kb"
    sentinel_dir.mkdir(parents=True)
    (sentinel_dir / "no-auto-approve").write_text("")

    mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)

    assert ckb.approved_paths(pkb_root) == set()


def test_mount_still_succeeds_if_auto_approve_raises(tmp_path, monkeypatch):
    """Auto-approval is best-effort — an exception must not fail the mount."""
    monkeypatch.delenv("ARAIL_AUTO_APPROVE_WORLD_TERMS", raising=False)
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    import arail.compiled_kb as ckb_mod

    def _boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ckb_mod, "auto_approve_world_terms", _boom)
    record = mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    assert record.world == "physics"
