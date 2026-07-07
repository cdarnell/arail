"""Adversarial mount-integration tests for World-shipped themes.

Threat model: a World author controls face.json entirely and can SEAL any
content (the builder re-computes hashes after overrides — seal-valid hostile
bundles). Invariants under attack:

1. a hostile theme never blocks the mount (theme failure ≠ mount failure);
2. the portal renders with the FALLBACK theme (palette_hint → default);
3. no payload byte from the hostile theme reaches any HTML response;
4. a valid theme actually drives the injected token block end-to-end.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest
from fastapi.testclient import TestClient

import arail.world_mount as wm
from arail.portal import app as portal_app
from tests.world_bundle_builder import VALID_DARK, make_bundle, valid_theme

MARK = 'id="ui-theme-vars"'


def _client():
    return TestClient(portal_app.app)


def _theme_block(body: str) -> str:
    m = re.search(r'<style id="ui-theme-vars">(.*?)</style>', body, re.S)
    assert m, "no injected theme block"
    return m.group(1)


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    pkb_root = tmp_path / "pkb"
    data_dir.mkdir()
    monkeypatch.setattr(wm, "_default_data_dir", lambda: data_dir)
    return tmp_path, data_dir, pkb_root


def _mount(bundle, data_dir, pkb_root):
    return wm.mount(bundle, pkb_root=pkb_root, data_dir=data_dir)


# ── happy path: a valid theme drives the page ──────────────────────────


def test_valid_world_theme_recolors_portal(lab):
    tmp, data_dir, pkb = lab
    bundle = make_bundle(tmp, slug="kawaii", display_name="Kawaii Lab",
                         face_overrides={"theme": valid_theme("playful")})
    _mount(bundle, data_dir, pkb)
    block = _theme_block(_client().get("/skills").text)
    assert f"--accent: {VALID_DARK['accent']};" in block
    assert f"--bg: {VALID_DARK['bg']};" in block
    assert "--radius-m: 14px;" in block  # playful scalars flowed through
    wm.unmount(data_dir=data_dir)
    block = _theme_block(_client().get("/skills").text)
    assert f"--accent: {VALID_DARK['accent']};" not in block  # reverted


def test_hacker_personality_theme_flows(lab):
    """The shipped AI/ML world pattern: legacy terminal palette + hacker
    personality, delivered as world data."""
    tmp, data_dir, pkb = lab
    hacker_dark = {
        "bg": "#0a0a0f", "surface": "#0f1118", "surface2": "#151821",
        "border": "#1e2230", "text": "#c8cdd8", "muted": "#78839a",
        "accent": "#00ff41", "accent2": "#00d4ff", "positive": "#00ff41",
        "warn": "#ffb000", "danger": "#ff3355", "info": "#b48eff",
    }
    theme = {"schema": "dac.world-theme/v1", "personality": "hacker",
             "dark": hacker_dark, "light": None}
    bundle = make_bundle(tmp, slug="ai-fundamentals",
                         display_name="AI Fundamentals",
                         face_overrides={"theme": theme})
    _mount(bundle, data_dir, pkb)
    block = _theme_block(_client().get("/skills").text)
    assert "--accent: #00ff41;" in block
    assert "--motif-scanline-alpha: 0.03;" in block  # hacker motif
    assert "--heading-font: var(--font-mono);" in block


# ── attacks ────────────────────────────────────────────────────────────

# Every payload carries the unique marker zzEVILzz so leak detection can't
# false-positive on legitimate page CSS/JS (e.g. real display:none rules).
INJECTION_THEMES = [
    # CSS/HTML breakout in a color slot
    {**valid_theme(), "dark": {**VALID_DARK,
        "accent": '#000000}</style><script>zzEVILzz(1)</script>'}},
    # url()/expression() smuggling
    {**valid_theme(), "dark": {**VALID_DARK, "bg": "url(javascript:zzEVILzz(1))"}},
    {**valid_theme(), "dark": {**VALID_DARK, "bg": "expression(zzEVILzz(1))"}},
    # var() indirection
    {**valid_theme(), "dark": {**VALID_DARK, "text": "var(--zzEVILzz)"}},
    # personality injection
    {**valid_theme(), "personality": "playful}</style><script>zzEVILzz()</script>"},
    # extra key smuggling raw CSS
    {**valid_theme(), "raw_css": "body{background:url(zzEVILzz)}"},
    # wrong types
    "zzEVILzz-just-a-string",
    ["#ff0000"] * 12,
    12345,
]


@pytest.mark.parametrize("hostile", INJECTION_THEMES)
def test_hostile_theme_mounts_but_falls_back_and_leaks_nothing(lab, hostile):
    tmp, data_dir, pkb = lab
    bundle = make_bundle(tmp, slug="hostile", display_name="Hostile World",
                         face_overrides={"theme": hostile})
    record = _mount(bundle, data_dir, pkb)  # mount must SUCCEED
    assert record is not None

    body = _client().get("/skills").text
    block = _theme_block(body)
    # Fallback: palette_hint slate-violet (the builder default) — a real preset.
    assert "--bg: #0d1018;" in block
    assert "zzEVILzz" not in body, "hostile theme payload leaked into HTML"
    wm.unmount(data_dir=data_dir)


def test_giant_theme_block_rejected_cheaply(lab):
    tmp, data_dir, pkb = lab
    huge = valid_theme()
    huge["dark"] = {**VALID_DARK, "bg": "#" + "a" * 1_000_000}
    bundle = make_bundle(tmp, slug="bloat", display_name="Bloat World",
                         face_overrides={"theme": huge})
    _mount(bundle, data_dir, pkb)
    block = _theme_block(_client().get("/skills").text)
    assert "--bg: #0d1018;" in block  # fallback preset
    assert "aaaaaaaaaa" not in block


def test_unreadable_palette_rejected_to_fallback(lab):
    tmp, data_dir, pkb = lab
    murk = valid_theme()
    murk["dark"] = {**VALID_DARK, "text": "#241521"}  # text ≈ bg
    bundle = make_bundle(tmp, slug="murky", display_name="Murky World",
                         face_overrides={"theme": murk})
    _mount(bundle, data_dir, pkb)
    block = _theme_block(_client().get("/skills").text)
    assert "--bg: #0d1018;" in block  # readable preset, not the murk
    assert "--text: #241521;" not in block


def test_theme_plus_bad_palette_hint_still_defaults(lab):
    """Both hint and theme hostile → default preset, no leak."""
    tmp, data_dir, pkb = lab
    bundle = make_bundle(
        tmp, slug="doubly", display_name="Doubly Hostile",
        face_overrides={
            "palette_hint": '</style><script>alert(2)</script>',
            "theme": {"schema": "dac.world-theme/v1", "personality": "nope",
                      "dark": VALID_DARK, "light": None},
        },
    )
    _mount(bundle, data_dir, pkb)
    body = _client().get("/skills").text
    block = _theme_block(body)
    assert "--bg: #0a0a0f;" in block  # blue-cyan-lab default
    assert "alert(2)" not in body
