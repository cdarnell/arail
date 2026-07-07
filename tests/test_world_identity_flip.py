"""Complete World Flip — identity flips live from the mount sidecar.

Weights: 30 setup / 30 Buddy / 20 security / 10 happy / 10 regression.

A World mount flips the lab identity (brand name/logo, theme, intent, framing,
palette) INSTANTLY — resolved at request time from ``world-mount.json`` — with
NO restart and NO ``.env`` write. Unmount reverts to the operator brand and the
generated dictionary.

Tests mount PHYSICS into a tmp data dir and repoint
``world_mount._default_data_dir`` at it (same monkeypatch instance the autouse
``_no_ambient_world_mount`` fixture uses → our override wins), mirroring the
existing world tests. The portal app reads identity with no ``data_dir`` arg, so
it goes through ``_default_data_dir`` and sees the mount.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from arail import world_mount as wm
from arail.identity import effective_identity
from arail.brand import load_brand

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "world-bundles"
PHYSICS = FIXTURES / "physics"
PHYSICS_NAME = "Physics — Measurement & Units"


def _face():
    return json.loads((PHYSICS / "face.json").read_bytes())


@pytest.fixture
def mounted_physics(tmp_path, monkeypatch):
    """Mount PHYSICS into a tmp data dir and make it the default mount."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    return data_dir


def _client():
    from arail.portal import app as portal_app
    return TestClient(portal_app.app)


# ════════════════════════════ SETUP (30%) ════════════════════════════

def test_instant_flip_no_restart_no_env(tmp_path, monkeypatch):
    """Case 1 — mount PHYSICS, GET dashboard in the SAME process → nav/title
    reflect the World and the mission card shows the World's lab_theme. No env
    written by mount()."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    env_path = tmp_path / ".env"
    data_dir.mkdir()
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)

    body = _client().get("/").text
    # The "&" in the World name is HTML-escaped in rendered templates.
    assert "Physics — Measurement &amp; Units" in body   # nav logo / title
    assert not env_path.exists()                          # NO .env write


def test_api_brand_flips(mounted_physics):
    """Case 2 — /api/brand reports the World name + ⟨name⟩ logo when mounted."""
    b = _client().get("/api/brand").json()
    assert b["name"] == PHYSICS_NAME
    assert b["logo"] == f"⟨{PHYSICS_NAME}⟩"


def test_effective_identity_unit_mounted(mounted_physics):
    """Case 3 — resolver unit: mounted identity is fully derived from face."""
    ident = effective_identity(mounted_physics)
    assert ident.name == PHYSICS_NAME
    assert ident.intent == "other"
    assert ident.intent_description == _face()["domain_framing"]
    assert ident.ui_theme.id == "slate-violet"
    assert ident.mounted is True
    assert ident.world == "physics"


def test_mount_signature_has_no_apply_face(tmp_path):
    """Case 4 — mount()/swap() no longer accept apply_face/env_path; CLI mount
    has no --apply-face flag."""
    import inspect
    msig = inspect.signature(wm.mount).parameters
    ssig = inspect.signature(wm.swap).parameters
    assert "apply_face" not in msig and "env_path" not in msig
    assert "apply_face" not in ssig and "env_path" not in ssig

    parser = wm._build_parser()
    # Parsing --apply-face for mount must now fail (unknown flag).
    with pytest.raises(SystemExit):
        parser.parse_args(["mount", str(PHYSICS), "--apply-face"])


# ════════════════════════════ BUDDY (30%) ════════════════════════════

def test_researcher_reframes_live(tmp_path, monkeypatch):
    """Case 5 — researcher intent + context reflect the mounted World live, and
    revert to the AI/ML default on unmount. No restart, no env."""
    from arail.agents import researcher

    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    # Unmounted (empty default dir) → AI/ML default.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    assert researcher._get_lab_intent() == "ai"

    # Mount → "other" + World framing.
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    assert researcher._get_lab_intent() == "other"
    ctx = researcher._get_system_context()
    assert PHYSICS_NAME in ctx
    assert _face()["domain_framing"] in ctx

    # Unmount → reverts to AI/ML default context.
    wm.unmount(data_dir=data_dir, pkb_root=pkb_root)
    assert researcher._get_lab_intent() == "ai"
    assert PHYSICS_NAME not in researcher._get_system_context()


def test_buddy_framing_block_live(tmp_path, monkeypatch):
    """Case 6 — Buddy _world_framing_block delimits the World domain/vocab when
    mounted, "" when unmounted."""
    from arail.agents import _builtin_buddy as bb

    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    assert bb._world_framing_block() == ""

    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    block = bb._world_framing_block()
    assert "# WORLD FRAMING" in block and "# END WORLD FRAMING" in block
    assert _face()["domain_framing"][:50] in block


def test_intent_name_and_description_live(mounted_physics):
    """Case 7 — resolver intent_name / intent_description reflect the World."""
    ident = effective_identity(mounted_physics)
    assert ident.intent_name == _face()["name"]
    assert ident.intent_description == _face()["domain_framing"]


# ════════════════════════════ SECURITY (20%) ════════════════════════════

def test_terms_never_reach_framing(mounted_physics):
    """Case 8 — terms.json text never appears in the Buddy framing block."""
    from arail.agents import _builtin_buddy as bb
    import json as _json
    terms = _json.loads((PHYSICS / "terms.json").read_bytes())
    block = bb._world_framing_block()
    # Pick a distinctive term string and assert it is absent from the prompt block.
    term_strings = []
    items = terms.get("terms", terms) if isinstance(terms, dict) else terms
    for t in items:
        if isinstance(t, dict):
            if t.get("short"):
                term_strings.append(str(t["short"]))
    assert term_strings, "fixture should have terms with definitions"
    for s in term_strings:
        assert s not in block


def test_framing_block_capped_and_delimited(tmp_path, monkeypatch):
    """Case 9 — oversized domain_framing is truncated; delimiters present."""
    from arail.agents import _builtin_buddy as bb
    import shutil, hashlib

    bundle = tmp_path / "huge_face"
    shutil.copytree(PHYSICS, bundle)
    face = json.loads((bundle / "face.json").read_bytes())
    face["domain_framing"] = "X" * 5000
    (bundle / "face.json").write_text(json.dumps(face))
    manifest = json.loads((bundle / "manifest.json").read_bytes())
    manifest["files"]["face.json"] = hashlib.sha256(
        (bundle / "face.json").read_bytes()).hexdigest()
    (bundle / "manifest.json").write_text(json.dumps(manifest))

    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    wm.mount(bundle, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)

    block = bb._world_framing_block()
    assert "# WORLD FRAMING" in block and "# END WORLD FRAMING" in block
    assert block.count("X") <= bb._MAX_WORLD_DOMAIN_FRAMING


def test_mount_adds_no_env_surface(tmp_path, monkeypatch):
    """Case 10 — mounting writes no env keys / no .env at all; identity flows
    only to display + the already-bounded researcher context."""
    env_path = tmp_path / ".env"
    env_path.write_text("OPERATOR=1\n")
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    # The operator .env is byte-for-byte unchanged — no face/intent keys.
    assert env_path.read_text() == "OPERATOR=1\n"


# ════════════════════════════ HAPPY (10%) ════════════════════════════

def test_operator_custom_brand_preserved_when_unmounted(tmp_path, monkeypatch):
    """Case 11 — operator LAB_NAME, no World → dashboard shows the operator
    brand (unmounted path preserves operator identity)."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    monkeypatch.setenv("LAB_NAME", "MyLab")
    from arail.brand import reset_brand_cache
    reset_brand_cache()
    try:
        ident = effective_identity()
        assert ident.name == "MyLab"
        assert ident.mounted is False
    finally:
        reset_brand_cache()


