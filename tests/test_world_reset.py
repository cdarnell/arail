"""WK-5: World = dataset — mounting/switching a World resets the KB's World
layer to only that World, while the user's own ingested content persists.
"""

from __future__ import annotations

import pytest

from arail import world_mount as wm
from tests.world_bundle_builder import make_bundle

A_TERMS = [{"slug": "alpha", "term": "Alpha", "category": "c", "short": "s",
            "definition": "d", "example": "e", "related": [], "source": "https://x"}]
B_TERMS = [{"slug": "beta", "term": "Beta", "category": "c", "short": "s",
            "definition": "d", "example": "e", "related": [], "source": "https://x"}]
CATS = [{"id": "c", "label": "C"}]


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    data = tmp_path / "data"; pkb = tmp_path / "pkb"
    worlds = tmp_path / "worlds"
    data.mkdir(); worlds.mkdir(); (pkb / "sources").mkdir(parents=True)
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data)
    monkeypatch.setattr(wm, "_default_pkb_root", lambda: pkb)
    # keep catalog-adoption out of the real lab/worlds/
    monkeypatch.setattr(wm, "_default_worlds_dir", lambda: worlds)
    return tmp_path, data, pkb


def _wdir(pkb, slug):
    return pkb / "sources" / f"world-{slug}"


def test_switching_worlds_resets_the_dataset(lab):
    tmp, data, pkb = lab
    a = make_bundle(tmp / "a", slug="worlda", terms_list=A_TERMS, categories=CATS)
    b = make_bundle(tmp / "b", slug="worldb", terms_list=B_TERMS, categories=CATS)

    wm.mount(a, data_dir=data, pkb_root=pkb)
    assert _wdir(pkb, "worlda").exists()

    # switch to B (swap) → A's dataset is gone, B's is present
    wm.swap(b, data_dir=data, pkb_root=pkb)
    assert _wdir(pkb, "worldb").exists()
    assert not _wdir(pkb, "worlda").exists(), "old World dataset should be swept on switch"


def test_mounting_sweeps_a_leftover_world(lab):
    tmp, data, pkb = lab
    # Simulate a stale staged world from a previous session.
    stale = _wdir(pkb, "ghost"); (stale / "terms").mkdir(parents=True)
    (stale / "world-ghost.md").write_text("# Ghost")
    a = make_bundle(tmp / "a", slug="worlda", terms_list=A_TERMS, categories=CATS)

    wm.mount(a, data_dir=data, pkb_root=pkb)
    assert not _wdir(pkb, "ghost").exists(), "leftover World should be swept on mount"
    assert _wdir(pkb, "worlda").exists()


def test_user_ingested_content_survives_a_switch(lab):
    tmp, data, pkb = lab
    # The user's own notes/uploads — NOT world data.
    note = pkb / "sources" / "articles"; note.mkdir(parents=True)
    (note / "my-paper.md").write_text("# My own research note")
    research = pkb / "research"; research.mkdir()
    (research / "program.md").write_text("# My program")

    a = make_bundle(tmp / "a", slug="worlda", terms_list=A_TERMS, categories=CATS)
    b = make_bundle(tmp / "b", slug="worldb", terms_list=B_TERMS, categories=CATS)
    wm.mount(a, data_dir=data, pkb_root=pkb)
    wm.swap(b, data_dir=data, pkb_root=pkb)

    assert (note / "my-paper.md").exists(), "user upload must survive a World switch"
    assert (research / "program.md").exists(), "user research must survive a World switch"


def test_sweep_helper_keeps_current_only(lab):
    tmp, data, pkb = lab
    for slug in ("one", "two", "three"):
        (_wdir(pkb, slug) / "terms").mkdir(parents=True)
    (pkb / "sources" / "notes").mkdir()  # non-world content
    removed = wm._sweep_other_worlds(pkb, keep_slug="two")
    assert removed == 2
    assert _wdir(pkb, "two").exists()
    assert not _wdir(pkb, "one").exists() and not _wdir(pkb, "three").exists()
    assert (pkb / "sources" / "notes").exists(), "non-world dir must never be swept"


