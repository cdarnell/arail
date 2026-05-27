"""test_aerollm_tier_resolution.py

Locks down the structural correctness of the AeroLLM tier resolution chain.

History:

  Sprint 2026-05-20-aerollm-72b-lift: introduced per-tier deep models
  (minimalist=7B, maximus=72B) and fixed two related bugs:
    Bug 1 (MIN_ID stomp): the loader read aerollm_maximus first when
      resolving AEROLLM_MODEL_MIN_ID, so lifting maximus to 72B would
      OOM every minimalist install on 16 GB Macs.
    Bug 2 (no per-tier resolution): capture_tier wrote a flat
      AEROLLM_MODEL_ID for both tiers, ignoring MIN_ID/MAX_ID.

  Sprint 2026-05-25-chat-2nd-inference-works: lowered the maximus
  default back to 7B (same as minimalist) so a fresh clone "just works"
  on any AeroLLM-capable Mac without first downloading 40 GB of weights.
  Operators upgrade to a frontier model after setup via AEROLLM_MODEL
  in .env (see pyproject.toml [tool.arail.models] for the recipe).

These tests pin:
  - the per-tier values in pyproject.toml,
  - the loader lookup chain (Bug 1 guard — preserves the structural
    fix so a future re-bump of maximus does not re-introduce the OOM),
  - the capture_tier case-block structure (Bug 2 guard).
"""
from __future__ import annotations

from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-reuse]


import re

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
SETUP_SH = REPO_ROOT / "scripts" / "setup.sh"

# As of 2026-05-25 the maximus default matches minimalist — both 7B.
# Operators bump maximus locally via AEROLLM_MODEL in .env.
EXPECTED_MAX_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"
EXPECTED_MIN_MODEL = "mlx-community/Qwen2.5-7B-Instruct-4bit"


@pytest.fixture(scope="module")
def models() -> dict:
    """Load [tool.arail.models] from pyproject.toml."""
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    return data["tool"]["arail"]["models"]


# ---------------------------------------------------------------------------
# pyproject.toml key assertions
# ---------------------------------------------------------------------------

def test_aerollm_maximus_is_7b(models):
    """aerollm_maximus must point at the 7B default — same as minimalist.

    Operators upgrade locally via AEROLLM_MODEL in .env; the shipped default
    has to load on any clone without first downloading 40 GB of weights.
    """
    assert models["aerollm_maximus"] == EXPECTED_MAX_MODEL, (
        f"aerollm_maximus should be {EXPECTED_MAX_MODEL!r}, got {models['aerollm_maximus']!r}"
    )


def test_aerollm_minimalist_is_7b(models):
    """aerollm_minimalist must point at the 7B model (minimalist tier deep mode)."""
    assert models["aerollm_minimalist"] == EXPECTED_MIN_MODEL, (
        f"aerollm_minimalist should be {EXPECTED_MIN_MODEL!r}, got {models['aerollm_minimalist']!r}"
    )


def test_aerollm_legacy_alias_is_7b(models):
    """aerollm legacy alias must stay at 7B (backward compat for tooling
    that reads [tool.arail.models].aerollm without knowing the tier split)."""
    assert models["aerollm"] == EXPECTED_MIN_MODEL, (
        f"aerollm legacy alias should be {EXPECTED_MIN_MODEL!r}, got {models['aerollm']!r}"
    )


def test_aerollm_maximus_matches_minimalist(models):
    """As of 2026-05-25 the two tiers share the 7B default by design.

    This is a deliberate inversion of the pre-7180a8a invariant: shipping
    a maximus default whose weights don't ship and whose RAM footprint
    OOMs typical clones was the larger product bug. Operators upgrade
    maximus locally via AEROLLM_MODEL.
    """
    assert models["aerollm_maximus"] == models["aerollm_minimalist"], (
        "aerollm_maximus and aerollm_minimalist should match the 7B default — "
        "if they diverge, the maximus arm may be footgunning fresh clones."
    )


# ---------------------------------------------------------------------------
# Loader resolution chain (mirrors setup.sh load_pyproject_metadata)
# ---------------------------------------------------------------------------
#
# The shell loader does:
#
#   AEROLLM_MODEL_MIN_ID = models.get("aerollm_minimalist",
#                          models.get("aerollm_min",
#                          models.get("aerollm", "")))
#
#   AEROLLM_MODEL_MAX_ID = models.get("aerollm_maximus",
#                          models.get("aerollm_max",
#                          models.get("aerollm", "")))
#
# We replicate this in Python so a CI runner without bash can verify it.
# ---------------------------------------------------------------------------

def _resolve_min_id(models: dict) -> str:
    """Exact lookup chain from load_pyproject_metadata for MIN_ID."""
    return models.get("aerollm_minimalist",
           models.get("aerollm_min",
           models.get("aerollm", "")))


