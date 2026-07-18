"""MODEL BUILDING tab: tier gating, preflight gate, mode gating, jobs merge."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    from arail.registry import core as reg_core

    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE",
                       str(tmp_path / "model_registry.json"))
    monkeypatch.setenv("ARAIL_BUILD_JOBS_FILE",
                       str(tmp_path / "build_jobs.json"))
    monkeypatch.setenv("NUCLEUS_CONFIGS_DIR", str(tmp_path / "configs"))
    monkeypatch.setenv("LAB_MODE", "airgapped")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    reg_core.reset_registry()

    # Pin capacity so preflight verdicts are deterministic.
    from arail.build import preflight
    monkeypatch.setattr(preflight, "_capacity", lambda: {
        "ram_gb": 32.0, "vram_gb": 24.0, "disk_gb": 200.0})

    import arail.portal.app as app_mod
    with TestClient(app_mod.app) as c:
        yield c
    reg_core.reset_registry()


@pytest.fixture
def fake_nucleus(monkeypatch):
    """Wire the build API's client factory to an in-memory orchestrator."""
    from arail.build.nucleus_client import NucleusHealth
    from arail.portal import build_api

    class _FakeClient:
        runs: dict = {}
        started: list = []

        def health(self):
            return NucleusHealth(up=True, url="http://127.0.0.1:18000",
                                 latency_ms=3.0)

        def start(self, run_id, manifest_path, dry_run=False):
            _FakeClient.started.append((run_id, manifest_path, dry_run))
            _FakeClient.runs[run_id] = {"run_id": run_id, "status": "started",
                                        "current_phase": "init",
                                        "dry_run": dry_run}
            return _FakeClient.runs[run_id]

        def status(self, run_id):
            return _FakeClient.runs[run_id]

        def trainer_progress(self):
            return {"epoch": 0, "step": 1, "total_steps": 10,
                    "loss": 3.2, "tokens_per_sec": 400}

        def list(self):
            return {"runs": list(_FakeClient.runs.values())}

    _FakeClient.runs = {}
    _FakeClient.started = []
    monkeypatch.setattr(build_api, "_client", lambda: _FakeClient())
    return _FakeClient


_GOOD_SPEC = {"params_b": 3.0, "precision": "q4", "method": "lora",
              "base_checkpoint": "mlx-community/Qwen2.5-3B-Instruct-4bit",
              "dataset_tokens_est": 1_000_000}
_RED_SPEC = {"params_b": 20.0, "precision": "bf16", "method": "full",
             "base_checkpoint": "x/base", "dataset_tokens_est": 1_000_000}


def test_build_page_gated_by_tier(client, monkeypatch):
    import arail.tier
    monkeypatch.setattr(arail.tier, "get_current_tier", lambda: "maximus")
    r = client.get("/build")
    assert r.status_code == 200
    assert "Model Building" in r.text
    assert "Anthropix" in r.text

    monkeypatch.setattr(arail.tier, "get_current_tier", lambda: "minimalist")
    nav = client.get("/").text
    assert "/build" not in nav


def test_preflight_endpoint_and_anthropix_lock(client):
    r = client.post("/api/build/preflight", json={"spec": _GOOD_SPEC})
    assert r.status_code == 200
    body = r.json()
    assert body["report"]["overall"] in ("green", "amber")
    anthropix = next(m for m in body["modes"] if m["mode"] == "anthropix")
    assert anthropix["available"] is False        # airgapped
    assert "airgapped" in anthropix["reason"]     # locked WITH visible copy
    assert anthropix["est_cost_usd"] > 0


def test_start_dry_run_maps_to_nucleus_dry_run(client, fake_nucleus):
    r = client.post("/api/build/start", json={
        "run_id": "qkz-dry-1", "mode": "dry_run", "spec": _GOOD_SPEC})
    assert r.status_code == 200, r.text
    assert fake_nucleus.started == [
        ("qkz-dry-1", "configs/arail-generated/qkz-dry-1.yaml", True)]
    assert r.json()["job"]["dry_run"] is True


