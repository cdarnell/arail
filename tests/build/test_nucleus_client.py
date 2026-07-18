"""NucleusClient against a fake orchestrator (requests-level monkeypatch)."""

from __future__ import annotations

import json

import pytest

from arail.build.nucleus_client import NucleusClient


class _FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body if body is not None else {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


class _FakeSession:
    """Mimics the nucleus orchestrator's /pipeline/* surface."""

    def __init__(self):
        self.runs = {}
        self.requests = []

    def get(self, url, headers=None, timeout=None):
        self.requests.append(("GET", url, headers))
        if url.endswith("/pipeline/list"):
            return _FakeResponse(200, {"runs": list(self.runs.values())})
        if "/pipeline/" in url and url.endswith("/events"):
            return _FakeResponse(200, [{"phase": "init"}, {"phase": "kice"}])
        if url.endswith("/status"):   # trainer
            return _FakeResponse(200, {"epoch": 1, "step": 10,
                                       "total_steps": 100, "loss": 2.31,
                                       "tokens_per_sec": 512})
        run_id = url.rstrip("/").split("/")[-1]
        if run_id in self.runs:
            return _FakeResponse(200, self.runs[run_id])
        return _FakeResponse(404, {"detail": "unknown run"})

    def post(self, url, headers=None, json=None, timeout=None):
        self.requests.append(("POST", url, headers, json))
        if url.endswith("/pipeline/start"):
            if not headers.get("X-API-Key"):
                return _FakeResponse(401, {"detail": "missing key"})
            rid = json["run_id"]
            if rid in self.runs:
                return _FakeResponse(409, {"detail": "duplicate run"})
            self.runs[rid] = {"run_id": rid, "status": "started",
                              "dry_run": json.get("dry_run", False),
                              "current_phase": "init"}
            return _FakeResponse(200, self.runs[rid])
        return _FakeResponse(200, {"ok": True})


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NUCLEUS_API_KEY", "test-key")
    c = NucleusClient(orchestrator_url="http://127.0.0.1:18000",
                      trainer_url="http://127.0.0.1:18006")
    fake = _FakeSession()
    c._session = fake
    return c, fake


def test_health_up_and_shape_checked(client):
    c, fake = client
    h = c.health()
    assert h.up and h.latency_ms is not None


def test_health_rejects_non_nucleus_service(client):
    c, fake = client
    orig_get = fake.get
    fake.get = lambda url, **k: _FakeResponse(200, {"object": "list",
                                                    "data": []})  # vLLM-ish
    h = c.health()
    assert not h.up
    assert "not the nucleus orchestrator" in h.detail


def test_health_down_carries_error_and_url(client):
    c, fake = client

    def _boom(url, **k):
        raise ConnectionError("refused")
    fake.get = _boom
    h = c.health()
    assert not h.up
    assert "refused" in h.detail
    assert h.url == "http://127.0.0.1:18000"


def test_start_sends_auth_and_dry_run_echo(client):
    c, fake = client
    out = c.start("run-1", "configs/arail-generated/run-1.yaml", dry_run=True)
    assert out["dry_run"] is True
    method, url, headers, body = fake.requests[-1]
    assert headers["X-API-Key"] == "test-key"
    assert body["superskill_manifest_path"].startswith("configs/")


def test_duplicate_run_raises(client):
    c, fake = client
    c.start("run-1", "configs/x.yaml")
    with pytest.raises(RuntimeError, match="409"):
        c.start("run-1", "configs/x.yaml")


def test_status_events_trainer(client):
    c, fake = client
    c.start("run-2", "configs/x.yaml")
    assert c.status("run-2")["current_phase"] == "init"
    assert len(c.events("run-2")) == 2
    prog = c.trainer_progress()
    assert prog["loss"] == 2.31 and prog["tokens_per_sec"] == 512
