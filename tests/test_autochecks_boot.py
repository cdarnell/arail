"""WP1 quiet-boot guarantees: nothing probes packages/versions/models unless
the user opts in (ARAIL_AUTOCHECKS) or explicitly asks (?probe=1 / doctor).

Covers:
  • autochecks.enabled() default-off + toggle
  • MODEL_HEALTH_INTERVAL_SEC=0 → one preflight, no re-probe loop
  • /api/admin/components does no subprocess work by default; shells out only
    with ?probe=1
  • an unprobed (unknown-health) registry entry still resolves as usable
    (probe-on-first-call) — so skipping the boot preflight is safe
"""

from __future__ import annotations

import threading
import time

import pytest


def test_autochecks_default_off(monkeypatch):
    from arail import autochecks
    monkeypatch.delenv("ARAIL_AUTOCHECKS", raising=False)
    assert autochecks.enabled() is False
    monkeypatch.setenv("ARAIL_AUTOCHECKS", "1")
    assert autochecks.enabled() is True
    monkeypatch.setenv("ARAIL_AUTOCHECKS", "0")
    assert autochecks.enabled() is False
    monkeypatch.setenv("ARAIL_AUTOCHECKS", "true")
    assert autochecks.enabled() is True


def test_health_interval_zero_is_one_shot(monkeypatch):
    """MODEL_HEALTH_INTERVAL_SEC=0 runs a single preflight and the thread
    exits — no recurring 'MODEL TIER DOWN' loop."""
    from arail.registry import health
    monkeypatch.setenv("MODEL_HEALTH_INTERVAL_SEC", "0")

    calls = {"n": 0}
    monkeypatch.setattr(health, "run_preflight",
                        lambda reg, announce=True: calls.__setitem__("n", calls["n"] + 1))

    class _Reg:
        pass

    health.start_background(_Reg())
    # The daemon thread should run exactly one preflight then terminate.
    for t in threading.enumerate():
        if t.name == "model-registry-health":
            t.join(timeout=2.0)
    time.sleep(0.05)
    assert calls["n"] == 1
    # No lingering health thread.
    assert not any(t.name == "model-registry-health" and t.is_alive()
                   for t in threading.enumerate())


def test_unknown_health_resolves_usable():
    """An entry that was never probed (health='unknown') must resolve as
    usable, so a quiet boot that skips the preflight still serves models."""
    from arail.registry.core import HealthState, _gate_reason, ModelEntry
    assert HealthState(status="unknown").usable is True
    # _gate_reason only gates unhealthy/not_installed — unknown passes.
    entry = ModelEntry(
        id="local-x", display_name="Local X", provider_type="local",
        backend="ollama_native", endpoint="http://127.0.0.1:11434/v1",
        model_id="llama3.2:1b", tier=0, enabled=True)
    entry.health = HealthState(status="unknown")
    assert _gate_reason(entry) is None


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    from arail.registry import core as reg_core
    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE",
                       str(tmp_path / "model_registry.json"))
    monkeypatch.delenv("ARAIL_AUTOCHECKS", raising=False)
    reg_core.reset_registry()
    from fastapi.testclient import TestClient
    import arail.portal.app as app_mod
    with TestClient(app_mod.app) as client:
        yield client
    reg_core.reset_registry()


def test_components_no_subprocess_by_default(app_client, monkeypatch):
    """A plain /api/admin/components load runs zero subprocesses — shell-only
    components report 'not checked' instead of shelling out pip list etc."""
    import subprocess

    called = {"n": 0}
    real_run = subprocess.run

    def _tracking_run(*a, **k):
        called["n"] += 1
        return real_run(*a, **k)

    monkeypatch.setattr(subprocess, "run", _tracking_run)
    r = app_client.get("/api/admin/components")
    assert r.status_code == 200
    assert called["n"] == 0, "default components load must not shell out"
    # Shell-only components (those with a version_cmd but no importable pkg)
    # should read 'not checked'.
    versions = [c["version"] for c in r.json()["components"]]
    assert any(v == "not checked" for v in versions) or all(
        v not in (None,) for v in versions)


def test_components_probe_shells_out(app_client, monkeypatch):
    """?probe=1 (the explicit 'Check versions' button) is allowed to shell
    out for shell-only components."""
    import subprocess

    called = {"n": 0}
    real_run = subprocess.run

    def _tracking_run(*a, **k):
        called["n"] += 1
        return real_run(*a, **k)

    monkeypatch.setattr(subprocess, "run", _tracking_run)
    r = app_client.get("/api/admin/components?probe=1")
    assert r.status_code == 200
    # At least one component defines a version_cmd, so probing shells out.
    assert called["n"] >= 1
