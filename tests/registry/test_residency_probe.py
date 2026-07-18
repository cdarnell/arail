"""Tier-0 residency: /api/ps distinguishes resident from server-up-but-cold."""

from __future__ import annotations

from arail.registry import health


class _Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def json(self):
        return self._body


def _fake_requests(monkeypatch, *, models_ok=True, ps_body=None, ps_status=200):
    def _get(url, timeout=None):
        if url.endswith("/models"):
            if not models_ok:
                raise ConnectionError("refused")
            return _Resp(200, {"data": [{"id": "ai-engineer:latest"}]})
        if url.endswith("/api/ps"):
            if ps_body is None:
                return _Resp(ps_status, {})
            return _Resp(ps_status, ps_body)
        raise AssertionError(f"unexpected url {url}")

    import requests
    monkeypatch.setattr(requests, "get", _get)


def _tier0(reg):
    return reg.entries["tier0-local"]


def test_resident_model_is_healthy_resident(tmp_registry, monkeypatch):
    _fake_requests(monkeypatch,
                   ps_body={"models": [{"name": "ai-engineer:latest"}]})
    state = health.probe_entry(_tier0(tmp_registry))
    assert state.status == "healthy"
    assert state.detail == "resident"


def test_server_up_model_unloaded_is_cold(tmp_registry, monkeypatch):
    _fake_requests(monkeypatch, ps_body={"models": []})
    state = health.probe_entry(_tier0(tmp_registry))
    assert state.status == "cold"
    assert "not loaded" in state.detail


def test_ps_error_falls_back_to_plain_healthy(tmp_registry, monkeypatch):
    _fake_requests(monkeypatch, ps_status=500)
    state = health.probe_entry(_tier0(tmp_registry))
    assert state.status == "healthy"          # can't tell ≠ cold
    assert state.detail != "resident"


def test_server_down_still_unhealthy(tmp_registry, monkeypatch):
    _fake_requests(monkeypatch, models_ok=False)
    state = health.probe_entry(_tier0(tmp_registry))
    assert state.status == "unhealthy"


def test_warming_mark_overrides_and_expires(tmp_registry, monkeypatch):
    _fake_requests(monkeypatch, ps_body={"models": []})
    entry = _tier0(tmp_registry)
    health.mark_warming(entry.id)
    try:
        state = health.probe_entry(entry)
        assert state.status == "warming"
        assert state.usable
        # Stale marks self-clear.
        health._WARMING[entry.id] -= health._WARMING_STALE_SEC + 1
        assert health.probe_entry(entry).status == "cold"
    finally:
        health.clear_warming(entry.id)
