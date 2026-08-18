"""The tuning loop must find its model on an airgapped box.

config/tuning-mlx.yml names the research model by HF id
("mlx-community/Qwen2.5-7B-Instruct-4bit"). The lab is airgapped by
default, so an uncached id is not a slow path — mlx_lm raises
LocalEntryNotFoundError and the pass dies at baseline, while the
checkpoint sits unused in ARAIL_MODELS_DIR.
"""
from __future__ import annotations

import pytest

from arail.experiments import mlx_backend as mb


def _make_model_dir(root, name):
    d = root / name
    d.mkdir(parents=True)
    (d / "config.json").write_text("{}")
    return d


def test_hf_id_resolves_to_a_local_checkout(tmp_path, monkeypatch):
    local = _make_model_dir(tmp_path, "Qwen2.5-7B-Instruct-4bit")
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path))
    assert mb.resolve_model_path(
        "mlx-community/Qwen2.5-7B-Instruct-4bit") == str(local)


def test_unknown_id_is_handed_back_untouched(tmp_path, monkeypatch):
    """A hybrid lab with a warm HF cache must keep working."""
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path))
    assert mb.resolve_model_path("mlx-community/Nope-9B") == "mlx-community/Nope-9B"


def test_an_explicit_directory_is_left_alone(tmp_path, monkeypatch):
    local = _make_model_dir(tmp_path, "Some-Model")
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path / "elsewhere"))
    assert mb.resolve_model_path(str(local)) == str(local)


def test_a_directory_without_config_json_is_not_a_model(tmp_path, monkeypatch):
    (tmp_path / "Qwen2.5-7B-Instruct-4bit").mkdir()
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path))
    assert mb.resolve_model_path(
        "mlx-community/Qwen2.5-7B-Instruct-4bit"
    ) == "mlx-community/Qwen2.5-7B-Instruct-4bit"


def test_empty_id_is_passed_through(tmp_path, monkeypatch):
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path))
    assert mb.resolve_model_path("") == ""


def test_knob_override_is_also_resolved(tmp_path, monkeypatch):
    """model_quant_variant picks a different checkpoint — it needs the
    same local resolution, or a variant sweep dies where baseline lived."""
    local = _make_model_dir(tmp_path, "Qwen2.5-7B-Instruct-8bit")
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path))
    got = mb._pick_model_id(
        {"model_quant_variant": "mlx-community/Qwen2.5-7B-Instruct-8bit"},
        fallback="mlx-community/Qwen2.5-7B-Instruct-4bit")
    assert got == str(local)


def test_fallback_is_resolved_when_no_override(tmp_path, monkeypatch):
    local = _make_model_dir(tmp_path, "Qwen2.5-7B-Instruct-4bit")
    monkeypatch.setattr("arail.config.MODELS_DIR", str(tmp_path))
    assert mb._pick_model_id(
        {}, fallback="mlx-community/Qwen2.5-7B-Instruct-4bit") == str(local)
