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

        self.model_name = os.getenv("MODEL_NAME",
                                     "mlx-community/Mistral-7B-Instruct-v0.3-4bit")
        # Allow local path first, fallback to hub name
        model_dir = os.path.join(os.getenv("OGLAB_MODELS_DIR", "./models"),
                                 self.model_name.split("/")[-1])
        path = model_dir if os.path.isdir(model_dir) else self.model_name
        self.model, self.tokenizer = self._load(path)

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7) -> ModelResponse:
        start = time.time()
        text = self._generate(self.model, self.tokenizer,
                              prompt=prompt, max_tokens=max_tokens,
                              temp=temperature, verbose=False)
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
                                     "mistralai/Mistral-7B-Instruct-v0.2")

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
        models_dir = os.getenv("OGLAB_MODELS_DIR", "./models")
        # If MODEL_NAME isn't an absolute path, look inside models dir
        if not os.path.isabs(model_path):
            candidates = list(
                p for p in __import__("pathlib").Path(models_dir).glob("*.gguf")
            )
            if candidates:
                model_path = str(candidates[0])
            else:
                raise FileNotFoundError(
                    f"No .gguf model found in {models_dir}. "
                    "Download one — see docs/SETUP.md"
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
            "MODEL_NAME", "mistralai/Mistral-7B-Instruct-v0.2"
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
            "MODEL_NAME", "mistralai/mistral-7b-instruct"
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
}
