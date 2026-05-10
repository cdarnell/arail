"""Tests for the Metal/MLX memory-safety layer.

Two layers cover the Metal OOM that historically nuked the lab:
  * ``arail.router.mlx_guard`` — cheap pre-flight + cache eviction.
    Refuses risky calls before they hit the allocator.
  * ``arail.skills.goal_parser._subprocess_runner`` — process
    isolation for the parser LLM call. A subprocess crash
    (uncatchable C++ Metal exception) leaves the parent alive.

Tests below avoid actually loading MLX — they mock the relevant
surface so the suite runs fast on every platform.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


# ── mlx_guard pre-flight ──────────────────────────────────────────────────

def test_clear_metal_cache_is_noop_without_mlx(monkeypatch):
    """Without MLX installed the helper must return False, never raise."""
    from arail.router import mlx_guard
    monkeypatch.setattr(mlx_guard, "_mlx_module", lambda: None)
    assert mlx_guard.clear_metal_cache() is False


def test_metal_memory_pressure_returns_none_without_mlx(monkeypatch):
    from arail.router import mlx_guard
    monkeypatch.setattr(mlx_guard, "_mlx_module", lambda: None)
    assert mlx_guard.metal_memory_pressure() is None


def test_assert_metal_safe_passes_when_mlx_unavailable(monkeypatch):
    """Non-MLX installs must not be penalized — the guard treats
    'unmeasurable' as 'safe to proceed'."""
    from arail.router import mlx_guard
    monkeypatch.setattr(mlx_guard, "_mlx_module", lambda: None)
    mlx_guard.assert_metal_safe(op="test")  # no raise


def test_assert_metal_safe_raises_when_threshold_exceeded(monkeypatch):
    """When pressure reads above the configurable threshold the guard
    must raise MetalOutOfMemory — not let the call through."""
    from arail.router import mlx_guard

    monkeypatch.setattr(mlx_guard, "clear_metal_cache", lambda: True)
    monkeypatch.setattr(mlx_guard, "metal_memory_pressure", lambda: 0.92)
    monkeypatch.setenv("ARAIL_MLX_MEMORY_GUARD_PCT", "0.85")

    with pytest.raises(mlx_guard.MetalOutOfMemory) as exc:
        mlx_guard.assert_metal_safe(op="MLX generate(test)")
    assert exc.value.pressure == pytest.approx(0.92)
    assert "92%" in str(exc.value)


def test_assert_metal_safe_passes_when_below_threshold(monkeypatch):
    from arail.router import mlx_guard

    monkeypatch.setattr(mlx_guard, "clear_metal_cache", lambda: True)
    monkeypatch.setattr(mlx_guard, "metal_memory_pressure", lambda: 0.40)
    mlx_guard.assert_metal_safe(op="MLX generate(test)")  # no raise


def test_guard_threshold_clamps_to_safe_range(monkeypatch):
    """Tunable but bounded — too-low or too-high values clamp to
    [0.5, 0.99] so a typo can't disable the guard or starve the lab."""
    from arail.router import mlx_guard
    monkeypatch.setenv("ARAIL_MLX_MEMORY_GUARD_PCT", "0.05")
    assert mlx_guard._guard_threshold() == 0.5
    monkeypatch.setenv("ARAIL_MLX_MEMORY_GUARD_PCT", "1.5")
    assert mlx_guard._guard_threshold() == 0.99
    monkeypatch.setenv("ARAIL_MLX_MEMORY_GUARD_PCT", "garbage")
    assert mlx_guard._guard_threshold() == 0.75  # default


def test_safely_clears_cache_after_call(monkeypatch):
    """The convenience wrapper must clear AFTER the call too —
    otherwise activations from the just-completed pass make the
    next pre-check wrongly refuse."""
    from arail.router import mlx_guard

    cleared: list[str] = []
    monkeypatch.setattr(
        mlx_guard, "clear_metal_cache",
        lambda: cleared.append("cleared") or True,
    )
    monkeypatch.setattr(mlx_guard, "metal_memory_pressure", lambda: 0.30)

    result = mlx_guard.safely(lambda x: x * 2, 3, op="test")
    assert result == 6
    # One clear from assert_metal_safe + one from the safely() finally.
    assert len(cleared) == 2


# ── Subprocess runner protocol ────────────────────────────────────────────

