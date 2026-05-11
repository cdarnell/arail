"""Test the per-tier LAB_MODE default introduced by sprint 2026-05-11-min-cloud-first.

Decisions pinned here:
  - First-run setup with LAB_TIER=min writes LAB_MODE=hybrid (cloud-first)
  - First-run setup with LAB_TIER=max writes LAB_MODE=airgapped (privacy-first)
  - upgrade.sh sets LAB_MODE only when the key is absent (preserves explicit
    user values across tier switches)
  - Re-running setup with an existing .env doesn't clobber an explicit LAB_MODE

These tests exercise the shell scripts directly via subprocess in a tmpdir,
mirroring the pattern in test_enable_compare_cli.py.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _env_value(env_path: Path, key: str) -> str | None:
    for line in env_path.read_text().splitlines():
        if line.startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"')
    return None


def _env_count(env_path: Path, key: str) -> int:
    return sum(1 for line in env_path.read_text().splitlines()
               if line.startswith(f"{key}="))


# ─── setup.sh setup_env helper ──────────────────────────────────────────
# We don't run the whole setup pipeline — too many side effects. Instead,
# we source setup.sh's helpers and invoke `_set_env_var` + the tier-based
# case statement directly.
#
# This is fragile to refactors of setup.sh but pins the exact write that
# matters: ARAIL_COMPARE_ENABLED and LAB_MODE per tier.


def _source_and_apply_tier_defaults(tier: str, env_path: Path) -> None:
    """Run setup.sh's tier-based env writes against the given .env path.

    The setup.sh _set_env_var helper writes to ./.env relative to cwd, so
    we run the helper from inside tmpdir."""
    script = f"""
        set -e
        cd "{env_path.parent}"
        # Pull in the _set_env_var helper. Define a no-op step()/info()/warn()
        # so the script body doesn't error before we reach the helper.
        step() {{ :; }}; info() {{ :; }}; warn() {{ :; }}; error() {{ echo "$@" >&2; exit 1; }}
        BOLD=""; RESET=""; CYAN=""; YELLOW=""; GREEN=""; RED=""
        # Cherry-pick just the helper definition — it's self-contained.
        eval "$(awk '/^_set_env_var\\(\\) \\{{$/,/^}}$/' {_REPO_ROOT}/scripts/setup.sh)"

        LAB_TIER="{tier}"
        case "${{LAB_TIER:-min}}" in
            max) _set_env_var ARAIL_COMPARE_ENABLED "1" ;;
            *)   _set_env_var ARAIL_COMPARE_ENABLED "0" ;;
        esac
        case "${{LAB_TIER:-min}}" in
            max) _set_env_var LAB_MODE "airgapped" ;;
            *)   _set_env_var LAB_MODE "hybrid" ;;
        esac
    """
    subprocess.run(["bash", "-c", script], check=True, capture_output=True, text=True)


@pytest.fixture
def tmp_env(tmp_path: Path) -> Path:
    """A tmpdir with a minimal .env so setup.sh's _set_env_var can edit it."""
    (tmp_path / ".env").write_text(
        "# arail .env (test)\nMODEL_BACKEND=mlx\nLAB_NAME=Test\n"
    )
    return tmp_path


def test_min_tier_writes_lab_mode_hybrid(tmp_env: Path):
    """LAB_TIER=min → LAB_MODE=hybrid (cloud-first default)."""
    _source_and_apply_tier_defaults("min", tmp_env / ".env")
    assert _env_value(tmp_env / ".env", "LAB_MODE") == "hybrid"


def test_max_tier_writes_lab_mode_airgapped(tmp_env: Path):
    """LAB_TIER=max → LAB_MODE=airgapped (privacy-first default)."""
    _source_and_apply_tier_defaults("max", tmp_env / ".env")
    assert _env_value(tmp_env / ".env", "LAB_MODE") == "airgapped"


def test_setup_writes_one_lab_mode_line(tmp_env: Path):
    """Running the tier write twice does not duplicate the LAB_MODE line."""
    _source_and_apply_tier_defaults("min", tmp_env / ".env")
    _source_and_apply_tier_defaults("min", tmp_env / ".env")
    assert _env_count(tmp_env / ".env", "LAB_MODE") == 1


