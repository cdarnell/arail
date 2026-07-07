"""World-supplied UI theme validation — ``dac.world-theme/v1``.

A World's ``face.json`` may carry an optional top-level ``theme`` block:

    "theme": {
      "schema": "dac.world-theme/v1",
      "personality": "playful",
      "dark":  { ...exactly 12 hex slots... },
      "light": null
    }

This module is the ONLY path from World data to a UI theme, and it is
paranoid by design (the ``skills_loader`` containment posture): the block is
untrusted input even though face.json is seal-verified — a World author can
seal anything. ``parse_world_theme`` fails CLOSED to ``None`` on any
violation, and the caller falls back to ``palette_hint`` → default, so a bad
theme never blocks a mount and never reaches CSS.

XSS-safety by construction is preserved: the only World-controlled values
that survive validation are ``#rrggbb`` strings matched by a full-string
regex and a personality id matched against the closed ``PERSONALITIES``
tuple — raw face.json text can never be interpolated into the emitted
``<style>`` block.

Readability is enforced, not assumed: WCAG relative-luminance contrast
gates (text:bg >= 4.5, muted:bg >= 3.0, accent:bg >= 3.0) reject palettes
that would render the portal unreadable.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from arail.ui_theme import PERSONALITIES, ThemeColors, UITheme

_log = logging.getLogger(__name__)

WORLD_THEME_SCHEMA = "dac.world-theme/v1"

# Full-string match only — no prefixes, suffixes, or shorthand forms.
_HEX_RE = re.compile(r"#[0-9a-fA-F]{6}\Z")

_COLOR_SLOTS: tuple[str, ...] = (
    "bg", "surface", "surface2", "border", "text", "muted",
    "accent", "accent2", "positive", "warn", "danger", "info",
)
_ALLOWED_TOP_KEYS = {"schema", "personality", "dark", "light"}

# Serialized size cap — a theme block is ~600 bytes; anything near this cap
# is hostile or broken.
_MAX_THEME_JSON_BYTES = 4096

_CONTRAST_RULES: tuple[tuple[str, str, float], ...] = (
    ("text", "bg", 4.5),
    ("muted", "bg", 3.0),
    ("accent", "bg", 3.0),
)


@dataclass(frozen=True)
class WorldThemeSpec:
    personality: str
    dark: ThemeColors
    light: Optional[ThemeColors] = None


def _rel_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of an #rrggbb color."""
    channels = []
    for i in (1, 3, 5):
        c = int(hex_color[i:i + 2], 16) / 255.0
        channels.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    la, lb = _rel_luminance(a), _rel_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _parse_scheme(raw: object) -> tuple[Optional[ThemeColors], str]:
    """One scheme block → ThemeColors, or (None, reason)."""
    if not isinstance(raw, dict):
        return None, "scheme block is not an object"
    keys = set(raw.keys())
    missing = [s for s in _COLOR_SLOTS if s not in keys]
    if missing:
        return None, f"missing color slots: {', '.join(missing)}"
    extra = keys - set(_COLOR_SLOTS)
    if extra:
        return None, f"unknown keys: {', '.join(sorted(extra))}"
    for slot in _COLOR_SLOTS:
        value = raw[slot]
        if not isinstance(value, str) or not _HEX_RE.match(value):
            return None, f"slot {slot!r} is not a #rrggbb color"
    colors = ThemeColors(**{slot: raw[slot].lower() for slot in _COLOR_SLOTS})
    for fg, bg, minimum in _CONTRAST_RULES:
        ratio = contrast_ratio(getattr(colors, fg), getattr(colors, bg))
        if ratio < minimum:
            return None, (
                f"contrast {fg}:{bg} is {ratio:.2f}, below the required {minimum:.1f}"
            )
    return colors, ""


def parse_world_theme(raw: object, world: str = "?") -> tuple[Optional[WorldThemeSpec], str]:
    """Validate a face.json ``theme`` block.

    Returns ``(spec, "")`` on success or ``(None, reason)`` on any violation.
    Never raises — this sits on the request path via effective_identity().
    """
    try:
        if raw is None:
            return None, "no theme block"
        if not isinstance(raw, dict):
            return None, "theme is not an object"
        try:
            size = len(json.dumps(raw))
        except (TypeError, ValueError):
            return None, "theme is not JSON-serializable"
        if size > _MAX_THEME_JSON_BYTES:
            return None, f"theme block too large ({size} bytes)"
        extra = set(raw.keys()) - _ALLOWED_TOP_KEYS
        if extra:
            return None, f"unknown keys: {', '.join(sorted(extra))}"
        if raw.get("schema") != WORLD_THEME_SCHEMA:
            return None, f"unsupported schema {raw.get('schema')!r}"
        personality = raw.get("personality")
        if personality not in PERSONALITIES:
            return None, f"unknown personality {personality!r}"
        dark, reason = _parse_scheme(raw.get("dark"))
        if dark is None:
            return None, f"dark scheme: {reason}"
        light: Optional[ThemeColors] = None
        if raw.get("light") is not None:
            light, reason = _parse_scheme(raw.get("light"))
            if light is None:
                return None, f"light scheme: {reason}"
        return WorldThemeSpec(personality=personality, dark=dark, light=light), ""
    except Exception as e:  # noqa: BLE001 — fail closed, never into a handler
        _log.warning("world_theme[%s]: validation crashed, rejecting: %s", world, e)
        return None, "validation error"


def build_world_ui_theme(spec: WorldThemeSpec, world: str, display_name: str) -> UITheme:
    """A UITheme from a validated spec. Derived neutrals (text_strong etc.)
    come from ``ui_theme._derive`` mix math — never from World input."""
    return UITheme(
        id=f"world-{world}",
        name=f"{display_name} theme",
        description=f"Theme shipped by the {display_name} World.",
        env_value=f"world-{world}",
        personality=spec.personality,
        dark=spec.dark,
        light=spec.light,
    )
