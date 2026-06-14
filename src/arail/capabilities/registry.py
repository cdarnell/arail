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


def _reset_for_tests() -> None:
    """Clear the registry (tests that re-import backends)."""
    _ADAPTERS.clear()
