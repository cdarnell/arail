"""Live lab identity resolver — the single source of truth for "who is this lab".

Resolves the effective lab identity at REQUEST time from the World mount sidecar
(``world-mount.json``), mirroring how the dictionary flip already resolves from
the mount per request. No module-level cache: a stale cache is exactly the
"needs-restart / wrong-after-unmount" class of bug we are removing.

- A World mounted  → derive identity (name, logo, theme, intent, framing,
  palette) from the staged ``face.json`` (+ manifest ``display_name``), each
  field independently falling back to operator brand / built-in default when its
  source is missing (tolerated-partial).
- No World mounted → operator ``LAB_*`` brand + built-in AI/ML defaults
  (reproduces today's behaviour exactly — regression-safe).

Consent model: mounting a World IS the operator's consent to adopt that World's
identity, including the (delimited, length-capped) Buddy framing block. There is
no separate ``--apply-face`` step and no ``.env`` write — the sidecar is the
single, cross-restart source of truth.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from arail.brand import Brand, load_brand
from arail.ui_theme import UITheme, load_ui_theme, default_ui_theme

_log = logging.getLogger(__name__)

# Built-in AI/ML defaults (lifted verbatim from the current hardcoded dashboard
# Mission-card string and the startup-banner intent name).
_DEFAULT_LAB_THEME = (
    "Making SSD-hosted model inference faster — frontier "
    "open-weight models on laptop hardware"
)
_DEFAULT_INTENT_NAME = "AI Engineer"


@dataclass(frozen=True)
class Identity:
    name: str                 # LAB_NAME  ← face.name when mounted
    logo: str                 # LAB_LOGO  ← ⟨face.name⟩ when mounted
    short_name: str
    tagline: str
    version: str
    lab_theme: str            # Mission-card north-star line (was LAB_THEME)
    intent: str               # "ai" | "other" | ...  (was LAB_INTENT)
    intent_name: str          # was LAB_INTENT_NAME
    intent_description: str   # was LAB_INTENT_DESCRIPTION (domain_framing)
    vocabulary_register: str  # face.vocabulary_register ("" when unmounted)
    ui_theme: UITheme         # resolved preset
    world: Optional[str]      # mounted world slug, or None
    mounted: bool

    def brand(self) -> Brand:
        """Back-compat Brand view for code/templates that expect a Brand."""
        return Brand(
            name=self.name,
            short_name=self.short_name,
            tagline=self.tagline,
            logo=self.logo,
            version=self.version,
        )


def _unmounted_identity() -> Identity:
    """Operator brand + built-in AI/ML defaults. Reproduces today's behaviour."""
    b = load_brand()
    return Identity(
        name=b.name,
        logo=b.logo,
        short_name=b.short_name,
        tagline=b.tagline,
        version=b.version,
        lab_theme=os.getenv("LAB_THEME", _DEFAULT_LAB_THEME),
        intent=os.getenv("LAB_INTENT", "ai").lower(),
        intent_name=os.getenv("LAB_INTENT_NAME", _DEFAULT_INTENT_NAME),
        intent_description=os.getenv("LAB_INTENT_DESCRIPTION", ""),
        vocabulary_register="",
        ui_theme=load_ui_theme(),
        world=None,
        mounted=False,
    )


def effective_identity(data_dir: Path | None = None) -> Identity:
    """Live lab identity, resolved at REQUEST time.

    Mounted World  → derive from face.json (+ manifest display_name).
    No World       → operator brand + built-in AI/ML defaults.
    Never raises: any failure falls back to operator/default per field.
    """
    try:
        from arail.world_mount import current_mount, mounted_face

        record = current_mount(data_dir)
    except Exception as e:  # noqa: BLE001
        _log.warning("identity: mount lookup failed, using default: %s", e)
        return _unmounted_identity()

    if record is None:
        return _unmounted_identity()

    # Mounted path — wrap entirely so the resolver never raises into a handler.
    try:
        b = load_brand()
        face = mounted_face(record)

        # display_name from manifest, best-effort, never from face-derived input.
        display_name = record.world
        try:
            import json

            manifest_path = Path(record.bundle_dir) / "manifest.json"
            if manifest_path.exists():
                manifest = json.loads(manifest_path.read_bytes())
                display_name = str(manifest.get("display_name", record.world))
        except Exception:  # noqa: BLE001
            display_name = record.world

        has_face = bool(face)
        face = face or {}
        face_name = str(face.get("name", "")).strip()

        # name → face.name → display_name (face present) → operator brand (no face)
        if face_name:
            name = face_name
        elif has_face:
            name = display_name or b.name
        else:
            name = b.name

        # Per-field fallback: when face is missing, every face-derived field
        # falls back to operator brand / built-in default.
        logo = f"⟨{name}⟩" if has_face else b.logo
        short_name = (
            name.lower().replace(" ", "-").replace("'", "")
            if has_face
            else b.short_name
        )
        tagline = (str(face.get("tagline", "")).strip() or b.tagline) if has_face else b.tagline

        # lab_theme → face.name (World's north-star) → default
        lab_theme = face_name if face_name else _DEFAULT_LAB_THEME

        # intent — a mounted World is always a custom domain
        intent = "other"

        # intent_name → face.name → display_name (face present) → default
        if face_name:
            intent_name = face_name
        elif has_face:
            intent_name = display_name or _DEFAULT_INTENT_NAME
        else:
            intent_name = _DEFAULT_INTENT_NAME

        intent_description = str(face.get("domain_framing", "")) if has_face else ""
        vocabulary_register = str(face.get("vocabulary_register", "")) if has_face else ""

        # ui_theme resolution: validated face.theme block → palette_hint
        # preset match → default. The theme block goes through the paranoid
        # world_theme validator (fail-closed); a rejected theme never blocks
        # identity resolution, it just falls through.
        ui_theme = default_ui_theme()
        palette_hint = str(face.get("palette_hint", "")).strip() if has_face else ""
        if palette_hint:
            resolved = load_ui_theme(palette_hint)
            if resolved.id == palette_hint or resolved.env_value == palette_hint:
                ui_theme = resolved
        if has_face and face.get("theme") is not None:
            try:
                from arail.world_theme import build_world_ui_theme, parse_world_theme

                spec, reason = parse_world_theme(face.get("theme"), world=record.world)
                if spec is not None:
                    ui_theme = build_world_ui_theme(spec, record.world, name)
                else:
                    _log.warning(
                        "identity: world %s theme rejected (%s), falling back to %s",
                        record.world, reason, ui_theme.id,
                    )
            except Exception as e:  # noqa: BLE001
                _log.warning("identity: world theme resolution failed: %s", e)

        return Identity(
            name=name,
            logo=logo,
            short_name=short_name,
            tagline=tagline,
            version=b.version,
            lab_theme=lab_theme,
            intent=intent,
            intent_name=intent_name,
            intent_description=intent_description,
            vocabulary_register=vocabulary_register,
            ui_theme=ui_theme,
            world=record.world,
            mounted=True,
        )
    except Exception as e:  # noqa: BLE001
        _log.warning("identity: mounted resolution failed, using default: %s", e)
        return _unmounted_identity()
