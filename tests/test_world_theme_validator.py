"""Unit tests for arail.world_theme — the World theme block validator.

Every rejection rule is exercised; the validator must fail CLOSED (None +
reason) on each, and never raise.
"""

from __future__ import annotations

import pytest

from arail.ui_theme import PERSONALITIES, theme_css
from arail.world_theme import (
    WORLD_THEME_SCHEMA,
    build_world_ui_theme,
    contrast_ratio,
    parse_world_theme,
)
from tests.world_bundle_builder import VALID_DARK, valid_theme


# ── acceptance ─────────────────────────────────────────────────────────


@pytest.mark.parametrize("personality", PERSONALITIES)
def test_valid_theme_accepted_for_every_personality(personality):
    spec, reason = parse_world_theme(valid_theme(personality))
    assert reason == ""
    assert spec is not None
    assert spec.personality == personality
    assert spec.dark.accent == VALID_DARK["accent"]
    assert spec.light is None


def test_valid_theme_builds_uitheme_and_emits_css():
    spec, _ = parse_world_theme(valid_theme("playful"))
    theme = build_world_ui_theme(spec, "kawaii", "Kawaii Lab")
    assert theme.id == "world-kawaii"
    css = theme_css(theme)
    assert f"--accent: {VALID_DARK['accent']};" in css
    assert "--radius-m: 14px;" in css  # playful personality scalars
    assert f"--blue: {VALID_DARK['accent2']};" in css  # legacy alias present


def test_hex_normalized_to_lowercase():
    t = valid_theme()
    t["dark"]["accent"] = "#FF6FAE"
    spec, _ = parse_world_theme(t)
    assert spec.dark.accent == "#ff6fae"


def test_light_scheme_accepted_when_valid():
    t = valid_theme()
    t["light"] = dict(VALID_DARK)  # same 12 slots — fine for the schema
    spec, reason = parse_world_theme(t)
    assert spec is not None and spec.light is not None, reason


# ── rejection rules ────────────────────────────────────────────────────


def _rejected(block):
    spec, reason = parse_world_theme(block)
    assert spec is None
    assert reason
    return reason


@pytest.mark.parametrize("block", [None, "pink", 42, ["#ff6fae"], True])
def test_non_dict_rejected(block):
    _rejected(block)


def test_wrong_schema_rejected():
    t = valid_theme()
    t["schema"] = "dac.world-theme/v99"
    assert "schema" in _rejected(t)


def test_missing_schema_rejected():
    t = valid_theme()
    del t["schema"]
    _rejected(t)


def test_unknown_top_level_key_rejected():
    t = valid_theme()
    t["css"] = "body { display:none }"
    assert "unknown keys" in _rejected(t)


def test_unknown_personality_rejected():
    t = valid_theme()
    t["personality"] = "1337-ultra"
    assert "personality" in _rejected(t)


def test_missing_color_slot_rejected():
    t = valid_theme()
    del t["dark"]["accent"]
    assert "missing" in _rejected(t)


def test_extra_color_slot_rejected():
    t = valid_theme()
    t["dark"]["glow"] = "#ffffff"
    assert "unknown keys" in _rejected(t)


@pytest.mark.parametrize("bad", [
    "#fff",                                  # shorthand
    "#gggggg",                               # non-hex
    "red",                                   # named color
    "rgb(0,0,0)",                            # functional
    "#ff6fae ",                              # trailing junk
    "#ff6fae}</style><script>alert(1)</script>",  # CSS/HTML injection
    "url(javascript:alert(1))",
    "expression(alert(1))",
    "var(--bg)",
    "#ff6fae\n#000000",                      # embedded newline
    "＃ff6fae",                          # fullwidth homoglyph '#'
    123456,                                  # non-string
    None,
])
def test_bad_color_values_rejected(bad):
    t = valid_theme()
    t["dark"]["accent"] = bad
    assert "accent" in _rejected(t)


def test_oversized_block_rejected():
    t = valid_theme()
    t["light"] = None
    t["dark"]["bg"] = "#1a0f16"
    big = valid_theme()
    big["personality"] = "playful"
    # Inflate via a legal-shaped but huge structure: many extra keys would be
    # caught first, so inflate inside an allowed slot's value instead.
    big["dark"]["bg"] = "#" + "a" * 8192
    reason = _rejected(big)
    assert "too large" in reason or "bg" in reason  # size cap or hex rule — both closed


def test_bad_light_scheme_rejected_even_with_valid_dark():
    t = valid_theme()
    t["light"] = {**VALID_DARK, "accent": "not-a-color"}
    assert "light" in _rejected(t)


# ── contrast enforcement ───────────────────────────────────────────────


def test_unreadable_text_rejected():
    t = valid_theme()
    t["dark"]["text"] = "#2a1a24"  # nearly the bg — unreadable
    assert "contrast" in _rejected(t)


def test_low_contrast_muted_rejected():
    t = valid_theme()
    t["dark"]["muted"] = "#241521"  # equals surface ≈ bg
    assert "contrast" in _rejected(t)


def test_low_contrast_accent_rejected():
    t = valid_theme()
    t["dark"]["accent"] = "#241521"
    assert "contrast" in _rejected(t)


def test_contrast_ratio_sanity():
    assert contrast_ratio("#000000", "#ffffff") == pytest.approx(21.0, abs=0.1)
    assert contrast_ratio("#ffffff", "#ffffff") == pytest.approx(1.0, abs=0.01)


def test_validator_never_raises_on_garbage():
    class Weird:  # non-serializable object
        pass

    spec, reason = parse_world_theme({"schema": WORLD_THEME_SCHEMA,
                                      "personality": "playful",
                                      "dark": Weird()})
    assert spec is None and reason