def test_sweep_never_raises_on_missing_sources(tmp_path):
    # No sources dir at all → no-op, returns 0.
    assert wm._sweep_other_worlds(tmp_path / "nope", keep_slug="x") == 0


# ---------------------------------------------------------------------------
# T9/T10 — `reset pkb`'s scope must drop the dangling world-mount.json and
# re-arm the one-shot World prompt marker (C10, F11). Same sandbox pattern
# as tests/test_reset_paths.py: copy the real reset.sh into a throwaway repo
# root so it can never touch the real lab/.
# ---------------------------------------------------------------------------

import shutil
import subprocess

_REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
_RESET_SH = _REPO_ROOT / "scripts" / "reset.sh"
_BASH = shutil.which("bash")

pytestmark_bash = pytest.mark.skipif(_BASH is None, reason="bash required")


def _make_sandbox(tmp_path):
    fake = tmp_path / "fakerepo"
    (fake / "scripts").mkdir(parents=True)
    shutil.copy2(_RESET_SH, fake / "scripts" / "reset.sh")
    return fake


def _run_reset(fake_repo, mode, env=None):
    return subprocess.run(
        [_BASH, "scripts/reset.sh", mode, "--yes"],
        cwd=fake_repo,
        env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(fake_repo / "home"), **(env or {})},
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytestmark_bash
def test_reset_pkb_drops_dangling_mount_pointer_and_rearms_marker(tmp_path):
    """T9: reset pkb removes world-mount.json and .world-prompt-seen, but
    leaves the rest of lab/data/ untouched."""
    fake = _make_sandbox(tmp_path)
    pkb = fake / "lab" / "pkb"
    (pkb / "sources" / "world-ai").mkdir(parents=True)
    (pkb / "sources" / "world-ai" / "terms.md").write_text("x", encoding="utf-8")

    data = fake / "lab" / "data"
    data.mkdir(parents=True)
    (data / "world-mount.json").write_text("{}", encoding="utf-8")
    (data / ".world-prompt-seen").write_text("", encoding="utf-8")
    (data / "identity.json").write_text("{}", encoding="utf-8")

    res = _run_reset(fake, "pkb")
    assert res.returncode == 0, res.stdout + res.stderr

    assert not pkb.exists(), "reset pkb should still wipe the PKB tree"
    assert not (data / "world-mount.json").exists(), (
        "reset pkb should drop the dangling world-mount.json (F11)"
    )
    assert not (data / ".world-prompt-seen").exists(), (
        "reset pkb should re-arm the one-shot World prompt marker (D1)"
    )
    assert (data / "identity.json").exists(), (
        "reset pkb must not touch unrelated lab/data/ files"
    )


@pytestmark_bash
def test_reset_pkb_idempotent_when_no_mount_files_present(tmp_path):
    """T10 (part 1): reset pkb with neither file present exits 0, no error."""
    fake = _make_sandbox(tmp_path)
    pkb = fake / "lab" / "pkb"
    pkb.mkdir(parents=True)
    (pkb / "note.md").write_text("x", encoding="utf-8")

    res = _run_reset(fake, "pkb")
    assert res.returncode == 0, res.stdout + res.stderr
    assert "error" not in res.stderr.lower()


@pytestmark_bash
def test_reset_models_and_plugins_leave_world_mount_files_untouched(tmp_path):
    """T10 (part 2): unrelated reset scopes are not coupled to the World
    mount pointer / marker — no scope drift."""
    fake = _make_sandbox(tmp_path)
    data = fake / "lab" / "data"
    data.mkdir(parents=True)
    (data / "world-mount.json").write_text("{}", encoding="utf-8")
    (data / ".world-prompt-seen").write_text("", encoding="utf-8")

    for mode in ("models", "plugins"):
        res = _run_reset(fake, mode)
        assert res.returncode == 0, res.stdout + res.stderr

    assert (data / "world-mount.json").exists()
    assert (data / ".world-prompt-seen").exists()