def _resolve_max_id(models: dict) -> str:
    """Exact lookup chain from load_pyproject_metadata for MAX_ID."""
    return models.get("aerollm_maximus",
           models.get("aerollm_max",
           models.get("aerollm", "")))


def test_loader_min_id_resolves_to_7b(models):
    """AEROLLM_MODEL_MIN_ID must resolve to the 7B model, NOT the 72B.

    This is the direct regression test for Bug 1 (MIN_ID stomp):
    the old loader read aerollm_maximus first, so lifting aerollm_maximus
    to 72B would have caused every minimalist install to resolve to 72B.
    """
    resolved = _resolve_min_id(models)
    assert resolved == EXPECTED_MIN_MODEL, (
        f"AEROLLM_MODEL_MIN_ID resolves to {resolved!r} — expected {EXPECTED_MIN_MODEL!r}.\n"
        "This is the MIN_ID stomp bug: aerollm_minimalist must come before aerollm_maximus "
        "in the lookup chain."
    )


def test_loader_max_id_resolves_to_7b(models):
    """AEROLLM_MODEL_MAX_ID must resolve to the 7B model (the new default)."""
    resolved = _resolve_max_id(models)
    assert resolved == EXPECTED_MAX_MODEL, (
        f"AEROLLM_MODEL_MAX_ID resolves to {resolved!r} — expected {EXPECTED_MAX_MODEL!r}."
    )


def test_loader_chain_keys_intact(models):
    """Structural guard: the loader's fallback chain keys must still exist.

    Preserves the Bug 1 fix shape (minimalist→min→aerollm; maximus→max→aerollm).
    A future re-bump of maximus to a frontier model would still need this chain
    intact so MIN_ID does not get stomped.
    """
    for key in ("aerollm_minimalist", "aerollm_maximus", "aerollm"):
        assert key in models, f"[tool.arail.models].{key} is missing — loader chain breaks."


# ---------------------------------------------------------------------------
# Tier case simulation (mirrors setup.sh capture_tier AeroLLM case block)
# ---------------------------------------------------------------------------
#
# Bug 2: before the fix, capture_tier used a flat assignment:
#
#   AEROLLM_MODEL_ID="${AEROLLM_MODEL_ID:-mlx-community/Qwen2.5-7B-Instruct-4bit}"
#
# for both tiers — MIN_ID/MAX_ID were loaded but never applied. We simulate
# the corrected case block here so a bash-less CI runner can verify it too.
# ---------------------------------------------------------------------------

def _simulate_capture_tier(lab_tier: str, models: dict) -> str:
    """Simulate the corrected case "$LAB_TIER" block in capture_tier.

    Returns the AEROLLM_MODEL_ID that capture_tier would write, given
    the AEROLLM_MODEL_MIN_ID / AEROLLM_MODEL_MAX_ID resolved from pyproject.
    """
    aerollm_model_max_id = _resolve_max_id(models)
    aerollm_model_min_id = _resolve_min_id(models)

    fallback_max = "mlx-community/Qwen2.5-72B-Instruct-4bit"
    fallback_min = "mlx-community/Qwen2.5-7B-Instruct-4bit"

    if lab_tier == "maximus":
        return aerollm_model_max_id or fallback_max
    else:
        return aerollm_model_min_id or fallback_min


def test_tier_maximus_selects_7b(models):
    """capture_tier with LAB_TIER=maximus must select the 7B default."""
    result = _simulate_capture_tier("maximus", models)
    assert result == EXPECTED_MAX_MODEL, (
        f"maximus tier resolved to {result!r}, expected {EXPECTED_MAX_MODEL!r}."
    )


def test_tier_minimalist_selects_7b(models):
    """capture_tier with LAB_TIER=minimalist must select the 7B deep model."""
    result = _simulate_capture_tier("minimalist", models)
    assert result == EXPECTED_MIN_MODEL, (
        f"minimalist tier resolved to {result!r}, expected {EXPECTED_MIN_MODEL!r}."
    )


def test_tier_unknown_falls_back_to_minimalist_model(models):
    """capture_tier's wildcard arm (* → minimalist path) selects the 7B."""
    result = _simulate_capture_tier("unknown_tier", models)
    assert result == EXPECTED_MIN_MODEL, (
        f"Unknown tier resolved to {result!r}; expected minimalist fallback {EXPECTED_MIN_MODEL!r}."
    )


def test_tier_legacy_min_alias_selects_7b(models):
    """Legacy 'min' tier (normalised to 'minimalist' in shell before this
    point, but test the non-maximus arm defensively) selects the 7B."""
    result = _simulate_capture_tier("min", models)
    assert result == EXPECTED_MIN_MODEL