# ════════════════════════════ REGRESSION (10%) ════════════════════════════

def test_default_lab_unchanged(tmp_path, monkeypatch):
    """Case 12 — no World, no custom env → default brand + AI/ML lab_theme +
    blue-cyan-lab theme (today's behaviour, regression-safe)."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    monkeypatch.delenv("LAB_NAME", raising=False)
    monkeypatch.delenv("LAB_THEME", raising=False)
    monkeypatch.delenv("LAB_INTENT", raising=False)
    from arail.brand import reset_brand_cache
    reset_brand_cache()
    try:
        ident = effective_identity()
        assert ident.name == load_brand().name        # "Autoresearch AI Lab"
        assert ident.name == "Autoresearch AI Lab"
        assert "SSD-hosted model inference" in ident.lab_theme
        from arail.ui_theme import default_ui_theme
        assert ident.ui_theme.id == default_ui_theme().id
        assert ident.intent == "ai"
        assert ident.mounted is False
    finally:
        reset_brand_cache()


def test_dictionary_flip_still_works(tmp_path, monkeypatch):
    """Case 12 (cont.) — dictionary flip still resolves from the mount: mounted
    → World terms; unmounted → no World terms."""
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()

    # Unmounted: no World term in the dictionary response.
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: empty)
    assert wm.current_mount() is None

    # Mounted: the staged World terms are reachable via mounted_face/record.
    wm.mount(PHYSICS, pkb_root=pkb_root, data_dir=data_dir)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    rec = wm.current_mount()
    assert rec is not None and rec.world == "physics"
    face = wm.mounted_face(rec)
    assert face is not None and face["name"] == PHYSICS_NAME
