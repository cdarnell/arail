"""ModelRouter — single entry-point for all inference backends."""

from __future__ import annotations

import os
from typing import Dict, Iterator, Optional

from arail.router.backends import (BACKEND_MAP, BaseBackend, ModelResponse,
                                   StreamResult)
from arail.costs import cost_tracker, current_recap_depth

# Backends whose inference calls leave this machine. Constructing one of
# these while airgapped is refused up front — the httpx/requests egress
# guard would block the eventual API call anyway, but failing here gives
# an immediate, non-network, user-readable error.
_CLOUD_BACKENDS = frozenset({"claude", "huggingface", "openrouter"})


class CloudBackendBlocked(RuntimeError):
    """A cloud backend was requested while the lab is airgapped."""


def _check_cloud_allowed(name: str) -> None:
    if name in _CLOUD_BACKENDS:
        from arail.airgap import is_airgapped
        if is_airgapped():
            raise CloudBackendBlocked(
                f"The lab is airgapped — the cloud backend '{name}' is "
                "blocked. Click the Airgapped pill in the status bar (or set "
                "LAB_MODE=hybrid in .env) to allow cloud providers, or pick "
                "a local backend."
            )


class ModelRouter:
    """Instantiate the correct backend based on env / config and expose a
    uniform ``complete()`` interface."""

    def __init__(self, backend: str | None = None,
                 *, billing_source: str = "agent") -> None:
        name = (backend or os.getenv("MODEL_BACKEND") or "mlx").lower()
        if name == "auto":
            name = self._auto_detect()
        if name not in BACKEND_MAP:
            raise ValueError(
                f"Unknown backend '{name}'. "
                f"Choose from: {', '.join(BACKEND_MAP)}"
            )
        _check_cloud_allowed(name)
        self.backend_name = name
        self.billing_source = billing_source
        self._backend: BaseBackend = BACKEND_MAP[name]()

    # ------------------------------------------------------------------
    @staticmethod
    def _auto_detect() -> str:
        """Best-effort platform detection (mirrors setup.sh logic)."""
        import platform
        if platform.system() == "Darwin" and platform.machine() == "arm64":
            return "mlx"
        # Check for Nvidia GPU
        import shutil
        if shutil.which("nvidia-smi"):
            return "cuda"
        return "cpu"

    # ------------------------------------------------------------------
    def complete(self, prompt: str, max_tokens: int = 512,
                 temperature: float = 0.7,
                 top_p: Optional[float] = None,
                 *, system: Optional[str] = None,
                 messages: Optional[list] = None) -> ModelResponse:
        response = self._backend.complete(
            prompt, max_tokens, temperature, top_p=top_p,
            system=system, messages=messages,
        )
        # Track cost — estimate input tokens from prompt + frozen prefix length
        tokens_in = max((len(prompt) + len(system or "")) // 4, 1)
        cost_tracker.track(
            backend=response.backend,
            model=response.model,
            tokens_in=tokens_in,
            tokens_out=response.tokens_used,
            latency_ms=response.latency_ms,
            source=self.billing_source,
            recap_depth=current_recap_depth(),
            cache_read_input_tokens=response.cache_read_input_tokens,
            cache_creation_input_tokens=response.cache_creation_input_tokens,
        )
        return response

    def stream_complete(self, prompt: str, max_tokens: int = 512,
                        temperature: float = 0.7,
                        top_p: Optional[float] = None,
                        *, system: Optional[str] = None,
                        messages: Optional[list] = None) -> Iterator[StreamResult]:
        for item in self._backend.stream_complete(
            prompt,
            max_tokens,
            temperature,
            top_p=top_p,
            system=system,
            messages=messages,
        ):
            if isinstance(item, ModelResponse):
                tokens_in = max((len(prompt) + len(system or "")) // 4, 1)
                cost_tracker.track(
                    backend=item.backend,
                    model=item.model,
                    tokens_in=tokens_in,
                    tokens_out=item.tokens_used,
                    latency_ms=item.latency_ms,
                    source=self.billing_source,
                    cache_read_input_tokens=item.cache_read_input_tokens,
                    cache_creation_input_tokens=item.cache_creation_input_tokens,
                )
            yield item

    def health_check(self) -> Dict[str, bool]:
        return {self.backend_name: self._backend.health_check()}

    def switch_backend(self, name: str) -> None:
        if name not in BACKEND_MAP:
            raise ValueError(f"Unknown backend: {name}")
        _check_cloud_allowed(name)
        self.backend_name = name
        self._backend = BACKEND_MAP[name]()
