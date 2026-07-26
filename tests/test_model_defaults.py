"""model_defaults.yaml — the one file to check for what's active.

Historically "which model does chat use" and "which model does AeroLLM
load" were each answered by a chain of .env vars, hardcoded fallback
constants, and installed-model detection spread across app.py and
router/backends.py. This is the single, authoritative source for those
two settings: `apply()` stamps its values into the SAME env vars (
MODEL_NAME, AEROLLM_MODEL) every existing call site already reads, so
nothing downstream needs to change to respect it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from arail import model_defaults


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """`apply()` writes MODEL_NAME/AEROLLM_MODEL straight to os.environ —
    by design (it must win over whatever .env set, the same way the
    portal's other os.environ-direct writers, e.g. the airgap toggle,
    intentionally bypass monkeypatch). That means monkeypatch's own
    teardown can't undo it: a test here that calls apply() directly
    (with an explicit path=, not through arail.config) leaves a real,
    persistent mutation that otherwise survives for the rest of the
    pytest session and can break unrelated tests elsewhere (confirmed —
    this exact leak once made test_aerollm_model_ready.py fail only when
    run after this file). Restore-by-hand in teardown, matching
    conftest.py's isolated_secrets fixture for the identical problem
    shape."""
    monkeypatch.delenv("MODEL_NAME", raising=False)
    monkeypatch.delenv("AEROLLM_MODEL", raising=False)
    _saved = {k: os.environ.get(k) for k in ("MODEL_NAME", "AEROLLM_MODEL")}
    yield
    for k, v in _saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_missing_file_overrides_nothing(tmp_path):
    result = model_defaults.apply(tmp_path / "does-not-exist.yaml")
    assert result == {}
    assert "MODEL_NAME" not in os.environ
    assert "AEROLLM_MODEL" not in os.environ


def test_default_a_stamps_model_name(tmp_path):
    f = tmp_path / "model_defaults.yaml"
    f.write_text("default_a: ai-engineer:latest\n", encoding="utf-8")
    result = model_defaults.apply(f)
    assert os.environ["MODEL_NAME"] == "ai-engineer:latest"
    assert result["default_a"] == "ai-engineer:latest"


def test_default_b_stamps_aerollm_model(tmp_path):
    f = tmp_path / "model_defaults.yaml"
    f.write_text("default_b: Qwen3-8B-4bit\n", encoding="utf-8")
    result = model_defaults.apply(f)
    assert os.environ["AEROLLM_MODEL"] == "Qwen3-8B-4bit"
    assert result["default_b"] == "Qwen3-8B-4bit"


def test_explicit_null_default_b_clears_a_stale_env_value(tmp_path, monkeypatch):
    """The honesty guarantee: an explicit `default_b: null` must win over
    whatever .env already set — "not configured" must not be silently
    overridden by a stale environment value from before this file
    existed."""
    monkeypatch.setenv("AEROLLM_MODEL", "some-stale-value-from-dot-env")
    f = tmp_path / "model_defaults.yaml"
    f.write_text("default_b: null\n", encoding="utf-8")
    result = model_defaults.apply(f)
    assert "AEROLLM_MODEL" not in os.environ
    assert result["default_b"] is None


def test_omitting_default_b_entirely_leaves_env_untouched(tmp_path, monkeypatch):
    """Distinguish 'the key is absent' (don't touch anything — some other
    mechanism, e.g. .env, may still be setting this) from 'the key is
    explicitly null' (clear it) — same distinction os.getenv's own
    default-vs-present-but-empty semantics needed getting right for
    AEROLLM_MODEL earlier tonight."""
    monkeypatch.setenv("AEROLLM_MODEL", "untouched-value")
    f = tmp_path / "model_defaults.yaml"
    f.write_text("default_a: ai-engineer:latest\n", encoding="utf-8")
    model_defaults.apply(f)
    assert os.environ["AEROLLM_MODEL"] == "untouched-value"


def test_malformed_yaml_never_raises(tmp_path):
    f = tmp_path / "model_defaults.yaml"
    f.write_text("not: valid: yaml: [[[", encoding="utf-8")
    result = model_defaults.apply(f)
    assert result == {}


def test_non_mapping_yaml_never_raises(tmp_path):
    f = tmp_path / "model_defaults.yaml"
    f.write_text("- just\n- a\n- list\n", encoding="utf-8")
    result = model_defaults.apply(f)
    assert result == {}


def test_empty_file_overrides_nothing(tmp_path):
    f = tmp_path / "model_defaults.yaml"
    f.write_text("", encoding="utf-8")
    result = model_defaults.apply(f)
    assert result == {}
    assert "MODEL_NAME" not in os.environ


def test_config_module_applies_it_at_import(monkeypatch, tmp_path):
    """The actual integration point: arail.config calls apply() right
    after load_dotenv(), so every existing MODEL_NAME/AEROLLM_MODEL
    reader across the codebase sees this file's values for free.

    Goes through ARAIL_MODEL_DEFAULTS_FILE (not chdir) — that's the real
    override path used everywhere else (config.py, and the session-level
    isolation in conftest.py that keeps a developer's real
    model_defaults.yaml from leaking into every other test)."""
    import importlib
    real = tmp_path / "model_defaults.yaml"
    real.write_text("default_a: test-model:latest\ndefault_b: test-deep-model\n", encoding="utf-8")
    monkeypatch.setenv("ARAIL_MODEL_DEFAULTS_FILE", str(real))
    from arail import config as config_mod
    importlib.reload(config_mod)
    assert os.environ.get("MODEL_NAME") == "test-model:latest"
    assert os.environ.get("AEROLLM_MODEL") == "test-deep-model"


def test_araIl_model_defaults_file_env_override_wins_over_cwd_default(monkeypatch, tmp_path):
    """The isolation mechanism itself, tested directly: with the env var
    set, a real model_defaults.yaml sitting in the CWD must be ignored —
    this is exactly what stops a developer's real file from leaking into
    a test process the way ARAIL_ENV_FILE already prevents for .env."""
    cwd_file = tmp_path / "cwd"
    cwd_file.mkdir()
    (cwd_file / "model_defaults.yaml").write_text(
        "default_a: from-cwd:latest\n", encoding="utf-8"
    )
    override_file = tmp_path / "override.yaml"
    override_file.write_text("default_a: from-override:latest\n", encoding="utf-8")

    monkeypatch.chdir(cwd_file)
    monkeypatch.setenv("ARAIL_MODEL_DEFAULTS_FILE", str(override_file))
    result = model_defaults.apply()
    assert result["default_a"] == "from-override:latest"
    assert os.environ["MODEL_NAME"] == "from-override:latest"


def test_session_isolation_points_at_a_file_that_does_not_exist():
    """The actual conftest.py wiring: ARAIL_MODEL_DEFAULTS_FILE is set
    session-wide before any arail.* import, pointing at a path that
    can never exist — so importing arail.config in ANY test never reads
    whatever is really sitting in this repo's own model_defaults.yaml."""
    override = os.environ.get("ARAIL_MODEL_DEFAULTS_FILE")
    assert override, "conftest.py must set ARAIL_MODEL_DEFAULTS_FILE for every test"
    assert not Path(override).exists()


def test_example_file_is_valid_yaml_and_documents_both_keys():
    """The committed .example file must actually parse and name both
    slots — it's the thing a new operator reads first."""
    import yaml
    example = Path(__file__).resolve().parent.parent / "model_defaults.yaml.example"
    assert example.exists()
    data = yaml.safe_load(example.read_text(encoding="utf-8"))
    assert "default_a" in data
    assert "default_b" in data
