"""Observability-under-load test — architect MUST-HIT #1.

The OBS2 mitigation in REVIEW.md is doc-only ("doc-asserted").  This
test proves /metrics latency stays under 50 ms WHILE an inference slot
is held by a slow background task.

The slow task simulates a chat-stream that would normally hold the
slot for 30+ seconds.  /metrics reads only in-memory snapshots, so its
latency must be independent of slot-hold duration.

Allocation:
  - Per ARAIL CLAUDE.md, this is a security/perf test (the architect
    flagged OBS2 as a security concern: a slow /metrics scrape is a
    DoS amplifier when behind a public Prometheus-as-a-service).
"""
from __future__ import annotations

import asyncio
import importlib
import time

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def fresh_scheduler(monkeypatch):
    """Reload arail.portal.scheduler so per-label state is fresh."""
    from arail.portal import scheduler as _sched
    importlib.reload(_sched)
    return _sched


def test_metrics_latency_under_50ms_while_slot_held(monkeypatch, tmp_path, fresh_scheduler):
    """Architect MUST-HIT #1: /metrics responds <50 ms (CI tol 100 ms)
    while inference_slot is held by a slow task."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("LAB_ROOT", str(tmp_path / "lab"))
    monkeypatch.setenv("ARAIL_DATA_DIR", str(tmp_path / "lab" / "data"))
    (tmp_path / "lab" / "data").mkdir(parents=True)

    from arail.portal.app import app

    async def _scenario():
        # Slow task that holds the slot for 1 second — long enough that any
        # /metrics call that synchronizes on the semaphore would stall.
        async def _hold():
            async with fresh_scheduler.inference_slot("chat-stream"):
                await asyncio.sleep(1.0)

        holder = asyncio.create_task(_hold())
        await asyncio.sleep(0.05)  # let holder grab the slot

        # Hit /metrics 10 times via TestClient.  TestClient is sync and
        # creates its own loop per request, but our scheduler module-level
        # state is process-global, so the in-flight count is visible.
        client = TestClient(app)
        latencies_ms = []
        for _ in range(10):
            t0 = time.perf_counter()
            r = client.get("/metrics")
            t1 = time.perf_counter()
            assert r.status_code == 200, r.text
            latencies_ms.append((t1 - t0) * 1000.0)

        await holder
        return latencies_ms

    latencies = asyncio.run(_scenario())

    # OBS2 budget per architect: <50 ms.  We allow CI headroom up to 100 ms
    # so this isn't flaky on busy CI runners; the design intent is 50 ms.
    p95 = sorted(latencies)[int(len(latencies) * 0.95)]
    p_max = max(latencies)
    assert p_max < 100.0, (
        f"/metrics latency exceeded 100ms while slot held — "
        f"p95={p95:.1f}ms, max={p_max:.1f}ms, samples={latencies}"
    )
    # The architect's design budget is 50 ms; we record but don't fail on
    # overrun up to 100 ms because TestClient's overhead is variable on
    # cold imports.  After the first call the overhead drops dramatically.
    after_warmup = latencies[1:]  # skip the first call
    p95_warm = sorted(after_warmup)[int(len(after_warmup) * 0.95)]
    assert p95_warm < 50.0, (
        f"/metrics post-warmup p95 exceeded 50ms budget — "
        f"p95={p95_warm:.1f}ms, samples={after_warmup}"
    )


def test_metrics_does_not_acquire_inference_slot(monkeypatch, tmp_path, fresh_scheduler):
    """OBS2 corollary: /metrics MUST NOT acquire inference_slot itself —
    if it did, scrape latency would be unbounded under inference load."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))

    from arail.portal.app import app

    # Hold the slot AND set capacity to 1.  If /metrics tried to acquire,
    # the second metrics call would block.
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "1")

    async def _scenario():
        async def _hold():
            async with fresh_scheduler.inference_slot("chat-stream"):
                await asyncio.sleep(2.0)

        holder = asyncio.create_task(_hold())
        await asyncio.sleep(0.05)

        client = TestClient(app)
        # Two rapid /metrics calls.  If /metrics acquired the slot, the
        # second one would queue for ~2s.
        t0 = time.perf_counter()
        r1 = client.get("/metrics")
        r2 = client.get("/metrics")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert r1.status_code == 200 and r2.status_code == 200

        # Cancel the holder so the test doesn't wait the full 2s.
        holder.cancel()
        try:
            await holder
        except asyncio.CancelledError:
            pass

        return elapsed_ms

    elapsed_ms = asyncio.run(_scenario())
    assert elapsed_ms < 1500.0, (
        f"Two /metrics calls took {elapsed_ms:.0f}ms while slot held — "
        f"this suggests /metrics is acquiring the inference semaphore (OBS2 violation)"
    )
