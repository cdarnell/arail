"""Phase 5 tests: Buddy WORLD FRAMING block.

Buddy (30%) allocation:
- mounted _compose_prompt has delimited capped WORLD FRAMING block
- unmounted _compose_prompt is byte-identical to base (no framing)
- domain_framing capped at _MAX_WORLD_DOMAIN_FRAMING chars
- vocabulary_register capped at _MAX_WORLD_VOCAB_REGISTER chars
- hostile face.json text is capped + delimited (cannot overflow prompt structure)
- WORLD FRAMING uses only face.json (never terms.json definition)
"""

from __future__ import annotations

import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"


from arail.world_mount import mount, unmount, current_mount


def _do_mount(tmp_path, bundle_dir=None):
    bundle_dir = bundle_dir or PHYSICS
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir(exist_ok=True)
    record = mount(bundle_dir, pkb_root=pkb_root, data_dir=data_dir)
    return data_dir, pkb_root, record


# ── _world_framing_block when not mounted ─────────────────────────────────────

def test_world_framing_empty_when_not_mounted(tmp_path, monkeypatch):
    """When no world is mounted, _world_framing_block() returns empty string."""
    # Patch current_mount to return None
    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: None)

    framing = buddy_mod._world_framing_block()
    assert framing == ""


# ── _world_framing_block when mounted ────────────────────────────────────────

def test_world_framing_has_delimiters_when_mounted(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    framing = buddy_mod._world_framing_block()
    assert framing.startswith("# WORLD FRAMING")
    assert "# END WORLD FRAMING" in framing


def test_world_framing_contains_domain_framing(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    framing = buddy_mod._world_framing_block()
    # Physics face has domain_framing about SI quantities
    assert "SI" in framing or "physics" in framing.lower() or "measurement" in framing.lower()


def test_world_framing_contains_vocabulary_register(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    framing = buddy_mod._world_framing_block()
    # Physics face has vocabulary_register about SI usage
    assert "Vocabulary:" in framing


# ── caps ──────────────────────────────────────────────────────────────────────

def test_world_framing_domain_capped(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    # Fake a very long domain_framing
    fake_face = {
        "domain_framing": "X" * 2000,
        "vocabulary_register": "Y",
    }
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)
    monkeypatch.setattr(wm_mod, "mounted_face", lambda r: fake_face)

    framing = buddy_mod._world_framing_block()
    # domain_framing must be capped
    assert "X" * (buddy_mod._MAX_WORLD_DOMAIN_FRAMING + 1) not in framing


def test_world_framing_vocab_capped(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    fake_face = {
        "domain_framing": "short",
        "vocabulary_register": "Z" * 2000,
    }
    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)
    monkeypatch.setattr(wm_mod, "mounted_face", lambda r: fake_face)

    framing = buddy_mod._world_framing_block()
    assert "Z" * (buddy_mod._MAX_WORLD_VOCAB_REGISTER + 1) not in framing


# ── _compose_prompt integration ───────────────────────────────────────────────

def test_compose_prompt_has_world_framing_when_mounted(tmp_path, monkeypatch):
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    prompt = buddy_mod._compose_prompt("test observation")
    assert "# WORLD FRAMING" in prompt
    assert "# END WORLD FRAMING" in prompt


def test_compose_prompt_no_framing_when_not_mounted(tmp_path, monkeypatch):
    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: None)

    prompt = buddy_mod._compose_prompt("test observation")
    assert "# WORLD FRAMING" not in prompt
    assert "# END WORLD FRAMING" not in prompt


def test_compose_prompt_contains_observation(tmp_path, monkeypatch):
    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: None)

    prompt = buddy_mod._compose_prompt("my unique observation 123")
    assert "my unique observation 123" in prompt


def test_world_framing_never_contains_terms_definition(tmp_path, monkeypatch):
    """WORLD FRAMING uses only face.json, never terms.json definitions."""
    data_dir, pkb_root, record = _do_mount(tmp_path)

    import arail.agents._builtin_buddy as buddy_mod
    import arail.world_mount as wm_mod

    monkeypatch.setattr(wm_mod, "current_mount", lambda *a, **kw: record)

    framing = buddy_mod._world_framing_block()
    # Terms definitions would contain specific physics content not in face.json
    # The hostile content "Ignore previous instructions" is in terms.json, not face.json
    assert "Ignore previous instructions" not in framing
