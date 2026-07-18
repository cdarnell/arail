"""Startup preflight: loud, non-blocking, and never loads aerollm weights."""

from __future__ import annotations

from arail.registry import health
from arail.registry.core import HealthState


def _fake_probe(status_map):
    def _probe(entry):
        return HealthState(status=status_map.get(entry.id, "unknown"),
                           latency_ms=12.0, checked_at=1.0,
                           endpoint=entry.endpoint,
                           detail=status_map.get(entry.id + "_detail", ""))
    return _probe


def _events(monkeypatch):
    captured = []
    from arail import activity
    monkeypatch.setattr(activity.activity_log, "emit",
                        lambda *a, **k: captured.append(a))
    return captured


def test_both_tiers_healthy_emits_success_summary(tmp_registry, monkeypatch):
    events = _events(monkeypatch)
    monkeypatch.setattr(health, "probe_entry", _fake_probe(
        {"tier0-local": "healthy", "tier1-aerollm": "cold"}))
    health.run_preflight(tmp_registry)
    ready = [e for e in events if "Model tiers ready" in e[1]]
    assert ready, events
    assert "ai-engineer" in ready[0][1]
    assert "cold" in ready[0][1]           # cold is reported, and is healthy


def test_tier_down_warns_loudly_with_endpoint(tmp_registry, monkeypatch):
    events = _events(monkeypatch)
    monkeypatch.setattr(health, "probe_entry", _fake_probe(
        {"tier0-local": "unhealthy",
         "tier0-local_detail": "ConnectionError: refused",
         "tier1-aerollm": "cold"}))
    health.run_preflight(tmp_registry)
    warns = [e for e in events if "MODEL TIER DOWN" in e[1]]
    assert warns, events
    assert "11434" in warns[0][1]          # names the endpoint
    assert "refused" in warns[0][1]        # and the actual error


def test_preflight_never_constructs_aerollm_backend(tmp_registry, monkeypatch):
    from arail.router.backends import AeroLLMBackend
    constructed = []
    orig_new = AeroLLMBackend.__new__
    monkeypatch.setattr(
        AeroLLMBackend, "__new__",
        lambda cls, *a, **k: (constructed.append(1), orig_new(cls))[1])
    # Real probes (no fakes): HTTP probes fail fast against nothing.
    health.run_preflight(tmp_registry, announce=False)
    assert constructed == []
    # aerollm entry got a real derived state, not a constructed runtime.
    assert tmp_registry.entries["tier1-aerollm"].health.status in (
        "unhealthy", "not_installed", "cold", "healthy")


def test_start_background_returns_immediately(tmp_registry, monkeypatch):
    import time
    monkeypatch.setattr(health, "run_preflight",
                        lambda reg, announce=True: time.sleep(0.2))
    t0 = time.monotonic()
    tmp_registry.start_background()
    assert time.monotonic() - t0 < 0.15    # preflight runs on the daemon thread
