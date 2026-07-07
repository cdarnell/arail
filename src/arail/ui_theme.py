"""UI theme system for the local portal (design system v2).

The portal stays CSS-variable driven. A theme is 12 semantic color slots per
scheme plus a *personality* ("technical" | "scholarly" | "playful") that maps
to shape/motif/motion scalars through the frozen ``_PERSONALITY`` table.
``theme_css()`` emits the ``:root`` override block the portal middleware
injects into every page; ``style.css`` carries matching real defaults, so
pages render correctly even without the injection.

Scheme-readiness: color slots live in a ``ThemeColors`` per scheme. Only
``dark`` ships today; when a light scheme lands, themes grow a ``light``
``ThemeColors`` and ``theme_css(theme, scheme="light")`` emits it under a
scheme selector — token names are scheme-neutral by design.

Legacy tokens (``--green``/``--blue``/``--amber``/``--red``/``--purple`` and
friends) are still emitted during the v2 migration because ~200K of per-page
CSS references them; they alias onto the semantic slots and are dropped once
the per-surface sweep and the token-compliance lint report zero consumers.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

PERSONALITIES: tuple[str, ...] = ("technical", "scholarly", "playful", "hacker")


@dataclass(frozen=True)
class ThemeColors:
    """The 12 semantic color slots of one scheme. Hex ``#rrggbb`` only —
    this is also the exact shape a World's face.json ``theme.dark`` block
    is validated into, so nothing outside these slots is theme-supplied."""

    bg: str
    surface: str
    surface2: str
    border: str
    text: str
    muted: str
    accent: str
    accent2: str
    positive: str
    warn: str
    danger: str
    info: str


@dataclass(frozen=True)
class UITheme:
    id: str
    name: str
    description: str
    env_value: str
    personality: str
    dark: ThemeColors
    light: ThemeColors | None = None
    # Exact values for derived neutrals (text_strong / border_strong /
    # positive_dim), keyed by slot name. Built-in presets pin these to their
    # historical values; themes built from World data leave it empty and get
    # ``_derive()`` results instead.
    derived: dict[str, str] = field(default_factory=dict)

    # Back-compat surface for /api/system/theme and the world switcher.
    @property
    def accent(self) -> str:
        return self.dark.accent

    @property
    def preview_start(self) -> str:
        return self.dark.bg

    @property
    def preview_end(self) -> str:
        return self.dark.accent


def _mix(a: str, b: str, ratio: float) -> str:
    """Blend hex ``a`` toward hex ``b`` by ``ratio`` (0..1)."""
    ar, ag, ab_ = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg_, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        round(ar + (br - ar) * ratio),
        round(ag + (bg_ - ag) * ratio),
        round(ab_ + (bb - ab_) * ratio),
    )


def _derive(colors: ThemeColors, pinned: dict[str, str]) -> dict[str, str]:
    """Derived neutrals for slots not carried by ThemeColors.

    Dark-scheme math (mix toward text/black); revisit the mix targets when a
    light scheme ships.
    """
    return {
        "surface3": pinned.get("surface3", _mix(colors.surface2, colors.text, 0.06)),
        "border_strong": pinned.get("border_strong", _mix(colors.border, colors.text, 0.10)),
        "text_strong": pinned.get("text_strong", _mix(colors.text, "#ffffff", 0.55)),
        "positive_dim": pinned.get("positive_dim", _mix(colors.positive, "#000000", 0.20)),
    }


# Personality → shape/motif/motion scalars. Frozen, closed table: a World's
# face.json can only *select* a personality, never supply scalar values, so
# nothing here is reachable by untrusted input.
_PERSONALITY: dict[str, dict[str, str]] = {
    "technical": {
        "--radius-s": "4px",
        "--radius-m": "6px",
        "--radius-l": "10px",
        "--radius-pill": "999px",
        "--motif-scanline-alpha": "0.03",
        "--glow-blur": "8px",
        "--glow-blur-far": "20px",
        "--glow-alpha": "0.30",
        "--glow-alpha-far": "0.10",
        "--dur-1": "100ms",
        "--dur-2": "170ms",
        "--dur-3": "280ms",
        "--ease-accent": "cubic-bezier(0.2, 0, 0, 1)",
        "--heading-font": "var(--font-mono)",
        "--label-transform": "uppercase",
        "--label-tracking": "0.08em",
        "--rail-from": "var(--accent)",
        "--rail-to": "var(--accent2)",
    },
    "scholarly": {
        "--radius-s": "6px",
        "--radius-m": "10px",
        "--radius-l": "14px",
        "--radius-pill": "999px",
        "--motif-scanline-alpha": "0",
        "--glow-blur": "6px",
        "--glow-blur-far": "16px",
        "--glow-alpha": "0.12",
        "--glow-alpha-far": "0.05",
        "--dur-1": "120ms",
        "--dur-2": "200ms",
        "--dur-3": "320ms",
        "--ease-accent": "cubic-bezier(0.2, 0, 0, 1)",
        "--heading-font": "var(--font-sans)",
        "--label-transform": "none",
        "--label-tracking": "0.01em",
        "--rail-from": "var(--accent2)",
        "--rail-to": "var(--accent)",
    },
    "playful": {
        "--radius-s": "10px",
        "--radius-m": "14px",
        "--radius-l": "20px",
        "--radius-pill": "999px",
        "--motif-scanline-alpha": "0",
        "--glow-blur": "14px",
        "--glow-blur-far": "28px",
        "--glow-alpha": "0.32",
        "--glow-alpha-far": "0.12",
        "--dur-1": "140ms",
        "--dur-2": "230ms",
        "--dur-3": "380ms",
        "--ease-accent": "cubic-bezier(0.34, 1.56, 0.64, 1)",
        "--heading-font": "var(--font-sans)",
        "--label-transform": "none",
        "--label-tracking": "0.02em",
        "--rail-from": "var(--accent)",
        "--rail-to": "var(--accent2)",
    },
    # The legacy 1337 terminal profile, preserved verbatim as a selectable
    # World personality (the shipped AI/ML world wears it). Unlike
    # "technical", these values never get retuned by design-system passes.
    "hacker": {
        "--radius-s": "4px",
        "--radius-m": "6px",
        "--radius-l": "10px",
        "--radius-pill": "999px",
        "--motif-scanline-alpha": "0.03",
        "--glow-blur": "8px",
        "--glow-blur-far": "20px",
        "--glow-alpha": "0.30",
        "--glow-alpha-far": "0.10",
        "--dur-1": "100ms",
        "--dur-2": "170ms",
        "--dur-3": "280ms",
        "--ease-accent": "cubic-bezier(0.2, 0, 0, 1)",
        "--heading-font": "var(--font-mono)",
        "--label-transform": "uppercase",
        "--label-tracking": "0.08em",
        "--rail-from": "var(--positive)",
        "--rail-to": "var(--accent2)",
    },
}


_THEMES: tuple[UITheme, ...] = (
    UITheme(
        id="blue-cyan-lab",
        name="Blue Cyan Lab",
        description="The default Arail look: crisp cyan accents over a deep navy operator surface.",
        env_value="blue-cyan-lab",
        personality="technical",
        dark=ThemeColors(
            bg="#0a0a0f",
            surface="#0f1118",
            surface2="#151821",
            border="#1e2230",
            text="#c8cdd8",
            muted="#78839a",
            accent="#00d4ff",
            accent2="#00d4ff",
            positive="#00ff41",
            warn="#ffb000",
            danger="#ff3355",
            info="#b48eff",
        ),
        derived={
            "border_strong": "#2a3040",
            "text_strong": "#e8ecf4",
            "positive_dim": "#00cc33",
        },
    ),
    UITheme(
        id="emerald-terminal",
        name="Emerald Terminal",
        description="A retro terminal profile with richer greens and dimmer blues.",
        env_value="emerald-terminal",
        personality="technical",
        dark=ThemeColors(
            bg="#070d09",
            surface="#0d1510",
            surface2="#132018",
            border="#1a3124",
            text="#cad8d0",
            muted="#7c9386",
            accent="#24d26f",
            accent2="#67d8c5",
            positive="#24d26f",
            warn="#d9b957",
            danger="#ff5f72",
            info="#8fb4ff",
        ),
        derived={
            "border_strong": "#245138",
            "text_strong": "#ecf7ef",
            "positive_dim": "#15914c",
        },
    ),
    UITheme(
        id="night-amber",
        name="Night Amber",
        description="A reading-heavy profile with warm amber emphasis on a blue-black base.",
        env_value="night-amber",
        personality="scholarly",
        dark=ThemeColors(
            bg="#0a0d14",
            surface="#111722",
            surface2="#182030",
            border="#263043",
            text="#d2d7e2",
            muted="#8e96a8",
            accent="#ffb454",
            accent2="#66c7ff",
            positive="#6fd08c",
            warn="#ffb454",
            danger="#ff6b6b",
            info="#d0a8ff",
        ),
        derived={
            "border_strong": "#34445d",
            "text_strong": "#f0f4fb",
            "positive_dim": "#49a66a",
        },
    ),
    UITheme(
        id="slate-violet",
        name="Slate Violet",
        description="A softer personal-lab palette with slate neutrals and cool violet highlights.",
        env_value="slate-violet",
        personality="scholarly",
        dark=ThemeColors(
            bg="#0d1018",
            surface="#141926",
            surface2="#1b2233",
            border="#283149",
            text="#d4d7e4",
            muted="#8d94aa",
            accent="#9e8cff",
            accent2="#7fc8ff",
            positive="#7bd8b5",
            warn="#f3b56a",
            danger="#ff748f",
            info="#9e8cff",
        ),
        derived={
            "border_strong": "#364364",
            "text_strong": "#f2f4fb",
            "positive_dim": "#4aa788",
        },
    ),
)


def list_ui_themes() -> list[UITheme]:
    return list(_THEMES)


def default_ui_theme() -> UITheme:
    return _THEMES[0]


def load_ui_theme(theme_id: str | None = None) -> UITheme:
    requested = (theme_id or os.getenv("LAB_UI_THEME") or default_ui_theme().id).strip().lower()
    for theme in _THEMES:
        if theme.id == requested or theme.env_value == requested:
            return theme
    return default_ui_theme()


def _hex_to_rgb_channels(value: str) -> str | None:
    """``#00d4ff`` → ``0, 212, 255`` (the channels for ``rgba(var(--x-rgb), a)``).

    Returns None for non-hex tokens (var() refs, scalar strings, etc.)."""
    v = value.strip()
    if len(v) == 7 and v[0] == "#":
        try:
            r, g, b = int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16)
            return f"{r}, {g}, {b}"
        except ValueError:
            return None
    return None


# Semantic token name ← ThemeColors slot. --muted is emitted under both its
# legacy name and --text-muted so swept and unswept CSS agree.
_SLOT_TOKENS: tuple[tuple[str, str], ...] = (
    ("--bg", "bg"),
    ("--surface", "surface"),
    ("--surface2", "surface2"),
    ("--border", "border"),
    ("--text", "text"),
    ("--text-muted", "muted"),
    ("--muted", "muted"),
    ("--accent", "accent"),
    ("--accent2", "accent2"),
    ("--positive", "positive"),
    ("--warn", "warn"),
    ("--danger", "danger"),
    ("--info", "info"),
)

# Legacy accent aliases (v1 token names) ← semantic slot / derived key.
_LEGACY_TOKENS: tuple[tuple[str, str], ...] = (
    ("--green", "positive"),
    ("--blue", "accent2"),
    ("--amber", "warn"),
    ("--red", "danger"),
    ("--purple", "info"),
)
_DERIVED_TOKENS: tuple[tuple[str, str], ...] = (
    ("--surface3", "surface3"),
    ("--border-strong", "border_strong"),
    ("--text-strong", "text_strong"),
    ("--positive-dim", "positive_dim"),
    # legacy names for the same values
    ("--border-hi", "border_strong"),
    ("--text-hi", "text_strong"),
    ("--green-dim", "positive_dim"),
)


def theme_css(theme: UITheme, scheme: str = "dark") -> str:
    """The ``:root`` override block for one theme.

    Emits hex color tokens (semantic + legacy aliases) with ``-rgb`` channel
    companions, plus the personality scalars. Glow strings and alpha tiers are
    composed in style.css from these primitives, so they are not emitted here.
    """
    colors = theme.dark if scheme == "dark" or theme.light is None else theme.light
    derived = _derive(colors, theme.derived)
    personality = _PERSONALITY.get(theme.personality, _PERSONALITY["technical"])

    lines = [":root {"]

    def emit(key: str, value: str) -> None:
        lines.append(f"  {key}: {value};")
        # RGB-channel companion for every hex token so style.css can do
        # rgba(var(--x-rgb), a) and alpha accents repaint with the theme.
        channels = _hex_to_rgb_channels(value)
        if channels is not None:
            lines.append(f"  {key}-rgb: {channels};")

    for token, slot in _SLOT_TOKENS:
        emit(token, getattr(colors, slot))
    for token, key in _DERIVED_TOKENS:
        emit(token, derived[key])
    for token, slot in _LEGACY_TOKENS:
        emit(token, getattr(colors, slot))
    for token, value in personality.items():
        lines.append(f"  {token}: {value};")

    lines.append("}")
    return "\n".join(lines)
