"""Backend implementations for every supported accelerator / cloud service."""

from __future__ import annotations

import atexit
import os
import time
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional


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


StreamResult = str | ModelResponse


def _coerce_stream_text(item: Any, current_text: str) -> tuple[str, str]:
    """Normalize backend-specific stream items into ``(full, delta)``."""
    raw: Any
    if isinstance(item, str):
        raw = item
    else:
        raw = getattr(item, "text", None)
        if raw is None:
            raw = getattr(item, "token", None)
        if raw is None:
            raw = getattr(item, "content", None)
        if raw is None:
            raw = str(item)

    text = str(raw or "")
    if not text:
        return current_text, ""
    if current_text and text.startswith(current_text):
        return text, text[len(current_text):]
    return current_text + text, text


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class BaseBackend(ABC):
    @abstractmethod
    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        """Run one completion.

        ``top_p`` is optional. When None, the backend uses its default
        sampling policy. Preset buttons on the dashboard set it to
        specific values (0.9 for Factual, 0.95 for Code, etc.).
        Backends that don't support top_p ignore it silently.
        """
        ...

    def stream_complete(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7,
                        top_p: Optional[float] = None) -> Iterator[StreamResult]:
        """Yield text deltas and finish with a ``ModelResponse``.

        Backends that do not support native streaming fall back to one
        blocking completion and yield the final response as a single item.
        """
        yield self.complete(prompt, max_tokens, temperature, top_p=top_p)

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
            import mlx_lm as _mlx_lm  # type: ignore[import-untyped]
            self._load = load
            self._generate = generate
            self._stream_generate = getattr(_mlx_lm, "stream_generate", None)
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
        model_dir = os.path.join(os.getenv("ARAIL_MODELS_DIR", "lab/models"),
                                 self.model_name.split("/")[-1])
        path = model_dir if os.path.isdir(model_dir) else self.model_name
        self.model, self.tokenizer = self._load(path)

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        # Memory-pressure guard. Clears the Metal cache and refuses
        # the call when accumulated activations have crossed the
        # configurable threshold (default 85%). The Metal allocator
        # OOM is a C++ exception that bypasses Python try/except, so
        # we'd rather surface a typed Python error here than let it
        # nuke the parent process. Callers (e.g. goal_parser) catch
        # MetalOutOfMemory and fall back to heuristic / smaller path.
        from arail.router.mlx_guard import assert_metal_safe, clear_metal_cache
        assert_metal_safe(op=f"MLX generate({self.model_name})")
        try:
            # mlx-lm ≥ 0.19 removed the `temp=` kwarg on generate(); you
            # now build a sampler via make_sampler(temp=...) and pass it
            # as `sampler=`. Old versions still accept `temp=` directly.
            if self._make_sampler is not None:
                sampler_kwargs = {"temp": temperature}
                if top_p is not None:
                    sampler_kwargs["top_p"] = top_p
                sampler = self._make_sampler(**sampler_kwargs)
                text = self._generate(
                    self.model, self.tokenizer,
                    prompt=prompt,
                    max_tokens=max_tokens,
                    sampler=sampler,
                    verbose=False,
                )
            else:
                # Pre-0.19 mlx-lm has no top_p support; silently drop it.
                # Some mid-version mlx-lm builds removed `temp=` but also
                # lack make_sampler — guard with a fallback to avoid the
                # repeated "unexpected keyword argument 'temp'" crash.
                try:
                    text = self._generate(
                        self.model, self.tokenizer,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        temp=temperature,
                        verbose=False,
                    )
                except TypeError:
                    # Newer generate() that dropped temp= but predates
                    # make_sampler.
                    text = self._generate(
                        self.model, self.tokenizer,
                        prompt=prompt,
                        max_tokens=max_tokens,
                        verbose=False,
                    )
        finally:
            # Always release activations after a generation pass —
            # leaving them in flight makes the next assert_metal_safe
            # spuriously refuse despite the model itself being smaller
            # than the limit.
            clear_metal_cache()
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

    def stream_complete(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7,
                        top_p: Optional[float] = None) -> Iterator[StreamResult]:
        if self._stream_generate is None:
            yield self.complete(prompt, max_tokens, temperature, top_p=top_p)
            return

        start = time.time()
        sampler = None
        if self._make_sampler is not None:
            sampler_kwargs = {"temp": temperature}
            if top_p is not None:
                sampler_kwargs["top_p"] = top_p
            sampler = self._make_sampler(**sampler_kwargs)

        kwargs: dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens,
        }
        if sampler is not None:
            kwargs["sampler"] = sampler

        full_text = ""
        for item in self._stream_generate(self.model, self.tokenizer, **kwargs):
            full_text, delta = _coerce_stream_text(item, full_text)
            if delta:
                yield delta

        yield ModelResponse(
            text=full_text,
            model=self.model_name,
            tokens_used=len(self.tokenizer.encode(full_text)),
            backend="mlx",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )


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
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        body: dict = {"prompt": prompt, "max_tokens": max_tokens,
                      "temperature": temperature}
        if top_p is not None:
            body["top_p"] = top_p
        resp = self._session.post(
            f"http://localhost:{self.port}/v1/completions",
            json=body,
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

    def stream_complete(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7,
                        top_p: Optional[float] = None) -> Iterator[StreamResult]:
        start = time.time()
        body: dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if top_p is not None:
            body["top_p"] = top_p

        full_text = ""
        tokens_used = 0
        with self._session.post(
            f"http://localhost:{self.port}/v1/completions",
            json=body,
            timeout=120,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    data = __import__("json").loads(payload)
                except Exception:
                    continue
                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("text") or ""
                if delta:
                    full_text += delta
                    yield delta
                usage = data.get("usage") or {}
                if usage.get("completion_tokens") is not None:
                    tokens_used = int(usage["completion_tokens"])

        yield ModelResponse(
            text=full_text,
            model=self.model_name,
            tokens_used=tokens_used or len(full_text.split()),
            backend="cuda",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )


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
        models_dir = os.getenv("ARAIL_MODELS_DIR", "lab/models")
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
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        kwargs: dict = {"max_tokens": max_tokens, "temperature": temperature}
        if top_p is not None:
            kwargs["top_p"] = top_p
        out = self.llm(prompt, **kwargs)
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
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        kwargs: dict = {
            "prompt": prompt, "max_new_tokens": max_tokens,
            "temperature": temperature, "model": self.model_name,
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        text = self.client.text_generation(**kwargs)
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
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        payload: dict = {"model": self.model_name,
                         "messages": [{"role": "user", "content": prompt}],
                         "temperature": temperature,
                         "max_tokens": max_tokens}
        if top_p is not None:
            payload["top_p"] = top_p
        resp = self._session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
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

    def stream_complete(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7,
                        top_p: Optional[float] = None) -> Iterator[StreamResult]:
        start = time.time()
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if top_p is not None:
            payload["top_p"] = top_p

        full_text = ""
        tokens_used = 0
        with self._session.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=120,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload_line = line[5:].strip()
                if payload_line == "[DONE]":
                    break
                try:
                    data = __import__("json").loads(payload_line)
                except Exception:
                    continue
                choice = (data.get("choices") or [{}])[0]
                delta = (((choice.get("delta") or {}).get("content"))
                         or choice.get("text")
                         or "")
                if delta:
                    full_text += delta
                    yield delta
                usage = data.get("usage") or {}
                if usage.get("completion_tokens") is not None:
                    tokens_used = int(usage["completion_tokens"])

        yield ModelResponse(
            text=full_text,
            model=self.model_name,
            tokens_used=tokens_used or len(full_text.split()),
            backend="openrouter",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )


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
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        kwargs: dict = {
            "model": self.model_name,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if top_p is not None:
            kwargs["top_p"] = top_p
        resp = self.client.messages.create(**kwargs)
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
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        payload: dict = {"model": self.model_name,
                         "messages": [{"role": "user", "content": prompt}],
                         "temperature": temperature,
                         "max_tokens": max_tokens}
        if top_p is not None:
            payload["top_p"] = top_p
        resp = self._session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
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

    def stream_complete(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7,
                        top_p: Optional[float] = None) -> Iterator[StreamResult]:
        start = time.time()
        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if top_p is not None:
            payload["top_p"] = top_p

        full_text = ""
        tokens_used = 0
        with self._session.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=120,
            stream=True,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload_line = line[5:].strip()
                if payload_line == "[DONE]":
                    break
                try:
                    data = __import__("json").loads(payload_line)
                except Exception:
                    continue
                choice = (data.get("choices") or [{}])[0]
                delta = (((choice.get("delta") or {}).get("content"))
                         or choice.get("text")
                         or "")
                if delta:
                    full_text += delta
                    yield delta
                usage = data.get("usage") or {}
                if usage.get("completion_tokens") is not None:
                    tokens_used = int(usage["completion_tokens"])

        yield ModelResponse(
            text=full_text,
            model=self.model_name,
            tokens_used=tokens_used or len(full_text.split()),
            backend="openai_compat",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# AirLLM  (layer-streaming baseline — 70B on constrained hardware)
# ---------------------------------------------------------------------------
class AirLLMBackend(BaseBackend):
    """Run large Hugging Face models via AirLLM's layer streaming path."""

    def __init__(self) -> None:
        try:
            from airllm import AutoModel  # type: ignore
            self._AutoModel = AutoModel
        except ImportError:
            raise ImportError("AirLLM not installed. Run: pip install airllm")

        self.model_name = os.getenv(
            "AIRLLM_MODEL",
            "meta-llama/Llama-3.1-70B",
        )
        compression = os.getenv("AIRLLM_COMPRESSION", "4bit") or None
        if compression == "none":
            compression = None

        models_dir = os.getenv("ARAIL_MODELS_DIR", "lab/models")
        cache_dir = os.path.join(models_dir, "airllm_cache")
        os.makedirs(cache_dir, exist_ok=True)

        local_dir = os.path.join(models_dir, self.model_name.split("/")[-1])
        model_path = local_dir if os.path.isdir(local_dir) else self.model_name

        load_kwargs: dict[str, Any] = {
            "compression": compression,
            "layer_shards_saving_path": cache_dir,
        }
        hf_token = os.getenv("HF_TOKEN")
        if hf_token:
            load_kwargs["hf_token"] = hf_token

        self.model = self._AutoModel.from_pretrained(model_path, **load_kwargs)
        self._max_length = int(os.getenv("AIRLLM_MAX_LENGTH", "512"))

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()

        input_tokens = self.model.tokenizer(
            [prompt],
            return_tensors="pt",
            return_attention_mask=False,
            truncation=True,
            max_length=self._max_length,
            padding=False,
        )

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_tokens,
            "use_cache": True,
            "return_dict_in_generate": True,
        }
        if temperature != 1.0 or top_p is not None:
            gen_kwargs["do_sample"] = True
            gen_kwargs["temperature"] = temperature
            if top_p is not None:
                gen_kwargs["top_p"] = top_p

        input_ids = input_tokens["input_ids"]
        torch = __import__("torch")
        if torch.cuda.is_available():
            input_ids = input_ids.cuda()

        generation = self.model.generate(input_ids, **gen_kwargs)
        text = self.model.tokenizer.decode(
            generation.sequences[0], skip_special_tokens=True
        )
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
        try:
            return (
                self.model is not None
                and self.model.tokenizer is not None
            )
        except Exception:
            return False


# ---------------------------------------------------------------------------
# AeroLLM  (in-process Rust runtime via the aero_api PyO3 wheel)
# ---------------------------------------------------------------------------
class AeroLLMBackend(BaseBackend):
    """Drive the AeroLLM Rust runtime through its `aero_api` PyO3 wheel.

    The wheel ships from `aerollm/crates/aero-api` (build with
    ``maturin develop --release``). Apple Silicon uses the in-process
    ``mlx-native`` backend; on other hosts the wheel falls back to the
    legacy subprocess shim (``mlx``).

    Default model: ``Qwen2.5-7B-Instruct`` resolved against
    ``ARAIL_MODELS_DIR`` (so a local checkpoint at
    ``$ARAIL_MODELS_DIR/Qwen2.5-7B-Instruct`` is picked up
    automatically). Set ``AEROLLM_MODEL`` to override the directory
    name.

    Threading: ``aero_api.Runtime`` is unsendable (MLX Metal context
    is thread-affine). All Runtime ops are pinned to a dedicated
    single-worker ``ThreadPoolExecutor`` so FastAPI's threadpool
    dispatch can hop into and out of this backend without touching
    the underlying handle from a foreign thread. Process shutdown
    may print one ``RuntimeError: ... unsendable, but is being
    dropped on another thread`` to stderr — that's Python's GC
    ordering interacting with our atexit handler, not a runtime bug.
    """

    def __init__(self) -> None:
        try:
            from aero_api import Runtime  # type: ignore[import-untyped]
        except ImportError as e:
            raise ImportError(
                "aero_api wheel not installed. Build it with: "
                "cd aerollm/crates/aero-api && maturin develop --release"
            ) from e

        self.model_name = os.getenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct")
        models_dir = os.getenv("ARAIL_MODELS_DIR", "lab/models")
        # Accept either a bare directory name (resolved against
        # ARAIL_MODELS_DIR) or an absolute path. The bare-name form is
        # the common case for the chat catalog; the absolute path
        # exists for ad-hoc operator use.
        if os.path.isabs(self.model_name):
            model_path = self.model_name
        else:
            model_path = os.path.join(models_dir, self.model_name)

        if not os.path.isdir(model_path):
            raise RuntimeError(
                f"AeroLLM model dir not found: {model_path}. "
                f"Set AEROLLM_MODEL and/or ARAIL_MODELS_DIR, or "
                f"download the checkpoint with `huggingface-cli download "
                f"Qwen/Qwen2.5-7B-Instruct --local-dir {model_path}`."
            )

        # Optional speculative-decoding draft. When AEROLLM_DRAFT_MODEL
        # is set and points at a directory under ARAIL_MODELS_DIR, the
        # runtime preloads a second backend; complete() does not yet
        # surface the spec-decode flag (chat path stays single-seq for
        # simplicity), but having the draft resident means a future
        # toggle costs only a kwarg flip, not a reload.
        draft_name = os.getenv("AEROLLM_DRAFT_MODEL")
        draft_path: Optional[str] = None
        if draft_name:
            cand = draft_name if os.path.isabs(draft_name) else os.path.join(models_dir, draft_name)
            if os.path.isdir(cand):
                draft_path = cand

        rt_kwargs: dict[str, Any] = {}
        if draft_path:
            rt_kwargs["draft_model"] = draft_path
        ring_depth = os.getenv("AEROLLM_RING_DEPTH")
        if ring_depth and ring_depth.isdigit() and int(ring_depth) > 0:
            rt_kwargs["ring_depth"] = int(ring_depth)

        self._model_path = model_path
        self._draft_path = draft_path

        # The aero_api Runtime is unsendable: PyO3 panics if the handle
        # is touched from a thread other than the one that constructed
        # it (MLX's Metal context is thread-affine). FastAPI's
        # `run_in_threadpool` dispatches deep_backend.complete() onto a
        # worker thread, so we'd hit the panic on the second chat turn.
        # Pin the Runtime to a dedicated single-worker executor: the
        # constructor builds it on the worker, and every complete()
        # call routes back through the same worker. The cost is one
        # extra thread-hop per call (~µs); the benefit is a runtime
        # that survives FastAPI's threading model unchanged.
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="aerollm-rt"
        )
        self._runtime: Any = None  # populated on the worker thread
        self._closed = False
        self._executor.submit(self._init_runtime, Runtime, model_path, rt_kwargs).result()
        # Drop the Runtime on the worker thread at process exit. Without
        # this, Python's GC can drop the unsendable handle from the main
        # thread and PyO3 raises RuntimeError during shutdown.
        atexit.register(self._close)

    def _init_runtime(self, runtime_cls: Any, model_path: str,
                      rt_kwargs: dict[str, Any]) -> None:
        """Construct + start the Runtime. Must run on the executor
        worker thread so the Metal context is bound to it."""
        rt = runtime_cls(model_path, **rt_kwargs)
        rt.start()
        self._runtime = rt

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            # Drop the Runtime on the worker thread it was built on.
            self._executor.submit(self._drop_runtime_on_worker).result(timeout=10)
        except Exception:
            pass
        try:
            self._executor.shutdown(wait=True, cancel_futures=True)
        except Exception:
            pass

    def _drop_runtime_on_worker(self) -> None:
        self._runtime = None

    @staticmethod
    def _wrap_chatml(prompt: str) -> str:
        """Wrap a bare prompt in Qwen2.5 ChatML so the instruct tuning
        actually fires. If the caller already produced ChatML (e.g. via
        a tokenizer's apply_chat_template upstream), pass it through
        unchanged to avoid double-wrapping."""
        if "<|im_start|>" in prompt:
            return prompt
        return (
            "<|im_start|>system\nYou are a concise, helpful assistant.<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

    def _generate_on_worker(self, wrapped: str,
                            gen_kwargs: dict[str, Any]) -> str:
        """Run on the executor worker. Holds the unsendable invariant."""
        return self._runtime.generate(wrapped, **gen_kwargs)

    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7,
                 top_p: Optional[float] = None) -> ModelResponse:
        start = time.time()
        wrapped = self._wrap_chatml(prompt)

        gen_kwargs: dict[str, Any] = {
            "max_new_tokens": max_tokens,
            "temperature": float(temperature),
        }
        if top_p is not None:
            gen_kwargs["top_p"] = float(top_p)

        # Hop to the dedicated runtime thread; .result() blocks until
        # it returns. If the worker raises, .result() re-raises here.
        text = self._executor.submit(
            self._generate_on_worker, wrapped, gen_kwargs
        ).result()

        # The runtime returns just the decoded continuation, but it
        # may include a trailing <|im_end|>; strip it. Older shim
        # paths sometimes echo the prompt — strip that defensively
        # too.
        if text.startswith(wrapped):
            text = text[len(wrapped):]
        text = text.replace("<|im_end|>", "").strip()

        # aero_api doesn't surface output-token count yet (planned in
        # a follow-up via generate_with_stats). Approximate with a
        # word-count fallback to match the AirLLMBackend style — good
        # enough for the dashboard's tok/min headline; the criterion
        # bench is the authoritative source for real tok/s numbers.
        tokens_used = max(len(text.split()), 0)

        return ModelResponse(
            text=text,
            model=self.model_name,
            tokens_used=tokens_used,
            backend="aerollm",
            latency_ms=(time.time() - start) * 1000,
            cost_usd=0.0,
        )

    def health_check(self) -> bool:
        return getattr(self, "_runtime", None) is not None


# ---------------------------------------------------------------------------
# Registry used by ModelRouter
# ---------------------------------------------------------------------------
BACKEND_MAP: dict[str, type[BaseBackend]] = {
    "mlx": MLXBackend,
    "cuda": CUDABackend,
    "cpu": CPUBackend,
    "airllm": AirLLMBackend,
    "openai_compat": OpenAICompatBackend,
    "huggingface": HuggingFaceBackend,
    "openrouter": OpenRouterBackend,
    "claude": ClaudeBackend,
    "aerollm": AeroLLMBackend,
}
