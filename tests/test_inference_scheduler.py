"""Inference-scheduler tests (failure modes A1, A2, A5, A6, A7, A9, OBS6).

Covers ``arail.portal.scheduler`` (note: ``tests/test_scheduler.py`` already
exists for ``arail.scheduler`` — the time-window scheduler — so we use a
distinct filename here to keep the two surfaces separate).

Cases:
  - Capacity clamp (A2): empty / negative / zero / >4 / garbage.
  - Semaphore release on exception and on cancellation (A1).
  - Per-label snapshot mirrors aggregate counters (OBS6).
  - FAST_PATH_PREFIXES does not include the chat handlers (A9).
  - Lazy semaphore init (A7).
  - Empty-label normalisation.
  - snapshot() / per_label_snapshot() shape.
"""
from __future__ import annotations

import asyncio

import pytest


# ---------------------------------------------------------------------------
# Fresh-module fixture — every test gets pristine module state.
# ---------------------------------------------------------------------------

@pytest.fixture()
def scheduler(monkeypatch):
    """Reload arail.portal.scheduler so module-level state is fresh per test."""
    import importlib
    from arail.portal import scheduler as s
    importlib.reload(s)
    return s


# ---------------------------------------------------------------------------
# A2 — capacity clamp
# ---------------------------------------------------------------------------

def test_capacity_default_is_one_when_unset(monkeypatch, scheduler):
    monkeypatch.delenv("ARAIL_INFERENCE_CONCURRENCY", raising=False)
    assert scheduler._capacity() == 1


def test_capacity_clamps_zero_to_one(monkeypatch, scheduler):
    """A2 mitigation: ARAIL_INFERENCE_CONCURRENCY=0 must not produce a 0-capacity semaphore."""
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "0")
    assert scheduler._capacity() == 1


def test_capacity_clamps_negative_to_one(monkeypatch, scheduler):
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "-5")
    assert scheduler._capacity() == 1


def test_capacity_clamps_high_to_four(monkeypatch, scheduler):
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "99")
    assert scheduler._capacity() == 4


def test_capacity_garbage_falls_back_to_one(monkeypatch, scheduler):
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "not-an-int")
    assert scheduler._capacity() == 1


def test_capacity_empty_string_falls_back_to_one(monkeypatch, scheduler):
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "   ")
    assert scheduler._capacity() == 1


def test_capacity_two_passes_through(monkeypatch, scheduler):
    monkeypatch.setenv("ARAIL_INFERENCE_CONCURRENCY", "2")
    assert scheduler._capacity() == 2


# ---------------------------------------------------------------------------
# A1 — slot release on exception
# ---------------------------------------------------------------------------

def test_inference_slot_releases_on_exception(scheduler):
    """A1 mitigation: a raising body must not deadlock subsequent acquires."""

    async def _scenario():
        with pytest.raises(RuntimeError):
            async with scheduler.inference_slot("chat-default"):
                raise RuntimeError("boom")
        # If the slot leaked, the second acquire would deadlock.  Use a tight
        # timeout to fail loud instead of hanging the suite.
        async with asyncio.timeout(2.0):
            async with scheduler.inference_slot("chat-default"):
                pass

    asyncio.run(_scenario())


def test_inference_slot_releases_on_cancel(scheduler):
    """A1 corollary: cancellation while inside the slot still releases."""

    async def _scenario():
        async def _hold_then_cancel():
            async with scheduler.inference_slot("chat-default"):
                await asyncio.sleep(60)  # interrupted by cancel below

        task = asyncio.create_task(_hold_then_cancel())
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        # Subsequent acquire must succeed promptly.
        async with asyncio.timeout(2.0):
            async with scheduler.inference_slot("chat-default"):
                pass

    asyncio.run(_scenario())


# ---------------------------------------------------------------------------
# OBS6 — per-label counter sync
# ---------------------------------------------------------------------------

def test_per_label_counters_balanced_after_run(scheduler):
    """OBS6 mitigation: in-flight increment + decrement must net to zero."""

    async def _scenario():
        async with scheduler.inference_slot("chat-default"):
            pass
        async with scheduler.inference_slot("chat-default"):
            pass

    asyncio.run(_scenario())
    snap = scheduler.per_label_snapshot()
    assert snap["chat-default"]["in_flight"] == 0
    assert snap["chat-default"]["completed_total"] == 2


