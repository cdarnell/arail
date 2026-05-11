"""Pin the min-tier install contract.

Sprint 2026-05-10-min-tier-simplification dropped `airllm>=2.0` from
`[project.optional-dependencies.min]` so `pip install -e ".[min]"` does
not pull a disk-streaming backend. The `max` tier still keeps airllm
(operator-gated at runtime by ARAIL_DEV_AIRLLM=1 on non-arm64).

These tests parse pyproject.toml directly so they catch regressions when
someone re-adds airllm to min without updating the docs.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _pyproject() -> dict:
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())


def test_min_tier_extras_is_empty():
    """`min` extras must be the empty list — no airllm, no other extras.

    The blueprint design is 'Ollama-only for min'. If you need a deep
    backend, you upgrade to max or enable an add-on. Anything that lands
    here re-couples min to a backend it deliberately doesn't ship."""
    data = _pyproject()
    extras = data["project"]["optional-dependencies"]
    assert extras["min"] == [], (
        f"min extras must be empty, got {extras['min']!r}. "
        "If you're adding a min-tier extra, update SPRINT.md and the tier "
        "description first."
    )


def test_max_tier_still_includes_airllm():
    """Regression guard: max keeps airllm so the operator-gated path on
    non-arm64 stays available. Don't accidentally drop it from max when
    pruning min."""
    data = _pyproject()
    max_extras = data["project"]["optional-dependencies"]["max"]
    assert any(spec.startswith("airllm") for spec in max_extras), (
        f"max extras lost airllm: {max_extras}"
    )


def test_min_surfaces_match_blueprint():
    """The declarative surface matrix gates the portal nav. Min must
    advertise exactly dashboard/chat/research/knowledge/agents — no
    admin/docs/notebooks/etc."""
    data = _pyproject()
    tiers = data["tool"]["arail"]["tiers"]
    assert tiers["min"]["surfaces"] == [
        "dashboard", "chat", "research", "knowledge", "agents",
    ]


def test_max_surfaces_superset_of_min():
    """Max must include every min surface plus its extras. Catch the
    case where someone reorders/drops from max."""
    data = _pyproject()
    tiers = data["tool"]["arail"]["tiers"]
    min_set = set(tiers["min"]["surfaces"])
    max_set = set(tiers["max"]["surfaces"])
    assert min_set.issubset(max_set), (
        f"max surfaces {max_set} is not a superset of min {min_set}"
    )


def test_tier_description_strings_mention_correct_inference_path():
    """Doc-string sanity: min description should NOT mention AirLLM
    (it was removed from min); max description SHOULD mention it
    (operator-gated, but still part of the tier extras).

    These are user-visible strings the portal reads — a stale value
    here shows up in the UI."""
    data = _pyproject()
    tiers = data["tool"]["arail"]["tiers"]
    min_desc = tiers["min"]["description"].lower()
    max_desc = tiers["max"]["description"].lower()
    assert "airllm" not in min_desc, (
        f"min description still mentions AirLLM: {min_desc!r}"
    )
    assert "ollama" in min_desc, (
        f"min description should mention Ollama: {min_desc!r}"
    )
    assert "airllm" in max_desc or "aerollm" in max_desc, (
        f"max description should mention a deep backend: {max_desc!r}"
    )
