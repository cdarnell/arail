"""Unit tests for src/arail/runtime_profile.py."""

from __future__ import annotations

import time

import pytest

from arail import runtime_profile as rp


@pytest.fixture(autouse=True)
def _reset_state(tmp_path, monkeypatch):
    """Each test runs against a fresh on-disk state file and a clean module."""
    monkeypatch.setattr(rp, "_STATE_PATH", tmp_path / "runtime_profile.json")
    rp._reset_for_tests()
    yield
    rp._reset_for_tests()


def test_resolver_default_balanced(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    profile, source = rp.resolve()
    assert profile == "balanced"
    assert source == "default"


def test_resolver_heavy_window_throughput(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "heavy")
    profile, source = rp.resolve()
    assert profile == "throughput"
    assert source == "window"


def test_resolver_presence_overrides_window(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "heavy")
    rp.mark_presence()
    profile, source = rp.resolve()
    assert profile == "interactive"
    assert source == "presence"


def test_override_wins_over_presence(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "active")
    rp.mark_presence()
    rp.set_override("throughput")
    profile, source = rp.resolve()
    assert profile == "throughput"
    assert source == "override"


def test_override_expiry_falls_through(monkeypatch):
    """A 1-second override expires; resolver falls through and persists the clear."""
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    rp.set_override("interactive", ttl_sec=1)

    # Within TTL: override wins
    profile, source = rp.resolve()
    assert profile == "interactive"
    assert source == "override"

    # Walk the override's set_at backward by 2 seconds to simulate expiry
    # without a real sleep (keeps the test fast and deterministic).
    rp._override["set_at"] = time.time() - 2.0

    profile, source = rp.resolve()
    assert profile == "balanced"
    assert source == "default"

    # And it was persisted as cleared
    assert rp._override is None
    payload = rp._STATE_PATH.read_text()
    assert '"override": null' in payload


def test_params_table_completeness():
    required_keys = {
        "airllm_max_tokens_cap",
        "inference_concurrency",
        "autoresearch",
        "aerollm_ring_depth",
        "aerollm_batch",
    }
    for profile in ("interactive", "balanced", "throughput"):
        p = rp.params(profile)
        assert required_keys <= set(p.keys()), f"{profile} missing keys: {required_keys - set(p.keys())}"


def test_params_invalid_profile_raises():
    with pytest.raises(ValueError):
        rp.params("aggressive")  # type: ignore[arg-type]


def test_set_override_invalid_profile_raises():
    with pytest.raises(ValueError):
        rp.set_override("aggressive")  # type: ignore[arg-type]


def test_set_override_persists_to_disk(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    rp.set_override("throughput", ttl_sec=600)
    assert rp._STATE_PATH.exists()
    # Force a fresh "load from disk" by wiping in-memory and resetting _loaded
    rp._override = None
    rp._loaded = False
    profile, source = rp.resolve()
    assert profile == "throughput"
    assert source == "override"


def test_clear_override_persists(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "idle")
    rp.set_override("interactive")
    rp.clear_override()
    profile, source = rp.resolve()
    assert profile == "balanced"
    assert source == "default"


def test_snapshot_shape(monkeypatch):
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "heavy")
    rp.set_override("interactive", ttl_sec=1800)
    rp.mark_presence()

    snap = rp.snapshot()
    assert snap["profile"] == "interactive"
    assert snap["source"] == "override"
    assert snap["window"] == "heavy"
    assert snap["override_profile"] == "interactive"
    assert isinstance(snap["override_expires_in_sec"], int)
    assert snap["override_expires_in_sec"] > 1700  # Just-set, near TTL
    assert snap["last_presence_sec_ago"] is not None
    assert snap["last_presence_sec_ago"] >= 0
    assert "params" in snap
    assert snap["params"]["airllm_max_tokens_cap"] == 256


def test_presence_idle_threshold(monkeypatch):
    """Presence older than PRESENCE_IDLE_SEC stops counting as active."""
    monkeypatch.setattr(rp, "current_window", lambda *a, **kw: "heavy")
    monkeypatch.setenv("ARAIL_PRESENCE_IDLE_SEC", "10")
    rp.mark_presence(now=time.time() - 60)  # Stale presence

    profile, source = rp.resolve()
    # Stale presence shouldn't win — falls through to the heavy window
    assert profile == "throughput"
    assert source == "window"