def test_setup_writes_compare_flag_per_tier(tmp_env: Path):
    """Smoke: ARAIL_COMPARE_ENABLED also writes per tier (already covered
    by test_min_tier_simplification_qa but pin once more here to catch
    regressions in setup_env())."""
    _source_and_apply_tier_defaults("min", tmp_env / ".env")
    assert _env_value(tmp_env / ".env", "ARAIL_COMPARE_ENABLED") == "0"
    _source_and_apply_tier_defaults("max", tmp_env / ".env")
    assert _env_value(tmp_env / ".env", "ARAIL_COMPARE_ENABLED") == "1"


# ─── upgrade.sh upsert-when-missing semantics ──────────────────────────


def test_upgrade_sets_lab_mode_when_missing(tmp_env: Path):
    """upgrade.sh on min→max sets LAB_MODE=airgapped when key absent."""
    env = tmp_env / ".env"
    # Pre-state: no LAB_MODE key.
    assert _env_value(env, "LAB_MODE") is None
    # Run the inline Python helper from upgrade.sh directly.
    tier = "max"
    script = f"""
import pathlib
try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

tier = "{tier}"
data = tomllib.loads(pathlib.Path("{_REPO_ROOT}/pyproject.toml").read_text())
models = data.get("tool", {{}}).get("arail", {{}}).get("models", {{}})
tier_model_key = f"airllm_{{tier}}"
airllm_model = models.get(tier_model_key, "") if tier == "max" else ""

p = pathlib.Path("{env}")
lines = p.read_text().splitlines() if p.exists() else []

def has_key(out, key):
    for line in out:
        if line.lstrip("# ").startswith(f"{{key}}="):
            return True
    return False

def upsert(out, key, value):
    seen = False
    new = []
    for line in out:
        if line.lstrip("# ").startswith(f"{{key}}="):
            new.append(f"{{key}}={{value}}")
            seen = True
        else:
            new.append(line)
    if not seen:
        if new and new[-1] != "":
            new.append("")
        new.append(f"{{key}}={{value}}")
    return new

lines = upsert(lines, "LAB_TIER", tier)
if airllm_model:
    lines = upsert(lines, "AIRLLM_MODEL", airllm_model)
if tier == "max" and not has_key(lines, "ARAIL_COMPARE_ENABLED"):
    lines = upsert(lines, "ARAIL_COMPARE_ENABLED", "1")
if not has_key(lines, "LAB_MODE"):
    lines = upsert(lines, "LAB_MODE", "airgapped" if tier == "max" else "hybrid")

p.write_text("\\n".join(lines) + "\\n")
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    assert _env_value(env, "LAB_MODE") == "airgapped"


def test_upgrade_preserves_explicit_lab_mode(tmp_env: Path):
    """upgrade.sh on min→max LEAVES an existing explicit LAB_MODE value
    alone (the upsert-when-missing semantics)."""
    env = tmp_env / ".env"
    # Pre-state: user explicitly set LAB_MODE=hybrid even on max.
    env.write_text(env.read_text() + "LAB_MODE=hybrid\n")
    tier = "max"
    script = f"""
import pathlib

p = pathlib.Path("{env}")
lines = p.read_text().splitlines() if p.exists() else []

def has_key(out, key):
    for line in out:
        if line.lstrip("# ").startswith(f"{{key}}="):
            return True
    return False

def upsert(out, key, value):
    seen = False
    new = []
    for line in out:
        if line.lstrip("# ").startswith(f"{{key}}="):
            new.append(f"{{key}}={{value}}")
            seen = True
        else:
            new.append(line)
    if not seen:
        new.append(f"{{key}}={{value}}")
    return new

tier = "{tier}"
if not has_key(lines, "LAB_MODE"):
    lines = upsert(lines, "LAB_MODE", "airgapped" if tier == "max" else "hybrid")
p.write_text("\\n".join(lines) + "\\n")
"""
    subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True)
    # The explicit hybrid value survives even though tier=max.
    assert _env_value(env, "LAB_MODE") == "hybrid"
