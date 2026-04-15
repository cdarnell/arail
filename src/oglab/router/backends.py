"""Backend implementations for every supported accelerator / cloud service."""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Shared response type
# ---------------------------------------------------------------------------
@dataclass
class ModelResponse:
    text: str
    model: str
    tokens_used: int
    backend: str
    latency_ms: float
    cost_usd: Optional[float] = None


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class BaseBackend(ABC):
    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        ...

    @abstractmethod
    def health_check(self) -> bool:
        ...


# ---------------------------------------------------------------------------
# MLX  (macOS Apple Silicon — completely local)
# ---------------------------------------------------------------------------
class MLXBackend(BaseBackend):
    def __init__(self) -> None:
        try:
            from mlx_lm import load, generate  # type: ignore[import-untyped]
            self._load = load
            self._generate = generate
        except ImportError:
            raise ImportError("MLX not installed. Run: pip install mlx mlx-lm")

        # New-style sampler factory is preferred; fall back to the old
        # `temp=` kwarg if we're on a pre-0.19 mlx-lm.
        try:
            from mlx_lm.sample_utils import make_sampler  # type: ignore[import-untyped]
            self._make_sampler = make_sampler
        except ImportError:  # pragma: no cover — only on old mlx-lm
            self._make_sampler = None

        self.model_name = os.getenv("MODEL_NAME",
                                     "mlx-community/Qwen3-8B-4bit")
        # Allow local path first, fallback to hub name
        model_dir = os.path.join(os.getenv("OGLAB_MODELS_DIR", "lab/models"),
                                 self.model_name.split("/")[-1])
        path = model_dir if os.path.isdir(model_dir) else self.model_name
        self.model, self.tokenizer = self._load(path)

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        # mlx-lm ≥ 0.19 removed the `temp=` kwarg on generate(); you now
        # build a sampler via make_sampler(temp=...) and pass it as
        # `sampler=`. Old versions still accept `temp=` directly.
        if self._make_sampler is not None:
            sampler = self._make_sampler(temp=temperature)
            text = self._generate(
                self.model, self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                sampler=sampler,
                verbose=False,
            )
        else:
            text = self._generate(
                self.model, self.tokenizer,
                prompt=prompt,
                max_tokens=max_tokens,
                temp=temperature,
                verbose=False,
            )
        return ModelResponse(
            text=text,
            model=self.model_name,
            tokens_used=len(self.tokenizer.encode(text)),
            backend="mlx",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            r = self.complete("test", max_tokens=5)
            return len(r.text) > 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
# CUDA  (Linux / WSL — local Nvidia GPU via vLLM OpenAI-compat server)
# ---------------------------------------------------------------------------
class CUDABackend(BaseBackend):
    def __init__(self) -> None:
        import requests  # noqa: F811
        self._session = requests.Session()
        self.port = int(os.getenv("LOCAL_API_PORT", "8000"))
        self.model_name = os.getenv("MODEL_NAME",
                                     "Qwen/Qwen3-8B")

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        resp = self._session.post(
            f"http://localhost:{self.port}/v1/completions",
            json={"prompt": prompt, "max_tokens": max_tokens,
                  "temperature": temperature},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["text"],
            model=self.model_name,
            tokens_used=data.get("usage", {}).get("completion_tokens", 0),
            backend="cuda",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            r = self._session.get(f"http://localhost:{self.port}/health",
                                  timeout=5)
            return r.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# CPU  (llama.cpp via llama-cpp-python — any OS, no GPU)
# ---------------------------------------------------------------------------
class CPUBackend(BaseBackend):
    def __init__(self) -> None:
        try:
            from llama_cpp import Llama  # type: ignore[import-untyped]
        except ImportError:
            raise ImportError("Run: pip install llama-cpp-python")

        model_path = os.getenv("MODEL_NAME", "")
        models_dir = os.getenv("OGLAB_MODELS_DIR", "lab/models")
        # If MODEL_NAME isn't an absolute path, look inside models dir
        if not os.path.isabs(model_path):
            pathlib = __import__("pathlib")
            models_root = pathlib.Path(models_dir)
            requested_name = os.path.basename(model_path)
            requested_stem = requested_name.rsplit(".", 1)[0].lower()
            requested_dir = requested_name.lower()

            candidates = sorted(models_root.rglob("*.gguf"))
            preferred = [
                candidate for candidate in candidates
                if requested_stem and (
                    requested_stem in candidate.name.lower()
                    or requested_dir in str(candidate.parent).lower()
                )
            ]

            if preferred:
                model_path = str(preferred[0])
            elif candidates:
                model_path = str(candidates[0])
            else:
                raise FileNotFoundError(
                    f"No .gguf model found in {models_dir}. "
                    "Download one — see README.md"
                )
        self.model_name = os.path.basename(model_path)
        self.llm = Llama(model_path=model_path, n_ctx=4096, verbose=False)

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        out = self.llm(prompt, max_tokens=max_tokens, temperature=temperature)
        text = out["choices"][0]["text"]  # type: ignore[index]
        return ModelResponse(
            text=text,
            model=self.model_name,
            tokens_used=out.get("usage", {}).get("completion_tokens", 0),
            backend="cpu",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            r = self.complete("test", max_tokens=5)
            return len(r.text) > 0
        except Exception:
            return False


# ---------------------------------------------------------------------------
# HuggingFace Inference API  (cloud — free tier)
# ---------------------------------------------------------------------------
class HuggingFaceBackend(BaseBackend):
    def __init__(self) -> None:
        api_key = os.getenv("HUGGINGFACE_API_KEY")
        if not api_key:
            raise ValueError("HUGGINGFACE_API_KEY not set")
        from huggingface_hub import InferenceClient  # type: ignore[import-untyped]
        self.client = InferenceClient(api_key=api_key)
        self.model_name = os.getenv(
            "MODEL_NAME", "Qwen/Qwen3-8B"
        )

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        text = self.client.text_generation(
            prompt=prompt, max_new_tokens=max_tokens,
            temperature=temperature, model=self.model_name
        )
        return ModelResponse(
            text=text,
            model=self.model_name,
            tokens_used=len(prompt.split()) + len(text.split()),
            backend="huggingface",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            self.complete("test", max_tokens=5)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# OpenRouter  (cloud — free tier, multiple models)
# ---------------------------------------------------------------------------
class OpenRouterBackend(BaseBackend):
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("OPENROUTER_API_KEY not set")
        import requests
        self._session = requests.Session()
        self.model_name = os.getenv(
            "MODEL_NAME", "Qwen/Qwen3-8B"
        )

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        resp = self._session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json={"model": self.model_name,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": temperature,
                  "max_tokens": max_tokens},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            model=self.model_name,
            tokens_used=data.get("usage", {}).get("completion_tokens", 0),
            backend="openrouter",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            self.complete("test", max_tokens=5)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Anthropic Claude  (cloud — paid)
# ---------------------------------------------------------------------------
class ClaudeBackend(BaseBackend):
    def __init__(self) -> None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not set")
        import anthropic  # type: ignore[import-untyped]
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model_name = os.getenv("MODEL_NAME", "claude-sonnet-4-20250514")

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        resp = self.client.messages.create(
            model=self.model_name,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return ModelResponse(
            text=resp.content[0].text,
            model=self.model_name,
            tokens_used=resp.usage.output_tokens,
            backend="claude",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=None,
        )

    def health_check(self) -> bool:
        try:
            self.complete("test", max_tokens=5)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# OpenAI-compatible local server  (LM Studio / Ollama / DeployLM)
# ---------------------------------------------------------------------------
class OpenAICompatBackend(BaseBackend):
    """Talks to any server that exposes the OpenAI /v1/chat/completions
    endpoint on localhost.  Works with LM Studio, Ollama, DeployLM, etc."""

    def __init__(self) -> None:
        import requests
        self._session = requests.Session()
        self.base_url = os.getenv("MODEL_API_BASE",
                                   "http://localhost:1234/v1").rstrip("/")
        self.model_name = os.getenv("MODEL_NAME", "default")
        self.api_key = os.getenv("MODEL_API_KEY", "not-needed")

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        resp = self._session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json={"model": self.model_name,
                  "messages": [{"role": "user", "content": prompt}],
                  "temperature": temperature,
                  "max_tokens": max_tokens},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        return ModelResponse(
            text=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model_name),
            tokens_used=data.get("usage", {}).get("completion_tokens", 0),
            backend="openai_compat",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        try:
            r = self._session.get(f"{self.base_url}/models", timeout=5)
            return r.status_code == 200
        except Exception:
            return False


# ---------------------------------------------------------------------------
# AirLLM  (layer-by-layer from disk — 70B+ on minimal RAM)
# ---------------------------------------------------------------------------
class AirLLMBackend(BaseBackend):
    """Run massive models (70B-405B) from disk via AirLLM.

    Layer-by-layer inference: only one transformer layer is loaded into
    memory at a time.  Slow (seconds-per-token) but lets you run models
    that would normally need 48+ GB VRAM on a 4 GB machine.
    """

    def __init__(self) -> None:
        try:
            from airllm import AutoModel  # type: ignore[import-untyped]
            self._AutoModel = AutoModel
        except ImportError:
            raise ImportError(
                "AirLLM not installed. Run: pip install airllm"
            )

        self.model_name = os.getenv(
            "AIRLLM_MODEL", "Qwen/Qwen3-8B"
        )
        compression = os.getenv("AIRLLM_COMPRESSION", "4bit") or None
        if compression == "none":
            compression = None

        models_dir = os.getenv("OGLAB_MODELS_DIR", "lab/models")
        cache_dir = os.path.join(models_dir, "airllm_cache")
        os.makedirs(cache_dir, exist_ok=True)

        # Check for local download first, fall back to hub ID
        local_dir = os.path.join(models_dir, self.model_name.split("/")[-1])
        model_path = local_dir if os.path.isdir(local_dir) else self.model_name

        self.model = self._AutoModel.from_pretrained(
            model_path,
            compression=compression,
            layer_shards_saving_path=cache_dir,
        )
        self._max_length = int(os.getenv("AIRLLM_MAX_LENGTH", "512"))

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()

        input_tokens = self.model.tokenizer(
            [prompt],
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=self._max_length,
            padding=False,
        )

        generation = self.model.generate(
            input_tokens["input_ids"].cuda()
            if __import__("torch").cuda.is_available()
            else input_tokens["input_ids"],
            max_new_tokens=max_tokens,
            use_cache=True,
            return_dict_in_generate=True,
        )
        text = self.model.tokenizer.decode(
            generation.sequences[0], skip_special_tokens=True
        )
        # Strip the input prompt from the output
        if text.startswith(prompt):
            text = text[len(prompt):]
        text = text.strip()

        tokens_used = len(generation.sequences[0]) - len(input_tokens["input_ids"][0])

        return ModelResponse(
            text=text,
            model=self.model_name,
            tokens_used=max(tokens_used, 0),
            backend="airllm",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        # Full generation is too slow for a health check.
        # Verify the model object and tokenizer are loaded.
        try:
            return (
                self.model is not None
                and self.model.tokenizer is not None
            )
        except Exception:
            return False


# ---------------------------------------------------------------------------
# Registry used by ModelRouter
# ---------------------------------------------------------------------------
BACKEND_MAP: dict[str, type[BaseBackend]] = {
    "mlx": MLXBackend,
    "cuda": CUDABackend,
    "cpu": CPUBackend,
    "openai_compat": OpenAICompatBackend,
    "huggingface": HuggingFaceBackend,
    "openrouter": OpenRouterBackend,
    "claude": ClaudeBackend,
    "airllm": AirLLMBackend,
}