def test_red_preflight_blocks_without_override(client, fake_nucleus):
    r = client.post("/api/build/start", json={
        "run_id": "qkz-red-1", "mode": "local", "spec": _RED_SPEC})
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "preflight_red"
    assert fake_nucleus.started == []

    r = client.post("/api/build/start", json={
        "run_id": "qkz-red-1", "mode": "local", "spec": _RED_SPEC,
        "override_red": True})
    assert r.status_code == 200
    assert r.json()["job"]["override_red"] is True


def test_anthropix_mode_locked_while_airgapped_is_409_not_500(client,
                                                              fake_nucleus):
    r = client.post("/api/build/start", json={
        "run_id": "qkz-acc-1", "mode": "anthropix", "spec": _GOOD_SPEC})
    assert r.status_code == 409
    assert "airgapped" in r.json()["detail"]
    assert fake_nucleus.started == []


def test_anthropix_mode_allowed_hybrid_with_key(client, fake_nucleus,
                                                monkeypatch, tmp_path):
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    r = client.post("/api/build/start", json={
        "run_id": "qkz-acc-2", "mode": "anthropix", "spec": _GOOD_SPEC})
    assert r.status_code == 200, r.text
    # The generated manifest routes the teacher tier through Claude.
    import yaml
    manifest = yaml.safe_load(
        (tmp_path / "configs" / "arail-generated" / "qkz-acc-2.yaml").read_text())
    assert manifest["models"]["teacher_tier1"].startswith("claude-")
    assert manifest["arail_extensions"]["build_mode"] == "anthropix"


def test_invalid_run_id_rejected(client, fake_nucleus):
    r = client.post("/api/build/start", json={
        "run_id": "bad id!", "mode": "local", "spec": _GOOD_SPEC})
    assert r.status_code == 400


def test_jobs_merge_status_and_trainer(client, fake_nucleus):
    client.post("/api/build/start", json={
        "run_id": "qkz-j1", "mode": "local", "spec": _GOOD_SPEC})
    r = client.get("/api/build/jobs")
    assert r.status_code == 200
    body = r.json()
    assert body["nucleus"]["up"] is True
    assert body["trainer"]["loss"] == 3.2
    job = next(j for j in body["jobs"] if j["run_id"] == "qkz-j1")
    assert job["phase"] == "init"
    assert job["preflight"]["overall"] in ("green", "amber")


# ── World-corpus build path ──────────────────────────────────────────

@pytest.fixture
def sync_thread(monkeypatch):
    """Run the World-build's background thread synchronously so tests are
    deterministic — no real threading, no waiting/polling for completion."""
    from arail.portal import build_api

    class _SyncThread:
        def __init__(self, target=None, name=None, daemon=None):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(build_api.threading, "Thread", _SyncThread)


@pytest.fixture
def fake_world_corpus(monkeypatch):
    """Fake arail.build.world_corpus.build_world_corpus — avoids any real
    network call to Synthesizer/Trainer."""
    import arail.build.world_corpus as wc_mod
    calls = []

    def _fake(world_slug, run_id, *, categories, tier2_categories,
              student_model, job_store, **kw):
        calls.append({"world_slug": world_slug, "run_id": run_id,
                      "categories": list(categories),
                      "tier2_categories": list(tier2_categories)})
        job_store.update(run_id, phase="train")
        return {"world_slug": world_slug, "categories": list(categories),
               "tier2_categories": list(tier2_categories),
               "term_count": 5, "record_count": 5,
               "train_result": {"status": "started"}}

    monkeypatch.setattr(wc_mod, "build_world_corpus", _fake)
    return calls


