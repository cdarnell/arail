"""Memory-pressure guard for the MLX backend.

The Metal allocator throws a C++ exception
(``[METAL] kIOGPUCommandBufferCallbackErrorOutOfMemory``) when the
unified-memory pool is exhausted. C++ exceptions bypass Python's
``try/except``, so a single OOM during a router call kills the entire
lab process — taking the portal, agents, and any in-flight research
runs down with it.

This module is the first line of defense: a cheap pre-flight check
that asks the OS about the current Metal memory pressure and refuses
the call when the threshold is exceeded. Callers are expected to
catch :class:`MetalOutOfMemory` and degrade gracefully (heuristic
parser, queued retry, smaller prompt, etc.).

The second line of defense — subprocess isolation — lives in
``arail.skills.goal_parser`` for the parser path. Even with this
guard, a single oversized prompt can still OOM mid-generation; the
subprocess wrapper catches that case so the parent process survives.

Everything here fails soft: if MLX isn't installed (CUDA / CPU /
hybrid installs), every check returns "safe" so non-MLX backends
aren't penalized.
"""

from __future__ import annotations

import os
from typing import Optional


# Default threshold: refuse when ≥ 85% of the unified memory pool is
# already pinned. Tunable via ARAIL_MLX_MEMORY_GUARD_PCT in .env.
_DEFAULT_GUARD_PCT = 0.85


class MetalOutOfMemory(RuntimeError):
    """Raised when a Metal call is refused because of memory pressure.

    This is a normal control-flow signal — callers should catch it and
    degrade (heuristic, queued retry, smaller prompt). It does NOT
    indicate that an OOM has actually occurred yet, only that one is
    likely if we proceed.
    """

    def __init__(self, message: str, *, pressure: Optional[float] = None) -> None:
        super().__init__(message)
        self.pressure = pressure


def _mlx_module():
    """Import ``mlx.core`` lazily — return None if MLX isn't installed."""
    try:
        import mlx.core as mx  # type: ignore[import-untyped]
        return mx
    except Exception:
        return None


def clear_metal_cache() -> bool:
    """Drop everything Metal has cached. Returns True iff something was cleared.

    Safe to call before AND after every LLM generation pass. Cheap
    (microseconds in the no-cached-state case). The kernel call list,
    activation buffers, and intermediate tensors are released even if
    Python references to the model itself remain.
    """
    mx = _mlx_module()
    if mx is None:
        return False
    try:
        clear = getattr(getattr(mx, "metal", None), "clear_cache", None)
        if clear is None:
            return False
        clear()
        return True
    except Exception:
        return False


def metal_memory_pressure() -> Optional[float]:
    """Return the current Metal memory pressure in [0.0, 1.0] or None.

    Computed as ``active_memory / max_recommended_working_set``. None
    means we couldn't measure (MLX missing, API surface changed, etc.) —
    callers should treat that as "unknown, proceed."
    """
    mx = _mlx_module()
    if mx is None:
        return None
    metal = getattr(mx, "metal", None)
    if metal is None:
        return None
    try:
        active = getattr(metal, "get_active_memory", None)
        ceiling = getattr(metal, "get_memory_limit", None) or getattr(
            metal, "get_max_recommended_working_set_size", None
        )
        if active is None or ceiling is None:
            return None
        a = float(active())
        c = float(ceiling())
        if c <= 0:
            return None
        return a / c
    except Exception:
        return None


def _guard_threshold() -> float:
    """Read the configurable threshold, clamped to [0.5, 0.99]."""
    raw = os.getenv("ARAIL_MLX_MEMORY_GUARD_PCT")
    if not raw:
        return _DEFAULT_GUARD_PCT
    try:
        v = float(raw)
    except ValueError:
        return _DEFAULT_GUARD_PCT
    return max(0.5, min(0.99, v))


def assert_metal_safe(*, op: str = "MLX call") -> None:
    """Raise :class:`MetalOutOfMemory` when pressure is past the threshold.

    Always clears the Metal cache first — much of the time the
    "pressure" is stale activations from an earlier pass that the
    next clear would release anyway. We measure AFTER the clear so
    the decision reflects the new state.

    No-ops when MLX isn't installed or pressure is unmeasurable.
    """
    clear_metal_cache()
    pressure = metal_memory_pressure()
    if pressure is None:
        return
    threshold = _guard_threshold()
    if pressure >= threshold:
        raise MetalOutOfMemory(
            f"Refusing {op}: Metal memory pressure {pressure:.0%} ≥ "
            f"guard threshold {threshold:.0%}. Lower the workload, "
            f"close other GPU consumers, or raise "
            f"ARAIL_MLX_MEMORY_GUARD_PCT in .env if you accept the risk.",
            pressure=pressure,
        )


def safely(callable_, *args, op: str = "MLX call", **kwargs):
    """Run ``callable_`` between two cache clears + a pressure pre-check.

    Convenience wrapper for the common pattern: clear, check, run,
    clear. Re-raises whatever the callable raises (including
    :class:`MetalOutOfMemory` from the pre-check) so callers stay in
    control of their fallback path.
    """
    assert_metal_safe(op=op)
    try:
        return callable_(*args, **kwargs)
    finally:
        clear_metal_cache()
