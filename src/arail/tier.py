"""Tier awareness — shared by the portal and the built-in agents.

Single source of truth for "which tier is this lab running as". The portal
(``src/arail/portal/app.py``) and the agents both need it, and the agents must
not import the portal (heavy + circular). Keep this module dependency-free.

Two tiers: ``minimalist`` (the everyday lab) and ``maximus`` (the full bench).
The v1.0.0 rename accepts the legacy ``min``/``max`` env values with a one-shot
deprecation warning (compat shim removed in v1.1.0).
"""
from __future__ import annotations

import logging
import os

TIERS: tuple[str, ...] = ("minimalist", "maximus")

# v1.0.0 tier rename — old min/max env values accepted with a one-shot warning.
_LEGACY_TIER_MAP: dict[str, str] = {"min": "minimalist", "max": "maximus"}
_LEGACY_TIER_WARNED: set[str] = set()


def get_current_tier() -> str:
    """Return the lab tier from ``LAB_TIER`` — ``minimalist`` or ``maximus``.

    Unknown values fall back to ``minimalist`` (the safe default). Legacy
    ``min``/``max`` are mapped with a one-shot deprecation warning.
    """
    raw = os.getenv("LAB_TIER", "minimalist").strip().lower()
    if raw in _LEGACY_TIER_MAP:
        if raw not in _LEGACY_TIER_WARNED:
            try:
                logging.getLogger("arail.tier").warning(
                    "LAB_TIER=%r is deprecated — use %r instead "
                    "(compat shim removes in v1.1.0)",
                    raw, _LEGACY_TIER_MAP[raw],
                )
            except Exception:  # noqa: BLE001
                pass
            _LEGACY_TIER_WARNED.add(raw)
        raw = _LEGACY_TIER_MAP[raw]
    return raw if raw in TIERS else "minimalist"


def is_maximus() -> bool:
    """True when the lab is running on the maximus (full-bench) tier.

    This is the gate for "agents default to the aeroLLM 2nd inference" — the
    deep backend only ships on maximus, so minimalist agents stay on the fast
    on-GPU model.
    """
    return get_current_tier() == "maximus"
