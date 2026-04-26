"""UI theme presets for the local portal.

The portal stays CSS-variable driven. A theme is just a named set of root
tokens that can be swapped without restyling individual components.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class UITheme:
    id: str
    name: str
    description: str
    preview_start: str
    preview_end: str
    accent: str
    env_value: str
    tokens: dict[str, str]


_THEMES: tuple[UITheme, ...] = (
    UITheme(
        id="blue-cyan-lab",
        name="Blue Cyan Lab",
        description="The default Arail look: crisp cyan accents over a deep navy operator surface.",
        preview_start="#08111b",
        preview_end="#00d4ff",
        accent="#00d4ff",
        env_value="blue-cyan-lab",
        tokens={
            "--bg": "#0a0a0f",
            "--surface": "#0f1118",
            "--surface2": "#151821",
            "--border": "#1e2230",
            "--border-hi": "#2a3040",
            "--text": "#c8cdd8",
            "--text-hi": "#e8ecf4",
            "--muted": "#78839a",
            "--green": "#00ff41",
            "--green-dim": "#00cc33",
            "--blue": "#00d4ff",
            "--amber": "#ffb000",
            "--red": "#ff3355",
            "--purple": "#b48eff",
            "--glow-green": "0 0 8px rgba(0,255,65,.3), 0 0 20px rgba(0,255,65,.1)",
            "--glow-blue": "0 0 8px rgba(0,212,255,.3), 0 0 20px rgba(0,212,255,.1)",
            "--glow-amber": "0 0 8px rgba(255,176,0,.3), 0 0 20px rgba(255,176,0,.1)",
            "--glow-red": "0 0 8px rgba(255,51,85,.3)",
        },
    ),
    UITheme(
        id="emerald-terminal",
        name="Emerald Terminal",
        description="A retro terminal profile with richer greens and dimmer blues.",
        preview_start="#08110a",
        preview_end="#24d26f",
        accent="#24d26f",
        env_value="emerald-terminal",
        tokens={
            "--bg": "#070d09",
            "--surface": "#0d1510",
            "--surface2": "#132018",
            "--border": "#1a3124",
            "--border-hi": "#245138",
            "--text": "#cad8d0",
            "--text-hi": "#ecf7ef",
            "--muted": "#7c9386",
            "--green": "#24d26f",
            "--green-dim": "#15914c",
            "--blue": "#67d8c5",
            "--amber": "#d9b957",
            "--red": "#ff5f72",
            "--purple": "#8fb4ff",
            "--glow-green": "0 0 8px rgba(36,210,111,.28), 0 0 20px rgba(36,210,111,.11)",
            "--glow-blue": "0 0 8px rgba(103,216,197,.24), 0 0 20px rgba(103,216,197,.1)",
            "--glow-amber": "0 0 8px rgba(217,185,87,.24), 0 0 20px rgba(217,185,87,.1)",
            "--glow-red": "0 0 8px rgba(255,95,114,.28)",
        },
    ),
    UITheme(
        id="night-amber",
        name="Night Amber",
        description="A reading-heavy profile with warm amber emphasis on a blue-black base.",
        preview_start="#0a0d14",
        preview_end="#ffb454",
        accent="#ffb454",
        env_value="night-amber",
        tokens={
            "--bg": "#0a0d14",
            "--surface": "#111722",
            "--surface2": "#182030",
            "--border": "#263043",
            "--border-hi": "#34445d",
            "--text": "#d2d7e2",
            "--text-hi": "#f0f4fb",
            "--muted": "#8e96a8",
            "--green": "#6fd08c",
            "--green-dim": "#49a66a",
            "--blue": "#66c7ff",
            "--amber": "#ffb454",
            "--red": "#ff6b6b",
            "--purple": "#d0a8ff",
            "--glow-green": "0 0 8px rgba(111,208,140,.24), 0 0 20px rgba(111,208,140,.1)",
            "--glow-blue": "0 0 8px rgba(102,199,255,.25), 0 0 20px rgba(102,199,255,.1)",
            "--glow-amber": "0 0 8px rgba(255,180,84,.3), 0 0 20px rgba(255,180,84,.12)",
            "--glow-red": "0 0 8px rgba(255,107,107,.26)",
        },
    ),
    UITheme(
        id="slate-violet",
        name="Slate Violet",
        description="A softer personal-lab palette with slate neutrals and cool violet highlights.",
        preview_start="#0d1018",
        preview_end="#9e8cff",
        accent="#9e8cff",
        env_value="slate-violet",
        tokens={
            "--bg": "#0d1018",
            "--surface": "#141926",
            "--surface2": "#1b2233",
            "--border": "#283149",
            "--border-hi": "#364364",
            "--text": "#d4d7e4",
            "--text-hi": "#f2f4fb",
            "--muted": "#8d94aa",
            "--green": "#7bd8b5",
            "--green-dim": "#4aa788",
            "--blue": "#7fc8ff",
            "--amber": "#f3b56a",
            "--red": "#ff748f",
            "--purple": "#9e8cff",
            "--glow-green": "0 0 8px rgba(123,216,181,.24), 0 0 20px rgba(123,216,181,.1)",
            "--glow-blue": "0 0 8px rgba(127,200,255,.24), 0 0 20px rgba(127,200,255,.1)",
            "--glow-amber": "0 0 8px rgba(243,181,106,.26), 0 0 20px rgba(243,181,106,.1)",
            "--glow-red": "0 0 8px rgba(255,116,143,.26)",
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


def theme_css(theme: UITheme) -> str:
    lines = [":root {"]
    for key, value in theme.tokens.items():
        lines.append(f"  {key}: {value};")
    lines.append("}")
    return "\n".join(lines)