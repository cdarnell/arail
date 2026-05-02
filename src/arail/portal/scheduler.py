"""In-process inference priority queue + fast-path metrics.

This module exposes a single async semaphore that gates calls into
the local-LLM router. Lightweight HTTP paths (dashboard polls, system
health, etc.) bypass the semaphore via the FAST_PATH middleware so
they never queue behind a 30-second inference response.

Usage
-----
In a chat handler::

    async with scheduler.inference_slot("chat-stream"):
        async for item in _stream_sync_iterator(router.stream_complete(...)):
            ...

In the FAST_PATH middleware::

    scheduler.fast_path_record(request.url.path, elapsed_ms)

Reading metrics::

    data = scheduler.snapshot()  # JSON-safe dict

Configuration
-------------
``ARAIL_INFERENCE_CONCURRENCY`` — integer [1, 4], default 1.  Controls
the semaphore capacity.  Set higher only when you have confirmed that
the router supports concurrent calls without thrashing (e.g. multiple
CPU threads / GPUs).  Single-worker uvicorn (the default) means this
is a process-wide limit.
"""

from __future__ import annotations

import asyncio
import os
from collections import deque
from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

# ---------------------------------------------------------------------------
# Fast-path prefix set
# ---------------------------------------------------------------------------
# Path prefixes that the fastpath_meter middleware times AND lets through
# without acquiring the inference semaphore. Anything not in this list
# is "heavy" — heavy paths still pass through the middleware (it just
# doesn't time them) and acquire the semaphore inside the handler.
#
# Guard: do NOT add /api/chat, /api/teacher/ask, or /api/agents/<id>/ask
# here — those are the callers of inference_slot.
FAST_PATH_PREFIXES: tuple[str, ...] = (
    "/api/system/",
    "/api/jobs/",
    "/api/activity/",
    "/api/agents/status",
    "/api/admin/components",
    "/api/admin/check-updates",
    "/api/admin/perf",
    "/api/admin/cleanup",
    "/api/admin/security",
    "/api/pkb/",
    "/api/research/",
    "/static/",
    "/favicon.ico",
)


# ---------------------------------------------------------------------------
# Module-level state (single-process; per-worker when --workers >1)
# ---------------------------------------------------------------------------
_SEM: asyncio.Semaphore | None = None
_INFLIGHT: int = 0
_PENDING: int = 0
_WAIT_SAMPLES: dict[str, deque[float]] = {}   # ms per label, maxlen 256
_RUN_SAMPLES: dict[str, deque[float]] = {}    # ms per label, maxlen 256
_FAST_SAMPLES: deque[float] = deque(maxlen=512)   # fast-path latency ms
_COMPLETED: deque[float] = deque(maxlen=4096)     # epoch sec of completions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _capacity() -> int:
    """Read ARAIL_INFERENCE_CONCURRENCY env, clamp to [1, 4], default 1.

    Malformed or empty values silently fall back to 1.
    """
    raw = os.getenv("ARAIL_INFERENCE_CONCURRENCY", "").strip()
    try:
        val = int(raw)
    except (ValueError, TypeError):
        return 1
    return max(1, min(4, val))


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-init the semaphore on the running event loop.

    Called only from within ``inference_slot``, which is always inside a
    running asyncio loop.  Because asyncio is cooperative and there is no
    ``await`` between the ``None`` check and the assignment, there is no
    race between two coroutines hitting this path simultaneously.
    """
    global _SEM
    if _SEM is None:
        _SEM = asyncio.Semaphore(_capacity())
    return _SEM


def _percentile(data: deque[float], p: float) -> float:
    """Return the p-th percentile of *data* (0–100).  Returns 0.0 if empty."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100.0) * (len(sorted_data) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(sorted_data) - 1)
    frac = idx - lo
    return sorted_data[lo] + frac * (sorted_data[hi] - sorted_data[lo])


def _label_stats(samples: dict[str, deque[float]]) -> dict[str, dict]:
    return {
        label: {
            "p50": round(_percentile(q, 50), 2),
            "p95": round(_percentile(q, 95), 2),
            "n": len(q),
        }
        for label, q in samples.items()
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@asynccontextmanager
async def inference_slot(label: str = "chat") -> AsyncIterator[None]:
    """Acquire one inference slot. Records wait_ms + run_ms per label.

    Postcondition: the slot is always released, even if the body raises.
    The ``try/finally`` guarantees that a handler exception never deadlocks
    subsequent callers.

    Bad input: ``label=""`` is recorded under ``"_unknown"``; never raises.
    """
    global _INFLIGHT, _PENDING

    if not label:
        label = "_unknown"

    if label not in _WAIT_SAMPLES:
        _WAIT_SAMPLES[label] = deque(maxlen=256)
    if label not in _RUN_SAMPLES:
        _RUN_SAMPLES[label] = deque(maxlen=256)

    sem = _get_semaphore()
    _PENDING += 1
    t_wait_start = perf_counter()

    await sem.acquire()

    t_wait_end = perf_counter()
    _PENDING -= 1
    _INFLIGHT += 1
    wait_ms = (t_wait_end - t_wait_start) * 1000.0
    _WAIT_SAMPLES[label].append(wait_ms)

    t_run_start = perf_counter()
    try:
        yield
    finally:
        t_run_end = perf_counter()
        run_ms = (t_run_end - t_run_start) * 1000.0
        _RUN_SAMPLES[label].append(run_ms)
        _COMPLETED.append(t_run_end)   # epoch-style via perf_counter is fine for 5m window
        _INFLIGHT -= 1
        sem.release()


def fast_path_record(path: str, ms: float) -> None:
    """Append a fast-path latency sample.  Never raises; drops on overflow."""
    try:
        _FAST_SAMPLES.append(ms)
    except Exception:  # noqa: BLE001
        pass


def snapshot() -> dict:
    """Return a JSON-safe metrics snapshot.  Always succeeds.

    Shape::

        {
          "capacity": int,
          "in_flight": int,
          "pending": int,
          "completed_5m": int,          # run-completes in last 300 s
          "wait_ms":     {"<label>": {"p50": float, "p95": float, "n": int}},
          "run_ms":      {"<label>": {"p50": float, "p95": float, "n": int}},
          "fast_path_ms": {"p50": float, "p95": float, "n": int},
        }
    """
    now = perf_counter()
    cutoff = now - 300.0  # 5 minutes
    completed_5m = sum(1 for ts in _COMPLETED if ts >= cutoff)

    fast_stats: dict[str, object] = {
        "p50": round(_percentile(_FAST_SAMPLES, 50), 2),
        "p95": round(_percentile(_FAST_SAMPLES, 95), 2),
        "n": len(_FAST_SAMPLES),
    }

    return {
        "capacity": _capacity(),
        "in_flight": _INFLIGHT,
        "pending": _PENDING,
        "completed_5m": completed_5m,
        "wait_ms": _label_stats(_WAIT_SAMPLES),
        "run_ms": _label_stats(_RUN_SAMPLES),
        "fast_path_ms": fast_stats,
    }
