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


# Default threshold: refuse when ≥ 75% of the unified memory pool is
# already pinned. Tunable via ARAIL_MLX_MEMORY_GUARD_PCT in .env.
# Lowered from 0.85 → 0.75 after a Metal Insufficient-Memory abort got
# past the old threshold and crashed the portal. The 10pp headroom buys
# room for activations that grow during a forward pass — by the time
# pressure crosses 85% the next allocation is already at the wire.
_DEFAULT_GUARD_PCT = 0.75


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

    MLX 0.21 promoted ``mx.clear_cache`` and deprecated
    ``mx.metal.clear_cache``. Try the new name first, fall back to the
    legacy one — both work today; only the legacy one prints a deprecation
    warning that pollutes our logs and (more importantly) the user's
    confidence in the lab.
    """
    mx = _mlx_module()
    if mx is None:
        return False
    try:
        clear = getattr(mx, "clear_cache", None) or getattr(
            getattr(mx, "metal", None), "clear_cache", None
        )
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

    Tries the new top-level API first (``mx.get_active_memory`` /
    ``mx.get_memory_limit``, MLX 0.21+) and falls back to the legacy
    ``mx.metal.*`` namespace. Both still resolve today; the legacy
    fallback is purely for older venvs.
    """
    mx = _mlx_module()
    if mx is None:
        return None
    metal = getattr(mx, "metal", None)
    try:
        active = (
            getattr(mx, "get_active_memory", None)
            or (getattr(metal, "get_active_memory", None) if metal else None)
        )
        ceiling = (
            getattr(mx, "get_memory_limit", None)
            or (getattr(metal, "get_memory_limit", None) if metal else None)
            or (getattr(metal, "get_max_recommended_working_set_size", None) if metal else None)
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


def install_memory_soft_limit(fraction: float = 0.85) -> Optional[int]:
    """Tell the Metal allocator to swap before throwing.

    Sets the MLX memory soft-limit to ``fraction`` of the recommended
    working set. When inference would exceed it, the allocator copies
    cold buffers out to system memory instead of raising
    ``kIOGPUCommandBufferCallbackErrorOutOfMemory`` — which is a C++
    ``std::runtime_error`` Python can't catch and which therefore
    aborts the entire interpreter.

    Returns the previous limit (in bytes) or None if MLX isn't
    installed / the API isn't present. Idempotent — call once on
    backend init.

    See: https://ml-explore.github.io/mlx/build/html/dev/metal_debugger.html
    """
    mx = _mlx_module()
    if mx is None:
        return None
    try:
        metal = getattr(mx, "metal", None)
        # Find the ceiling (working-set size). Same lookup as pressure.
        get_ceiling = (
            getattr(mx, "get_memory_limit", None)
            or (getattr(metal, "get_max_recommended_working_set_size", None) if metal else None)
        )
        # Find the setter. Try new top-level first, then legacy metal namespace.
        set_limit = (
            getattr(mx, "set_memory_limit", None)
            or (getattr(metal, "set_memory_limit", None) if metal else None)
        )
        if get_ceiling is None or set_limit is None:
            return None
        ceiling = float(get_ceiling())
        if ceiling <= 0:
            return None
        target = int(ceiling * max(0.5, min(0.99, fraction)))
        # MLX < 0.13 takes (limit, relaxed); newer takes (limit). Try both.
        try:
            previous = set_limit(target, True)  # legacy: relaxed=True
        except TypeError:
            previous = set_limit(target)
        return int(previous) if previous is not None else None
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
