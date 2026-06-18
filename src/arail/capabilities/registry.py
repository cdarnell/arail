"""The capability registry: id -> adapter map, with platform-aware selection.

Registration happens at import of ``arail.capabilities`` (its ``__init__``
imports both backend packages, each calling ``register(...)`` at module scope).
Macos and Linux backends both register unconditionally; *availability* (not
registration) is platform-gated via ``is_available()``.
"""

from __future__ import annotations

import os
import platform
from typing import Dict, List, Optional

from .adapter import Adapter

# id -> list of adapters (one per platform, in registration order)
_ADAPTERS: Dict[str, List[Adapter]] = {}


def _host_platform() -> str:
    """The platform to select for. Honors ``ARAIL_FORCE_PLATFORM`` (test hook,
    WC-B) so a test on macOS can force-select the Linux backend."""
    forced = os.getenv("ARAIL_FORCE_PLATFORM")
    if forced:
        return forced.strip().lower()
    return platform.system().lower()


def register(adapter: Adapter) -> None:
    """Register an adapter under its ``id``. Called at import by each backend."""
    _ADAPTERS.setdefault(adapter.id, []).append(adapter)


def adapters_for(capability_id: str) -> List[Adapter]:
    """All registered adapters for an id, any platform."""
    return list(_ADAPTERS.get(capability_id, []))


def select(capability_id: str) -> Optional[Adapter]:
    """Platform-aware selection.

    - Prefer a platform-matched adapter that ``is_available()``.
    - Else return the platform-matched-but-unavailable adapter (so the caller
      gets a CapabilityUnavailable with the RIGHT message — e.g. the Linux stub).
    - Else None (no adapter registered for this id at all → WC-C path).
    """
    candidates = _ADAPTERS.get(capability_id)
    if not candidates:
        return None
    host = _host_platform()
    matched = [a for a in candidates if a.platform == host]
    if not matched:
        return None
    for a in matched:
        try:
            if a.is_available():
                return a
        except Exception:  # noqa: BLE001 — a flaky probe must not crash selection
            continue
    return matched[0]


def available_capability(capability_id: str) -> Optional[Adapter]:
    """Return the platform adapter for ``capability_id`` IFF it ``is_available()``
    on this machine, else None.

    This is the toolchain-present probe used by the KB capture affordances: it is
    decoupled from any mounted World (it asks the platform adapter directly, not
    the World's declared capabilities). A flaky ``is_available()`` probe degrades
    to None rather than crashing the caller.
    """
    candidates = _ADAPTERS.get(capability_id)
    if not candidates:
        return None
    host = _host_platform()
    matched = [a for a in candidates if a.platform == host]
    for a in matched:
        try:
            if a.is_available():
                return a
        except Exception:  # noqa: BLE001 — a flaky probe must not crash the caller
            continue
    return None


# Capabilities whose toolchain the KB capture UI can light up, independent of any
# mounted World. (STT = on-device Whisper; OCR = on-device image-text backend.)
_INSTALLABLE_CAPABILITY_IDS = ("speech-to-text", "equation-ocr")


def installed_capabilities() -> Dict[str, bool]:
    """``{capability_id: is_available()}`` for the KB-installable capabilities on
    this platform. Decoupled from any World mount."""
    return {
        cid: available_capability(cid) is not None
        for cid in _INSTALLABLE_CAPABILITY_IDS
    }


def _reset_for_tests() -> None:
    """Clear the registry (tests that re-import backends)."""
    _ADAPTERS.clear()
