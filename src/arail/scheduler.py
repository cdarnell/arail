"""Arail scheduler — time windows + a global halt flag.

Two concepts:

1. **Window** — active / heavy / idle, derived from `LAB_ACTIVE_HOURS`
   and `LAB_HEAVY_HOURS` in the environment. Default: active 08:00-22:00,
   heavy 22:00-08:00 (so the GPU hammers while you sleep).
2. **Halt flag** — a process-wide boolean that agents poll. Setting it
   via :func:`halt_all_jobs` cancels in-flight work without tearing down
   the portal itself (that's :func:`arail stop`).

The scheduler is deliberately simple: no cron, no DAG, no wake-up
callbacks. Agents are responsible for calling :func:`current_window`
and :func:`jobs_halted` at their own tick points.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal

Window = Literal["active", "heavy", "idle"]


@dataclass(frozen=True)
class HourRange:
    start: time
    end: time

    def contains(self, now: time) -> bool:
        if self.start <= self.end:
            return self.start <= now < self.end
        # Wraps midnight (e.g. 22:00-08:00)
        return now >= self.start or now < self.end


def _parse_range(raw: str) -> HourRange | None:
    try:
        lo, hi = raw.strip().split("-", 1)
        return HourRange(time.fromisoformat(lo.strip()), time.fromisoformat(hi.strip()))
    except (ValueError, AttributeError):
        return None


def _active_range() -> HourRange:
    return _parse_range(os.getenv("LAB_ACTIVE_HOURS", "")) \
        or HourRange(time(8, 0), time(22, 0))


def _heavy_range() -> HourRange:
    return _parse_range(os.getenv("LAB_HEAVY_HOURS", "")) \
        or HourRange(time(22, 0), time(8, 0))


def current_window(now: datetime | None = None) -> Window:
    """Return the current window. Heavy takes precedence over active
    when ranges overlap; anything outside both is 'idle'."""
    t = (now or datetime.now()).time()
    if _heavy_range().contains(t):
        return "heavy"
    if _active_range().contains(t):
        return "active"
    return "idle"


def window_label(w: Window | None = None) -> str:
    """Human-friendly label for the dashboard mode indicator."""
    w = w or current_window()
    return {
        "active": "☀ active — light work only",
        "heavy":  "🌙 heavy window — experiments running",
        "idle":   "◦ idle — queued work drains",
    }[w]


def startup_delay_seconds() -> int:
    """How long agents should wait on boot before their first tick."""
    try:
        return max(0, int(os.getenv("LAB_STARTUP_DELAY_SEC", "300")))
    except ValueError:
        return 300


# ── Global halt flag ─────────────────────────────────────────────────

_halt_lock = threading.Lock()
_halted = False


def jobs_halted() -> bool:
    with _halt_lock:
        return _halted


def halt_all_jobs() -> None:
    """Flip the halt flag. Agents poll this and abort their current tick."""
    global _halted
    with _halt_lock:
        _halted = True


def resume_all_jobs() -> None:
    global _halted
    with _halt_lock:
        _halted = False


def state() -> dict:
    """Serializable snapshot for the portal's /api/jobs/state endpoint."""
    w = current_window()
    out = {
        "window": w,
        "label": window_label(w),
        "halted": jobs_halted(),
        "active_hours": os.getenv("LAB_ACTIVE_HOURS", "08:00-22:00"),
        "heavy_hours": os.getenv("LAB_HEAVY_HOURS", "22:00-08:00"),
        "startup_delay_sec": startup_delay_seconds(),
    }
    # Lazy import to avoid circular: runtime_profile imports current_window.
    try:
        from arail.runtime_profile import snapshot as _profile_snapshot
        out["runtime_profile"] = _profile_snapshot()
    except Exception:
        pass
    return out
