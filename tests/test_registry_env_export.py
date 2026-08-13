"""_export_registry_env — sprints/2026-08-11-two-slot-chat-models Part 4.

secrets.env is never loaded into the process environment at boot (only
read on demand via _read_secrets()); the registry is the only thing a UI
model pick writes to. Without this export, a pick would be invisible to
every other env reader in the process (AeroLLMBackend._cache_key, the
residency probes, _resilient_chat_default) until the operator also
hand-edited .env to match.
"""

from __future__ import annotations

import os
import sys
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(_REPO_ROOT, "src") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))


def _isolate_registry(monkeypatch):
    from arail.registry import core as reg_core
    tmp_dir = tempfile.mkdtemp(prefix="arail-export-env-registry-")
    monkeypatch.setenv("ARAIL_MODEL_REGISTRY_FILE", os.path.join(tmp_dir, "model_registry.json"))
    reg_core.reset_registry()


def test_export_sets_aerollm_model_from_registry(monkeypatch):
    import arail.portal.app as app_mod

    _isolate_registry(monkeypatch)
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "llama-ai-eng")
    monkeypatch.setenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct-4bit")

    # Seed once, then simulate an operator/UI pick diverging AEROLLM_MODEL
    # from what the registry now holds (as a real deep-slot pick would).
    from arail.registry import get_registry
    from arail.registry.store import TIER1_ID
    from dataclasses import replace
    reg = get_registry()
    reg._ensure_loaded()
    reg.add_entry(replace(reg.entries[TIER1_ID], model_id="Qwen2.5-3B-Instruct-4bit", source="user"))

    monkeypatch.delenv("AEROLLM_MODEL", raising=False)
    app_mod._export_registry_env()
    assert os.environ.get("AEROLLM_MODEL") == "Qwen2.5-3B-Instruct-4bit"


def test_export_sets_model_name_for_ollama_backend(monkeypatch):
    import arail.portal.app as app_mod

    _isolate_registry(monkeypatch)
    monkeypatch.setenv("MODEL_BACKEND", "ollama_native")
    monkeypatch.setenv("MODEL_NAME", "llama-ai-eng")

    from arail.registry import get_registry
    from arail.registry.store import TIER0_ID
    from dataclasses import replace
    reg = get_registry()
    reg._ensure_loaded()
    reg.add_entry(replace(reg.entries[TIER0_ID], model_id="ai-engineer:latest", source="user"))

    monkeypatch.setenv("MODEL_NAME", "llama-ai-eng")  # env unmoved; only the registry diverged
    app_mod._export_registry_env()
    assert os.environ.get("MODEL_NAME") == "ai-engineer:latest"


def test_export_does_not_touch_model_name_for_non_ollama_backend(monkeypatch):
    """mlx/cpu/cuda primaries aren't Ollama's env-var story — exporting
    MODEL_NAME for them would be pointless (nothing reads it that way) and
    risks clobbering an unrelated env convention."""
    import arail.portal.app as app_mod

    _isolate_registry(monkeypatch)
    monkeypatch.setenv("MODEL_BACKEND", "mlx")
    monkeypatch.setenv("MODEL_NAME", "some-mlx-model")

    monkeypatch.delenv("MODEL_NAME", raising=False)
    app_mod._export_registry_env()
    assert os.environ.get("MODEL_NAME") is None


def test_export_never_raises_on_registry_failure(monkeypatch):
    import arail.portal.app as app_mod
    import arail.registry as registry_pkg

    def _boom():
        raise RuntimeError("registry file corrupt")

    # _export_registry_env does `from arail.registry import get_registry`
    # (the package-level re-export), so that's the name that must be
    # patched — patching arail.registry.core.get_registry wouldn't affect
    # this already-bound re-export.
    monkeypatch.setattr(registry_pkg, "get_registry", _boom)
    app_mod._export_registry_env()  # must not raise