def _runner_path() -> str:
    return "arail.skills.goal_parser._subprocess_runner"


def test_subprocess_runner_returns_error_on_empty_input():
    proc = subprocess.run(
        [sys.executable, "-m", _runner_path()],
        input="",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "missing prompt" in payload["error"]


def test_subprocess_runner_returns_error_on_bad_json():
    proc = subprocess.run(
        [sys.executable, "-m", _runner_path()],
        input="{ this is not json",
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0
    payload = json.loads(proc.stdout)
    assert payload["ok"] is False
    assert "bad input" in payload["error"]


# ── Goal parser subprocess fallback ───────────────────────────────────────

def test_parser_falls_back_to_heuristic_when_subprocess_crashes(monkeypatch):
    """The whole point of the isolation: even when the subprocess
    dies non-zero (Metal C++ OOM, segfault), parse() must return a
    sensible heuristic dict, not raise."""
    from arail.skills.goal_parser import GoalParser

    # Force a "subprocess died" simulation by pointing at a script
    # that exits 137 (SIGKILL — what an OOM-killed process looks like).
    # We do this by monkey-patching subprocess.run inside the module.
    import arail.skills.goal_parser as gp_mod

    class FakeCompleted:
        returncode = 137
        stdout = ""
        stderr = "Killed"

    monkeypatch.setattr(
        gp_mod.subprocess, "run", lambda *a, **kw: FakeCompleted()
    )

    parser = GoalParser()
    result = parser.parse("Improve AirLLM throughput on my MacBook")
    # Heuristic output has these baseline keys.
    assert "domain" in result
    assert "primary_objective" in result
    assert "extracted_entities" in result
    assert "confidence" in result


def test_parser_falls_back_when_subprocess_times_out(monkeypatch):
    from arail.skills.goal_parser import GoalParser
    import arail.skills.goal_parser as gp_mod

    def fake_run(*a, **kw):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1)

    monkeypatch.setattr(gp_mod.subprocess, "run", fake_run)

    parser = GoalParser()
    result = parser.parse("Improve AirLLM throughput on my MacBook")
    assert "domain" in result
    assert result.get("primary_objective")


def test_parser_uses_subprocess_text_on_success(monkeypatch):
    """When the subprocess returns valid JSON, parse() incorporates it."""
    from arail.skills.goal_parser import GoalParser
    import arail.skills.goal_parser as gp_mod

    fake_text = json.dumps({
        "goal": "test",
        "domain": "ml-research",
        "primary_objective": "Test the parser subprocess wiring",
        "sub_objectives": ["check it works"],
        "success_metrics": {"works": "yes"},
        "timeline": "now",
        "constraints": [],
        "resources_needed": [],
    })

    class FakeCompleted:
        returncode = 0
        stdout = json.dumps({"ok": True, "text": fake_text})
        stderr = ""

    monkeypatch.setattr(
        gp_mod.subprocess, "run", lambda *a, **kw: FakeCompleted()
    )

    parser = GoalParser()
    result = parser.parse("Improve speculative decoding")
    assert result["primary_objective"] == "Test the parser subprocess wiring"
    assert result["sub_objectives"] == ["check it works"]


def test_parser_inproc_mode_bypasses_subprocess(monkeypatch):
    """Setting ARAIL_GOAL_PARSE_INPROC=1 must skip subprocess.run entirely
    (so existing tests that mock the router still work)."""
    from arail.skills.goal_parser import GoalParser
    import arail.skills.goal_parser as gp_mod

    monkeypatch.setenv("ARAIL_GOAL_PARSE_INPROC", "1")
    called = {"sub": False}

    def fake_run(*a, **kw):
        called["sub"] = True
        raise AssertionError("subprocess should not be invoked in inproc mode")

    monkeypatch.setattr(gp_mod.subprocess, "run", fake_run)

    # In-proc path falls through to the heuristic when no router is wired.
    parser = GoalParser()
    parser.router = None  # ensure lazy init path is taken

    # _llm_inproc swallows exceptions and returns None → heuristic.
    # We can't easily mock the lazy-instantiated router here without
    # touching the model load path, so just confirm the subprocess
    # branch is bypassed.
    monkeypatch.setattr(
        parser, "_llm_inproc", lambda prompt: None,
    )
    result = parser.parse("anything")
    assert called["sub"] is False
    assert "primary_objective" in result
