"""No silent fallback: every degradation is a visible FallbackEvent."""

from __future__ import annotations

import time


def _mark_unhealthy(reg, entry_id, detail="connection refused"):
    from arail.registry.core import HealthState
    reg.entries[entry_id].health = HealthState(
        status="unhealthy", checked_at=time.time(),
        endpoint=reg.entries[entry_id].endpoint, detail=detail)


def test_reasoning_falls_back_to_fast_with_visible_event(tmp_registry):
    reg = tmp_registry
    _mark_unhealthy(reg, "tier1-aerollm", "runtime not initialized")

    res = reg.resolve("reasoning", tab="research")
    assert res.entry.id == "tier0-local"          # fell back
    assert res.requested.id == "tier1-aerollm"    # what was asked for
    ev = res.fallback
    assert ev is not None
    assert ev.from_id == "tier1-aerollm" and ev.to_id == "tier0-local"
    assert ev.reason == "unhealthy"
    assert "runtime not initialized" in ev.detail
    assert ev.status == "unhealthy"
    # The event is retained for the UI banner.
    assert any(e.from_id == "tier1-aerollm" for e in reg.recent_events)


def test_fast_down_is_structured_failure_not_silent_chain(tmp_registry):
    reg = tmp_registry
    _mark_unhealthy(reg, "tier0-local", "HTTP 503 from /models")

    res = reg.resolve("fast", tab="agents")
    assert res.entry is None                       # hard, structured failure
    assert res.requested.id == "tier0-local"
    assert res.fallback is not None
    assert res.fallback.to_id is None
    assert "503" in res.fallback.detail
    assert res.fallback.endpoint == "http://127.0.0.1:11434/v1"


def test_fallback_event_rides_activity_log(tmp_registry, monkeypatch):
    events = []
    from arail import activity
    monkeypatch.setattr(activity.activity_log, "emit",
                        lambda *a, **k: events.append((a, k)))
    reg = tmp_registry
    _mark_unhealthy(reg, "tier1-aerollm")
    reg.resolve("reasoning")
    assert any("model_event" in (a[3] if len(a) > 3 else k.get("data") or {})
               for a, k in events), events


def test_report_failure_flips_health_and_next_resolve_falls_back(tmp_registry):
    reg = tmp_registry
    assert reg.resolve("reasoning").entry.id == "tier1-aerollm"
    reg.report_failure("tier1-aerollm", ConnectionError("boom"))
    assert reg.entries["tier1-aerollm"].health.status == "unhealthy"
    res = reg.resolve("reasoning")
    assert res.entry.id == "tier0-local"
    assert res.fallback is not None


def test_report_success_recovers(tmp_registry):
    reg = tmp_registry
    reg.report_failure("tier1-aerollm", ConnectionError("boom"))
    reg.report_success("tier1-aerollm", latency_ms=42.0)
    assert reg.entries["tier1-aerollm"].health.status == "healthy"
    res = reg.resolve("reasoning")
    assert res.entry.id == "tier1-aerollm"
    assert res.fallback is None


def test_resolution_router_none_on_dead_entry_without_raising(tmp_registry):
    reg = tmp_registry
    _mark_unhealthy(reg, "tier0-local")
    res = reg.resolve("fast")
    assert res.entry is None
    assert res.router() is None        # never raises
