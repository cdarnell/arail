"""POST /api/experiments — the generic design-an-experiment input path.

Validates the hardened contract: CSRF envelope, hypothesis required,
variables must be a bounded JSON object, archetype must be one the engine
actually implements (never "unmeasured"), methodology/metrics default from
the engine's own tables. Runtime inputs like a benchmark command ride in
``variables`` — typed, per-user, never part of a World bundle.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import arail.portal.app as app_mod
from arail.portal.app import app
from arail.skills.experiment_tracker import ExperimentTracker


@pytest.fixture(autouse=True)
def _iso_tracker(tmp_path, monkeypatch):
    monkeypatch.setattr(app_mod, "tracker", ExperimentTracker(tmp_path / "exps"))


def _client():
    return TestClient(app, raise_server_exceptions=False)


def test_create_with_archetype_defaults_methodology_and_metrics():
    with _client() as c:
        r = c.post("/api/experiments", json={
            "hypothesis": "Lowering shadow quality improves my 1% lows",
            "archetype": "game_config_optimization",
            "variables": {
                "benchmark_command": ["python", "bench.py"],
                "game_tunables": {"shadow_quality": ["low", "medium", "high"]},
            },
        })
    assert r.status_code == 200
    exp = r.json()
    assert exp["variables"]["archetype"] == "game_config_optimization"
    # typed variables preserved verbatim — argv stays a list
    assert exp["variables"]["benchmark_command"] == ["python", "bench.py"]
    from arail.research import mini_experiments as mx
    assert exp["methodology"] == mx.ARCHETYPE_METHODOLOGY["game_config_optimization"]
    assert exp["metrics"] == mx.ARCHETYPE_METRICS["game_config_optimization"]


def test_hypothesis_required():
    with _client() as c:
        r = c.post("/api/experiments", json={"archetype": "model_throughput"})
    assert r.status_code == 400
    assert r.json()["error"] == "hypothesis_required"


def test_unknown_archetype_rejected_with_known_list():
    with _client() as c:
        r = c.post("/api/experiments", json={
            "hypothesis": "x", "archetype": "teleportation"})
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "unknown_archetype"
    assert "game_config_optimization" in body["known"]
    assert "unmeasured" not in body["known"]


def test_unmeasured_archetype_rejected():
    with _client() as c:
        r = c.post("/api/experiments", json={
            "hypothesis": "x", "archetype": "unmeasured"})
    assert r.status_code == 400


def test_variables_must_be_object():
    with _client() as c:
        r = c.post("/api/experiments", json={
            "hypothesis": "x", "variables": ["not", "a", "dict"]})
    assert r.status_code == 400
    assert r.json()["error"] == "variables_must_be_object"


def test_variables_size_cap():
    with _client() as c:
        r = c.post("/api/experiments", json={
            "hypothesis": "x", "variables": {"blob": "y" * 9000}})
    assert r.status_code == 400
    assert r.json()["error"] == "variables_too_large"


def test_cross_site_rejected():
    with _client() as c:
        r = c.post("/api/experiments",
                   json={"hypothesis": "x"},
                   headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403


def test_no_archetype_is_allowed_and_stays_unrouted():
    """An experiment without an archetype is legal — it records honestly as
    unmeasured when run, per the engine's contract."""
    with _client() as c:
        r = c.post("/api/experiments", json={"hypothesis": "free-form note"})
    assert r.status_code == 200
    assert "archetype" not in r.json()["variables"]