def test_tier_legacy_max_alias_selects_7b(models):
    """Legacy 'max' tier (normalised to 'maximus' in shell) selects the 7B
    default. Both tiers share the same model as of 2026-05-25."""
    # 'max' is normalised to 'maximus' by capture_tier before the AeroLLM
    # case block is reached; simulate that normalisation here.
    normalised = "maximus"
    result = _simulate_capture_tier(normalised, models)
    assert result == EXPECTED_MAX_MODEL


# ---------------------------------------------------------------------------
# CO-1: shell-source guard (reads scripts/setup.sh as text)
# ---------------------------------------------------------------------------
#
# The tests above mirror the Python logic; a shell-only revert of setup.sh
# would not be caught by them. This test reads the actual shell script and
# asserts the two structural properties that were broken before the fix:
#
#   1. AEROLLM_MODEL_MIN_ID lookup leads with "aerollm_minimalist" — not
#      "aerollm_maximus" (the Bug 1 stomp). If someone reverts line ~115,
#      this test goes red before any deployment can OOM a minimalist user.
#
#   2. The capture_tier case block maps maximus → AEROLLM_MODEL_MAX_ID and
#      the wildcard → AEROLLM_MODEL_MIN_ID (Bug 2 fix). If someone replaces
#      the case block with a flat assignment again, this test goes red.
# ---------------------------------------------------------------------------


def test_setup_sh_min_id_loader_leads_with_aerollm_minimalist():
    """Bug 1 shell-guard: AEROLLM_MODEL_MIN_ID lookup in setup.sh must lead
    with 'aerollm_minimalist', not 'aerollm_maximus'.

    A shell-only revert of setup.sh:~115 (flipping the .get() chain back to
    aerollm_maximus first) would restore the OOM trap for minimalist users
    the moment aerollm_maximus stays at 72B. This test catches that revert
    without needing a bash harness.
    """
    text = SETUP_SH.read_text(encoding="utf-8")

    # The corrected line looks like (possibly with surrounding whitespace):
    #   "AEROLLM_MODEL_MIN_ID": str(models.get("aerollm_minimalist", ...))
    # We assert aerollm_minimalist appears BEFORE aerollm_maximus on any line
    # that sets AEROLLM_MODEL_MIN_ID.
    min_id_line = None
    for line in text.splitlines():
        if "AEROLLM_MODEL_MIN_ID" in line and "models.get" in line:
            min_id_line = line
            break

    assert min_id_line is not None, (
        "Could not find the AEROLLM_MODEL_MIN_ID loader line in scripts/setup.sh. "
        "Was the load_pyproject_metadata heredoc moved or renamed?"
    )

    # The first models.get() key on the MIN_ID line must be aerollm_minimalist.
    first_key_match = re.search(r'models\.get\("([^"]+)"', min_id_line)
    assert first_key_match is not None, (
        f"Could not parse models.get() call on MIN_ID line: {min_id_line!r}"
    )
    first_key = first_key_match.group(1)
    assert first_key == "aerollm_minimalist", (
        f"AEROLLM_MODEL_MIN_ID loader leads with {first_key!r} — must be "
        f"'aerollm_minimalist'. Reverting to 'aerollm_maximus' first re-introduces "
        f"Bug 1 (minimalist installs resolve to 72B → OOM on 16 GB Macs)."
    )


def test_setup_sh_capture_tier_has_aerollm_case_block():
    """Bug 2 shell-guard: capture_tier in setup.sh must contain an AeroLLM
    case block that maps maximus→AEROLLM_MODEL_MAX_ID and *→AEROLLM_MODEL_MIN_ID.

    A shell-only revert to a flat assignment (ignoring tier) would silently
    give maximus users the 7B model. This test catches that structural revert.
    """
    text = SETUP_SH.read_text(encoding="utf-8")

    # Assert the maximus arm maps to MAX_ID
    assert re.search(
        r'maximus\)\s+AEROLLM_MODEL_ID="\$\{AEROLLM_MODEL_MAX_ID',
        text,
    ), (
        "scripts/setup.sh capture_tier is missing the "
        "'maximus) AEROLLM_MODEL_ID=\"${AEROLLM_MODEL_MAX_ID...' arm. "
        "Maximus tier would fall through to the minimalist (7B) path."
    )

    # Assert the wildcard arm maps to MIN_ID (appears after the maximus arm)
    assert re.search(
        r'\*\)\s+AEROLLM_MODEL_ID="\$\{AEROLLM_MODEL_MIN_ID',
        text,
    ), (
        "scripts/setup.sh capture_tier is missing the "
        "'*) AEROLLM_MODEL_ID=\"${AEROLLM_MODEL_MIN_ID...' wildcard arm. "
        "Non-maximus tiers (including minimalist) would not get the 7B model."
    )
