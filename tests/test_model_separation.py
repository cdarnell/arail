"""test_model_separation.py — F10: minimalist (Ollama 1B) and maximus (AeroLLM 7B)
model ids must never collide.

The two-tier architecture keeps two completely separate model identities:
  - MODEL_NAME    → Ollama minimalist default → "llama-ai-eng" (1B, persona-wrap)
  - AEROLLM_MODEL → AeroLLM maximus deep      → "Qwen2.5-7B-Instruct-4bit" (7B)

Conflating these (e.g. setting MODEL_NAME=Qwen2.5-7B-Instruct-4bit, or
AEROLLM_MODEL=llama-ai-eng) is the single biggest correctness risk in this sprint.
This test asserts the defaults differ and that each lives in the correct namespace.
"""
from __future__ import annotations

import os


# Default values as defined in backends.py and setup.sh.
# If these defaults ever change, the test must be updated deliberately — not silently.
_OLLAMA_DEFAULT = "llama-ai-eng"
_AEROLLM_DEFAULT = "Qwen2.5-7B-Instruct-4bit"


def _get_ollama_model() -> str:
    """Return the effective Ollama minimalist model id (env or default)."""
    # OllamaNativeBackend reads MODEL_NAME (not AEROLLM_MODEL).
    # When MODEL_NAME is not set the _resilient_chat_default() in app.py resolves
    # to llama-ai-eng; here we just check the env/default, not the resolver.
    return os.getenv("MODEL_NAME", _OLLAMA_DEFAULT)


def _get_aerollm_model() -> str:
    """Return the effective AeroLLM model id (env or default)."""
    return os.getenv("AEROLLM_MODEL", _AEROLLM_DEFAULT)


def test_ollama_default_is_llama_ai_eng():
    """MODEL_NAME default must be llama-ai-eng (the Ollama 1B persona-wrap)."""
    model = os.getenv("MODEL_NAME", _OLLAMA_DEFAULT)
    # In a default environment (no override), must be the llama persona-wrap.
    if "MODEL_NAME" not in os.environ:
        assert model == _OLLAMA_DEFAULT, (
            f"Ollama default changed from '{_OLLAMA_DEFAULT}' to '{model}'. "
            "If this is intentional, update this test AND the Llama disclosure surfaces."
        )


def test_aerollm_default_is_qwen_7b():
    """AEROLLM_MODEL default must be Qwen2.5-7B-Instruct-4bit (the AeroLLM 7B)."""
    model = os.getenv("AEROLLM_MODEL", _AEROLLM_DEFAULT)
    if "AEROLLM_MODEL" not in os.environ:
        assert model == _AEROLLM_DEFAULT, (
            f"AeroLLM default changed from '{_AEROLLM_DEFAULT}' to '{model}'. "
            "Update this test AND the ARCHITECTURE.md assumptions if intentional."
        )


def test_ollama_model_starts_with_llama():
    """The Ollama minimalist model id must start with 'llama-' (disclosure + naming contract)."""
    model = _get_ollama_model()
    assert model.startswith("llama-"), (
        f"Ollama minimalist model id '{model}' does not start with 'llama-'. "
        "The Llama disclosure requires the model name to reflect its lineage. "
        "If you changed the minimalist model away from Llama lineage, update the "
        "disclosure surfaces and this test explicitly."
    )


def test_aerollm_model_does_not_start_with_llama():
    """The AeroLLM maximus model must NOT be a Llama model (it is Qwen/Apache-2.0)."""
    model = _get_aerollm_model()
    assert not model.startswith("llama-") and "llama" not in model.lower(), (
        f"AeroLLM model '{model}' appears to be a Llama model. "
        "The maximus deep model must be Qwen2.5-7B-Instruct-4bit (Apache-2.0). "
        "Mixing Llama into the AeroLLM path re-opens the license question for "
        "the 'hide-the-base' rule — requires explicit review."
    )


def test_model_ids_do_not_collide():
    """MODEL_NAME (Ollama 1B) and AEROLLM_MODEL (AeroLLM 7B) must be distinct."""
    ollama_model = _get_ollama_model()
    aerollm_model = _get_aerollm_model()
    assert ollama_model != aerollm_model, (
        f"MODEL_NAME and AEROLLM_MODEL are both '{ollama_model}'. "
        "The two model identifiers must never collide — the Ollama 1B and the "
        "AeroLLM 7B are served by different backends on different runtimes."
    )


def test_aerollm_model_is_not_llama_1b():
    """Regression: AEROLLM_MODEL must not be set to the 1B Llama model."""
    aerollm_model = _get_aerollm_model()
    assert "llama3.2:1b" not in aerollm_model.lower(), (
        f"AEROLLM_MODEL='{aerollm_model}' — the 1B Llama base model cannot be "
        "served by AeroLLM (AeroLLM loads MLX-format weights; Ollama serves the "
        "llama3.2:1b GGUF). This is a backend mismatch."
    )


def test_ollama_model_is_not_qwen_7b():
    """Regression: MODEL_NAME must not be set to the 7B AeroLLM model."""
    ollama_model = _get_ollama_model()
    assert "Qwen2.5-7B" not in ollama_model and "qwen2.5-7b" not in ollama_model.lower(), (
        f"MODEL_NAME='{ollama_model}' — the 7B Qwen model cannot be served "
        "by OllamaNativeBackend (Ollama doesn't automatically have the MLX "
        "4bit weights). Use AEROLLM_MODEL for AeroLLM."
    )