def test_per_label_counters_counts_each_label_separately(scheduler):
    async def _scenario():
        async with scheduler.inference_slot("agent-pip"):
            pass
        async with scheduler.inference_slot("chat-default"):
            pass
        async with scheduler.inference_slot("chat-default"):
            pass

    asyncio.run(_scenario())
    snap = scheduler.per_label_snapshot()
    assert snap["agent-pip"]["completed_total"] == 1
    assert snap["chat-default"]["completed_total"] == 2


def test_per_label_counters_balanced_after_exception(scheduler):
    """OBS6 + A1: exception must not skew per-label in_flight."""

    async def _scenario():
        with pytest.raises(ValueError):
            async with scheduler.inference_slot("chat-default"):
                raise ValueError("nope")

    asyncio.run(_scenario())
    snap = scheduler.per_label_snapshot()
    assert snap["chat-default"]["in_flight"] == 0
    # completed_total still increments because we use try/finally
    assert snap["chat-default"]["completed_total"] == 1


def test_aggregate_in_flight_balanced_after_exception(scheduler):
    """A1: aggregate _INFLIGHT must match per-label sum."""

    async def _scenario():
        with pytest.raises(RuntimeError):
            async with scheduler.inference_slot("chat-default"):
                raise RuntimeError()

    asyncio.run(_scenario())
    snap = scheduler.snapshot()
    assert snap["in_flight"] == 0
    assert snap["pending"] == 0


# ---------------------------------------------------------------------------
# Empty / unknown label normalisation
# ---------------------------------------------------------------------------

def test_empty_label_normalises_to_unknown(scheduler):
    async def _scenario():
        async with scheduler.inference_slot(""):
            pass

    asyncio.run(_scenario())
    snap = scheduler.per_label_snapshot()
    assert "_unknown" in snap


# ---------------------------------------------------------------------------
# A9 — FAST_PATH_PREFIXES guard against accidental chat inclusion
# ---------------------------------------------------------------------------

def test_fast_path_prefixes_does_not_include_chat(scheduler):
    """A9 mitigation: chat / agent ask MUST NOT be fast-pathed."""
    forbidden = ("/api/chat", "/api/agents/ask")
    for path in forbidden:
        # Direct membership is the design intent; substring check would let
        # a future "/api/chat-something" silently slip in too.
        assert path not in scheduler.FAST_PATH_PREFIXES, (
            f"{path} must NOT be in FAST_PATH_PREFIXES — chat must acquire the inference slot"
        )
        # Also assert no prefix in FAST_PATH_PREFIXES is itself a prefix of the chat path.
        for p in scheduler.FAST_PATH_PREFIXES:
            assert not path.startswith(p), (
                f"FAST_PATH_PREFIXES entry {p!r} prefixes chat-path {path!r} — "
                f"this would let chat traffic bypass the inference semaphore."
            )


# ---------------------------------------------------------------------------
# A7 — lazy semaphore init
# ---------------------------------------------------------------------------

def test_get_semaphore_initialises_on_first_call(scheduler):
    """A7: first inference_slot acquire must materialise the semaphore lazily."""
    assert scheduler._SEM is None  # fresh module

    async def _touch():
        async with scheduler.inference_slot("chat-default"):
            pass

    asyncio.run(_touch())
    assert scheduler._SEM is not None


# ---------------------------------------------------------------------------
# snapshot() shape
# ---------------------------------------------------------------------------

def test_snapshot_shape_keys_present(scheduler):
    snap = scheduler.snapshot()
    for k in ("capacity", "in_flight", "pending", "completed_5m",
              "wait_ms", "run_ms", "fast_path_ms"):
        assert k in snap, f"snapshot missing key {k!r}"
    assert isinstance(snap["wait_ms"], dict)
    assert isinstance(snap["run_ms"], dict)
    assert isinstance(snap["fast_path_ms"], dict)


def test_per_label_snapshot_empty_returns_empty_dict(scheduler):
    """Per-label snapshot on a fresh module must return an empty dict, not raise."""
    snap = scheduler.per_label_snapshot()
    assert snap == {}


def test_fast_path_record_never_raises(scheduler):
    # Should accept arbitrary positive / negative values without raising.
    scheduler.fast_path_record("/api/system/health", 0.42)
    scheduler.fast_path_record("/static/x.css", 99999.0)
    scheduler.fast_path_record("", -1.0)
    snap = scheduler.snapshot()
    assert snap["fast_path_ms"]["n"] == 3
