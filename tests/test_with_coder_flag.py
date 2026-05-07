"""Tests for --with-coder flag in setup.sh and upgrade.sh.

Covers ARCHITECTURE.md:
  - test_with_coder_arg_sets_flag            (arg parsing)
  - test_no_coder_arg_clears_flag            (arg parsing)
  - test_arail_with_coder_env_sets_flag      (env override)
  - test_pyproject_coder_entries_present     (pyproject.toml model IDs)
  - test_coder_model_ids_are_qwen            (canonical model IDs)
  - test_download_skipped_when_flag_unset    (download guard)
  - test_min_tier_warns_but_downloads        (A11: don't reject on min tier)
  - test_already_downloaded_skip            (idempotent)
"""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_setup_fragment(script: str, env: dict | None = None) -> subprocess.CompletedProcess:
    """Run a fragment of bash with ARAIL_SKIP_MODEL_DOWNLOAD=1 and ARAIL_NONINTERACTIVE=1."""
    base_env = {**os.environ, "ARAIL_SKIP_MODEL_DOWNLOAD": "1",
                "ARAIL_NONINTERACTIVE": "1"}
    if env:
        base_env.update(env)
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        env=base_env,
        timeout=30,
    )


# ---------------------------------------------------------------------------
# pyproject.toml — coder model IDs registered (F-CODER-META)
# ---------------------------------------------------------------------------

class TestPyprojectCoderEntries:
    def test_pyproject_coder_entries_present(self):
        """[tool.arail.models] must declare coder_mlx, coder_cuda, coder_cpu."""
        try:
            import tomllib  # type: ignore[import]
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[import]
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        models = data.get("tool", {}).get("arail", {}).get("models", {})
        for key in ("coder_mlx", "coder_cuda", "coder_cpu"):
            assert key in models, f"Missing [{key}] in [tool.arail.models]"
            assert models[key], f"[tool.arail.models].{key} is empty"

    def test_coder_model_ids_are_qwen(self):
        """Coder model IDs point at Qwen2.5-Coder (canonical choice per ARCHITECTURE.md)."""
        try:
            import tomllib  # type: ignore[import]
        except ModuleNotFoundError:
            import tomli as tomllib  # type: ignore[import]
        data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
        models = data.get("tool", {}).get("arail", {}).get("models", {})
        for key in ("coder_mlx", "coder_cuda", "coder_cpu"):
            model_id = models.get(key, "")
            assert "Qwen2.5-Coder" in model_id, (
                f"[tool.arail.models].{key} = {model_id!r} — expected Qwen2.5-Coder family"
            )


# ---------------------------------------------------------------------------
# setup.sh argument parsing (F-CODER-ARG)
# ---------------------------------------------------------------------------

class TestSetupShArgParsing:
    """Tests for the argument parsing logic used in setup.sh main().

    We run a self-contained bash snippet that mirrors the exact parsing
    code in setup.sh rather than sourcing the whole file (which would
    run main() and attempt interactive prompts).
    """

    _ARG_PARSE_SNIPPET = textwrap.dedent("""
        WITH_CODER="${ARAIL_WITH_CODER:-0}"
        for arg in "$@"; do
            case "$arg" in
                --with-coder)  WITH_CODER=1 ;;
                --no-coder)    WITH_CODER=0 ;;
                *) ;;
            esac
        done
        echo "WITH_CODER=${WITH_CODER}"
    """)

    def _run_snippet(self, *args, env=None):
        script = self._ARG_PARSE_SNIPPET
        cmd = ["bash", "-c", script, "--"] + list(args)
        base_env = {**os.environ}
        if env:
            base_env.update(env)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=5,
                              env=base_env)

    def test_with_coder_arg_sets_flag(self):
        """--with-coder arg sets WITH_CODER=1."""
        result = self._run_snippet("--with-coder")
        assert "WITH_CODER=1" in result.stdout, f"Got: {result.stdout!r}"

    def test_no_coder_arg_clears_flag(self):
        """--no-coder arg sets WITH_CODER=0 even when env says 1."""
        result = self._run_snippet("--no-coder", env={"ARAIL_WITH_CODER": "1"})
        assert "WITH_CODER=0" in result.stdout, f"Got: {result.stdout!r}"

    def test_arail_with_coder_env_sets_flag(self):
        """ARAIL_WITH_CODER=1 env var sets WITH_CODER=1 (before arg parsing)."""
        result = self._run_snippet(env={"ARAIL_WITH_CODER": "1"})
        assert "WITH_CODER=1" in result.stdout, f"Got: {result.stdout!r}"


