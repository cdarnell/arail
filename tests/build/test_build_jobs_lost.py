"""A nucleus restart that forgot a run marks the job LOST — never frozen."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ARAIL_BUILD_JOBS_FILE", str(tmp_path / "jobs.json"))
    import arail.portal.app as app_mod
    with TestClient(app_mod.app) as c:
        yield c


@pytest.fixture
def fake_nucleus(monkeypatch):
    from arail.build.nucleus_client import NucleusHealth
    from arail.portal import build_api

    class _FakeClient:
        forget = False

        def health(self):
            return NucleusHealth(up=True, url="http://127.0.0.1:18000",
                                 latency_ms=2.0)

        def status(self, run_id):
            if _FakeClient.forget:
                return {"status": "not_found"}
            return {"run_id": run_id, "status": "running",
                    "current_phase": "train"}

        def trainer_progress(self):
            return None

    _FakeClient.forget = False
    monkeypatch.setattr(build_api, "_client", lambda: _FakeClient())
    return _FakeClient


def test_forgotten_run_goes_lost_and_persists(client, fake_nucleus):
    from arail.build.jobs import BuildJobStore
    BuildJobStore().create("qkz-l1", mode="local", manifest_path="configs/x.yaml",
                           preflight=None, override_red=False, dry_run=False)

    body = client.get("/api/build/jobs").json()
    job = next(j for j in body["jobs"] if j["run_id"] == "qkz-l1")
    assert job["phase"] == "train"                 # live linkage first

    fake_nucleus.forget = True                     # nucleus restarted
    body = client.get("/api/build/jobs").json()
    job = next(j for j in body["jobs"] if j["run_id"] == "qkz-l1")
    assert job["phase"] == "lost"
    assert "no longer knows" in job["lost_reason"]
    assert BuildJobStore().get("qkz-l1")["phase"] == "lost"   # persisted

    # Terminal: no further status polls for lost jobs.
    body = client.get("/api/build/jobs").json()
    assert "qkz-l1" not in body["statuses"]


def test_client_status_404_returns_not_found():
    from arail.build.nucleus_client import NucleusClient

    class _S:
        def get(self, url, headers=None, timeout=None):
            raise RuntimeError("HTTP 404")

    c = NucleusClient(orchestrator_url="http://127.0.0.1:18000")
    c._session = _S()
    assert c.status("gone")["status"] == "not_found"
