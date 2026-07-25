"""Setup-on-clean-machine tests — pyproject extras + import-graph smoke.

ARAIL ships as a clone-and-run blueprint; the most common failure mode
is "user does ./arailctl upgrade max but pip-audit didn't actually install".
These tests pin the install surface so a future refactor can't silently
drop the security extra.

Per ARAIL CLAUDE.md QA allocation: setup is the largest bucket (30%).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


@pytest.fixture(scope="module")
def pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# pyproject.toml extras
# ---------------------------------------------------------------------------

def test_security_extra_pins_pip_audit(pyproject_text):
    """A dedicated [security] extra exists and pins pip-audit major version."""
    # Match: security = ["pip-audit>=2.7.0,<3"]
    m = re.search(
        r'^security\s*=\s*\[\s*"pip-audit>=2\.7\.\d+,<3"\s*\]',
        pyproject_text, re.MULTILINE,
    )
    assert m, "Expected `security = [\"pip-audit>=2.7.0,<3\"]` in pyproject.toml"


def test_maximus_extra_includes_pip_audit(pyproject_text):
    """The maximus tier ships pip-audit so users on maximus get CVE scanning."""
    # Find the `maximus = [` block and assert pip-audit is inside it.
    m = re.search(r'^maximus\s*=\s*\[(?P<body>.+?)^\]', pyproject_text,
                  re.MULTILINE | re.DOTALL)
    assert m, "Could not locate `maximus = [...]` in pyproject.toml"
    assert "pip-audit" in m.group("body"), (
        "maximus extra must include pip-audit (so `./arailctl upgrade maximus` installs CVE scanner)"
    )


def test_minimalist_extra_does_NOT_include_pip_audit(pyproject_text):
    """The minimalist tier MUST NOT install pip-audit — keeps default install lean."""
    # minimalist = [] in v1.0.0 (no deps in the base tier).
    m = re.search(r'^minimalist\s*=\s*\[(?P<body>.*?)\]', pyproject_text,
                  re.MULTILINE | re.DOTALL)
    assert m, "Could not locate `minimalist = [...]` in pyproject.toml"
    assert "pip-audit" not in m.group("body"), (
        "minimalist extra MUST NOT include pip-audit — that defeats the opt-in tier model"
    )


# ---------------------------------------------------------------------------
# Import graph smoke
# ---------------------------------------------------------------------------

def test_portal_app_module_imports():
    """Fresh-clone smoke: `from arail.portal import app` must succeed."""
    from arail.portal import app  # noqa: F401


def test_scheduler_module_imports():
    from arail.portal import scheduler  # noqa: F401


def test_security_scan_module_imports():
    """security_scan.py must load even when pip-audit is absent (C5)."""
    from arail.portal import security_scan  # noqa: F401


def test_security_scan_is_available_returns_bool_without_raising():
    """is_available() must always return a bool, never raise."""
    from arail.portal import security_scan
    result = security_scan.is_available()
    assert isinstance(result, bool)


def test_security_scan_status_returns_dict_when_no_file(monkeypatch, tmp_path):
    """status() with no last_scan.json must return a stub dict, never raise."""
    monkeypatch.setenv("ARAIL_DATA_DIR", str(tmp_path))
    import importlib
    import arail.config as _cfg
    importlib.reload(_cfg)
    from arail.portal import security_scan
    importlib.reload(security_scan)
    s = security_scan.status()
    assert isinstance(s, dict)
    assert "available" in s


# ---------------------------------------------------------------------------
# Lab-mode env var fallback chain
# ---------------------------------------------------------------------------

def test_lab_mode_default_is_airgapped(monkeypatch):
    """Default lab mode (no env vars) is airgapped — the safest setting."""
    monkeypatch.delenv("LAB_MODE", raising=False)
    monkeypatch.delenv("ARAIL_MODE", raising=False)
    from arail.portal.app import _lab_mode
    assert _lab_mode() == "airgapped"


def test_lab_mode_lab_mode_takes_precedence(monkeypatch):
    """LAB_MODE wins over ARAIL_MODE if both set."""
    monkeypatch.setenv("LAB_MODE", "hybrid")
    monkeypatch.setenv("ARAIL_MODE", "airgapped")
    from arail.portal.app import _lab_mode
    assert _lab_mode() == "hybrid"


# ---------------------------------------------------------------------------
# setup.sh network-mode capture (welcome-flow CLI parity)
# ---------------------------------------------------------------------------

SETUP_SH = Path(__file__).resolve().parent.parent / "scripts" / "setup.sh"


@pytest.fixture(scope="module")
def setup_sh_text() -> str:
    return SETUP_SH.read_text(encoding="utf-8")


def test_setup_defines_capture_mode(setup_sh_text):
    """CLI parity with the browser welcome flow: a mode prompt exists."""
    assert "capture_mode()" in setup_sh_text
    body = setup_sh_text.split("capture_mode()", 1)[1].split("\n}\n", 1)[0]
    # Non-interactive path honors the standard knobs (ARAIL_MODE is the
    # existing legacy alias — no third env-var name).
    assert "ARAIL_NONINTERACTIVE" in body
    assert "ARAIL_MODE" in body
    # The crucial education copy: self-provided material + in-box Worlds.
    assert "YOU provide" in body
    assert "ship inside ARAIL" in body


def test_setup_main_calls_capture_mode(setup_sh_text):
    assert re.search(r"^\s*capture_mode\s*$", setup_sh_text, re.MULTILINE)


def test_setup_persists_lab_mode(setup_sh_text):
    assert '_set_env_var LAB_MODE "$LAB_MODE"' in setup_sh_text


def test_setup_verify_checks_shipped_worlds(setup_sh_text):
    """Step 11 verifies the vendored bundles (warn, never abort)."""
    verify_body = setup_sh_text.split("\nverify() {", 1)[1].split("\n}\n", 1)[0]
    assert "verify-shipped" in verify_body
    assert "git checkout -- lab/worlds" in verify_body


# ---------------------------------------------------------------------------
# Tier-0 everyday-model binding must match what setup actually installs
# ---------------------------------------------------------------------------
#
# Regression guard: setup auto-installs llama-ai-eng (Ollama) on minimalist and
# deliberately does NOT download the ~5 GB MLX Qwen3-8B there. So setup_env()
# must bind the everyday model to the Ollama persona on minimalist, not to the
# un-downloaded MLX model — otherwise a fresh minimalist lab opens the chat tab
# onto a broken default.

def _setup_env_body(setup_sh_text: str) -> str:
    return setup_sh_text.split("\nsetup_env() {", 1)[1].split("\n}\n", 1)[0]


def test_minimalist_binds_everyday_model_to_installed_ollama_persona(setup_sh_text):
    body = _setup_env_body(setup_sh_text)
    assert "MODEL_BACKEND=ollama_native" in body
    assert "MODEL_NAME=llama-ai-eng" in body


def test_env_binding_is_tier_gated_not_unconditional_mlx(setup_sh_text):
    """The MLX/CUDA/CPU Qwen3-8B binding must sit under a maximus-only branch,
    so minimalist never inherits a model download_model() skips."""
    body = _setup_env_body(setup_sh_text)
    # The Ollama persona bind must appear BEFORE the accel-native Qwen binding,
    # i.e. inside the minimalist branch of a tier gate.
    ollama_at = body.find("MODEL_NAME=llama-ai-eng")
    mlx_at = body.find("MODEL_NAME=${MODEL_MLX_ID}")
    assert ollama_at != -1 and mlx_at != -1
    assert ollama_at < mlx_at, "minimalist Ollama bind should precede the maximus MLX bind"
    # And the maximus bind must be reachable only when the tier is maximus.
    assert 'if [[ "$_env_tier" != "maximus" ]]' in body


# ---------------------------------------------------------------------------
# README pointer to PUBLISH.md
# ---------------------------------------------------------------------------

def test_readme_links_to_publish_md():
    """A user looking at README must find the path to PUBLISH.md."""
    readme = Path(__file__).resolve().parent.parent / "README.md"
    assert readme.exists()
    text = readme.read_text(encoding="utf-8")
    assert "PUBLISH.md" in text or "docs/PUBLISH" in text, (
        "README must link to docs/PUBLISH.md so operators discover the publish guide"
    )