def test_world_build_start_launches_and_completes(client, sync_thread,
                                                   fake_world_corpus):
    r = client.post("/api/build/world/start", json={
        "run_id": "photo-1", "world_slug": "photography",
        "categories": ["exposure", "light"]})
    assert r.status_code == 200, r.text
    assert fake_world_corpus == [{
        "world_slug": "photography", "run_id": "photo-1",
        "categories": ["exposure", "light"], "tier2_categories": []}]

    job = client.get("/api/build/jobs").json()
    row = next(j for j in job["jobs"] if j["run_id"] == "photo-1")
    assert row["mode"] == "world_corpus"
    assert row["phase"] == "completed"          # sync thread already ran
    assert row["result"]["record_count"] == 5


def test_world_build_default_categories_when_omitted(client, sync_thread,
                                                      fake_world_corpus):
    from arail.build.world_corpus import CRAFT_CATEGORIES
    client.post("/api/build/world/start", json={
        "run_id": "photo-2", "world_slug": "photography"})
    assert fake_world_corpus[0]["categories"] == list(CRAFT_CATEGORIES)


def test_world_build_duplicate_run_id_conflicts(client, sync_thread,
                                                fake_world_corpus):
    client.post("/api/build/world/start",
                json={"run_id": "photo-3", "world_slug": "photography"})
    r = client.post("/api/build/world/start",
                    json={"run_id": "photo-3", "world_slug": "photography"})
    assert r.status_code == 409


def test_world_build_bad_run_id_rejected(client):
    r = client.post("/api/build/world/start",
                    json={"run_id": "bad id!", "world_slug": "photography"})
    assert r.status_code == 400


def test_world_build_failure_recorded_on_job(client, sync_thread, monkeypatch):
    import arail.build.world_corpus as wc_mod

    def _boom(*a, **k):
        raise ValueError("no approved terms found")
    monkeypatch.setattr(wc_mod, "build_world_corpus", _boom)

    r = client.post("/api/build/world/start",
                    json={"run_id": "photo-4", "world_slug": "photography"})
    assert r.status_code == 200            # launch itself always succeeds
    job = client.get("/api/build/jobs").json()
    row = next(j for j in job["jobs"] if j["run_id"] == "photo-4")
    assert row["phase"] == "failed"
    assert "no approved terms" in row["error"]


def test_jobs_endpoint_never_polls_orchestrator_for_world_corpus_jobs(
        client, fake_nucleus):
    """Regression: world_corpus jobs have no orchestrator run_id — polling
    client.status() for one would always 404 and get misdiagnosed as
    'lost' by the not_found-handling block."""
    from arail.build.jobs import BuildJobStore
    BuildJobStore().create("photo-5", mode="world_corpus",
                           manifest_path="world:photography",
                           preflight=None, override_red=False, dry_run=False)
    BuildJobStore().update("photo-5", phase="synthesize_tier1")

    r = client.get("/api/build/jobs")
    body = r.json()
    assert "photo-5" not in body["statuses"]     # never polled
    row = next(j for j in body["jobs"] if j["run_id"] == "photo-5")
    assert row["phase"] == "synthesize_tier1"    # NOT marked "lost"


def test_build_detail_returns_job_only_for_world_corpus_mode(client, fake_nucleus):
    from arail.build.jobs import BuildJobStore
    BuildJobStore().create("photo-6", mode="world_corpus",
                           manifest_path="world:photography",
                           preflight=None, override_red=False, dry_run=False)
    BuildJobStore().update("photo-6", phase="synthesize_tier2",
                           synth_progress={"tier": 2, "batch": 1, "of": 2})

    r = client.get("/api/build/photo-6/detail")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] is None and body["events"] == []
    assert body["graduation"] is None and body["seal"] is None
    assert body["job"]["phase"] == "synthesize_tier2"
    assert body["job"]["synth_progress"]["batch"] == 1
    # No orchestrator status/events/graduation/seal calls were made for it.
    assert "photo-6" not in fake_nucleus.runs


def test_build_page_renders_world_corpus_section(client, monkeypatch):
    import arail.tier
    monkeypatch.setattr(arail.tier, "get_current_tier", lambda: "maximus")
    r = client.get("/build")
    assert r.status_code == 200
    assert "World-sourced build" in r.text
    assert "bxw-start-btn" in r.text
    assert "bxw-world" in r.text
