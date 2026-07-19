"""Background Tier-1 (aeroLLM) preload — deep work feels instant.

The deep model historically loaded lazily on the first agent call, so the
first deep request after every portal (re)start paid a multi-GB weight
load. This loop preloads it in the background whenever it is SAFE to do
so, using the exact same gate agents already obey:

    deep_policy.background_safe()  — not halted, not in the active window,
    operator absent (runtime profile), profile allows background aerollm,
    Metal memory pressure < 0.60.

The gate is re-checked *after* acquiring the inference slot (presence may
have arrived while queued). Construction goes through
``deep_policy.get_deep_router()`` — the single owner of the resident
runtime — so there is never a second copy. Kill switch:
``ARAIL_AEROLLM_PRELOAD=0``. Interval: ``ARAIL_AEROLLM_PRELOAD_INTERVAL_SEC``
(default 300).

Note ``get_deep_router()`` latches failures (_FAILED): if construction
fails once, this loop emits one loud warning and stands down instead of
thrashing a broken wheel/model every tick.
"""

from __future__ import annotations

import asyncio
import logging
import os

log = logging.getLogger(__name__)


def _enabled() -> bool:
    return os.getenv("ARAIL_AEROLLM_PRELOAD", "1").strip().lower() \
        not in ("0", "false", "no")


def _interval() -> float:
    try:
        return max(float(os.getenv("ARAIL_AEROLLM_PRELOAD_INTERVAL_SEC", "300")), 30.0)
    except ValueError:
        return 300.0


def _tier1_resident() -> bool:
    """Inspect the shared runtime WITHOUT constructing anything (R5)."""
    try:
        from arail.router.backends import AeroLLMBackend
        shared = getattr(AeroLLMBackend, "_shared", None) or {}
        return any(getattr(inst, "_runtime", None) is not None
                   for inst in shared.values())
    except Exception:  # noqa: BLE001
        return False


async def _preload_once() -> str:
    """One preload attempt. Returns a status string (for tests/logging)."""
    from arail.agents import deep_policy
    from arail.portal import scheduler
    from arail.registry import health as reg_health
    from arail.registry.store import TIER1_ID

    if _tier1_resident():
        return "already_resident"
    # prefer_deep(foreground=False) = maximus tier + wheel importable +
    # background_safe() (halt / window / presence / profile / pressure<0.60).
    if not deep_policy.prefer_deep(foreground=False):
        return "not_safe"

    reg_health.mark_warming(TIER1_ID)
    try:
        async with scheduler.inference_slot("aerollm-preload"):
            # Presence may have arrived while we queued behind a chat turn —
            # re-check before committing to a multi-GB synchronous load.
            if not deep_policy.background_safe():
                return "not_safe_after_wait"
            router = await asyncio.to_thread(deep_policy.get_deep_router)
    finally:
        reg_health.clear_warming(TIER1_ID)

    try:
        from arail.activity import activity_log
        from arail.registry import get_registry
        reg = get_registry()
        reg._ensure_loaded()
        entry = reg.entries.get(TIER1_ID)
        if entry is not None:
            entry.health = reg_health.probe_entry(entry)
        if router is not None:
            activity_log.emit(
                "registry",
                "Deep model preloaded — Tier 1 is resident and ready.",
                "success",
                {"model_event": {"kind": "preload_ok", "entry_id": TIER1_ID}})
            return "loaded"
        activity_log.emit(
            "registry",
            "Deep model preload failed (aeroLLM unavailable) — deep calls "
            "will fall back visibly. Standing down until restart.",
            "warn",
            {"model_event": {"kind": "preload_failed", "entry_id": TIER1_ID}})
        return "failed"
    except Exception:  # noqa: BLE001
        return "failed"


async def aerollm_preload_loop() -> None:
    """Fire-and-forget startup task. Never raises."""
    if not _enabled():
        return
    announced_skip = False
    while True:
        try:
            status = await _preload_once()
            if status in ("loaded", "failed", "already_resident"):
                if status == "failed":
                    return   # _FAILED latched — stand down, stay honest
                # Resident (either way): drop to a slow keep-watch so a
                # future manual unload can re-trigger a warm.
            elif status.startswith("not_safe") and not announced_skip:
                announced_skip = True
                try:
                    from arail.activity import activity_log
                    activity_log.emit(
                        "registry",
                        "Deep-model preload waiting for a safe window "
                        "(operator absent + memory headroom).", "info")
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            log.warning("aerollm preload tick failed: %s", exc)
        await asyncio.sleep(_interval())
