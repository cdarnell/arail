"""BuildJobStore needs zero changes to support mode='world_corpus' — it
already accepts freeform preflight dicts and arbitrary update() kwargs."""

from __future__ import annotations

import pytest

from arail.build.jobs import BuildJobStore


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setenv("ARAIL_BUILD_JOBS_FILE", str(tmp_path / "jobs.json"))
    return BuildJobStore()


def test_create_with_world_corpus_mode(store):
    job = store.create(
        "run-1", mode="world_corpus", manifest_path="world:photography",
        preflight={"world_slug": "photography", "categories": ["exposure"]},
        override_red=False, dry_run=False)
    assert job["mode"] == "world_corpus"
    assert job["preflight"]["world_slug"] == "photography"


def test_update_accepts_freeform_progress_fields(store):
    store.create("run-2", mode="world_corpus", manifest_path="world:x",
                preflight=None, override_red=False, dry_run=False)
    updated = store.update("run-2", phase="synthesize_tier1",
                           synth_progress={"tier": 1, "batch": 3, "of": 9},
                           world_slug="x", categories=["exposure"])
    assert updated["phase"] == "synthesize_tier1"
    assert updated["synth_progress"]["batch"] == 3
    assert updated["world_slug"] == "x"

    # Round-trips through the store, not just the in-memory dict.
    reloaded = store.get("run-2")
    assert reloaded["synth_progress"]["of"] == 9


def test_list_sorts_world_corpus_jobs_alongside_orchestrator_jobs(store):
    store.create("orch-1", mode="local", manifest_path="configs/x.yaml",
                preflight=None, override_red=False, dry_run=False)
    store.create("world-1", mode="world_corpus", manifest_path="world:x",
                preflight=None, override_red=False, dry_run=False)
    jobs = store.list()
    assert {j["run_id"] for j in jobs} == {"orch-1", "world-1"}