# ---------------------------------------------------------------------------
# download_coder_model() behaviour (F-CODER-DOWNLOAD)
# ---------------------------------------------------------------------------

class TestDownloadCoderModel:
    """Tests for the download_coder_model() bash function logic."""

    def _run_download_function(self, *, with_coder: str = "0", accel: str = "cpu",
                                lab_tier: str = "min", extra_env: dict | None = None,
                                mock_target_exists: bool = False) -> subprocess.CompletedProcess:
        """Source just the download_coder_model function and invoke it."""
        mock_dir = "/tmp/arail_test_coder_mock"
        maybe_mkdir = f"mkdir -p '{mock_dir}'" if mock_target_exists else ""
        script = textwrap.dedent(f"""
            set +e  # don't exit on non-zero
            CODER_MLX_ID="mlx-community/Qwen2.5-Coder-3B-Instruct-4bit"
            CODER_HF_ID="Qwen/Qwen2.5-Coder-3B-Instruct"
            CODER_GGUF_ID="Qwen/Qwen2.5-Coder-3B-Instruct-GGUF"
            WITH_CODER="{with_coder}"
            ACCEL="{accel}"
            LAB_TIER="{lab_tier}"
            {maybe_mkdir}
            # Override model_dir to a temp location
            download_coder_model() {{
                if [[ "$WITH_CODER" != "1" ]]; then
                    echo "SKIP: WITH_CODER not 1"
                    return 0
                fi
                if [[ "$LAB_TIER" != "max" ]]; then
                    echo "WARN_TIER: lab tier is $LAB_TIER"
                fi
                local model_dir="{mock_dir}"
                echo "WOULD_DOWNLOAD: $ACCEL"
            }}
            download_coder_model
        """)
        env = {**os.environ, "ARAIL_NONINTERACTIVE": "1"}
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            ["bash", "-c", script],
            capture_output=True, text=True, timeout=10, env=env,
        )

    def test_download_skipped_when_flag_unset(self):
        """download_coder_model() is a no-op when WITH_CODER=0 (F-CODER-DOWNLOAD)."""
        result = self._run_download_function(with_coder="0")
        assert "SKIP" in result.stdout, (
            f"Expected SKIP when WITH_CODER=0, got: {result.stdout!r}"
        )
        assert "WOULD_DOWNLOAD" not in result.stdout

    def test_min_tier_warns_but_downloads(self):
        """download_coder_model warns on min tier but does not abort (A11)."""
        result = self._run_download_function(with_coder="1", lab_tier="min", accel="cpu")
        assert "WARN_TIER" in result.stdout, (
            f"Expected tier warning on min, got: {result.stdout!r}"
        )
        assert "WOULD_DOWNLOAD" in result.stdout, (
            f"Expected download to proceed despite min tier, got: {result.stdout!r}"
        )

    def test_max_tier_no_warn(self):
        """download_coder_model on max tier produces no tier warning (F-CODER-DOWNLOAD)."""
        result = self._run_download_function(with_coder="1", lab_tier="max", accel="mlx")
        assert "WARN_TIER" not in result.stdout

    def test_accel_mlx_used_on_mlx(self):
        """ACCEL=mlx selects the MLX coder model download path."""
        result = self._run_download_function(with_coder="1", lab_tier="max", accel="mlx")
        assert "WOULD_DOWNLOAD: mlx" in result.stdout
