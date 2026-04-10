"""ModelRouter — single entry-point for all inference backends."""

from __future__ import annotations

import os
from typing import Dict

from oglab.router.backends import BACKEND_MAP, BaseBackend, ModelResponse
from oglab.costs import cost_tracker


class ModelRouter:
    """Instantiate the correct backend based on env / config and expose a
    uniform ``complete()`` interface."""

    def __init__(self, backend: str | None = None) -> None:
        name = (backend or os.getenv("MODEL_BACKEND", "mlx")).lower()
        if name == "auto":
            name = self._auto_detect()
        if name not in BACKEND_MAP:
            raise ValueError(
                f"Unknown backend '{name}'. "
                f"Choose from: {', '.join(BACKEND_MAP)}"
            )
        self.backend_name = name
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
                 temperature: float = 0.7) -> ModelResponse:
        response = self._backend.complete(prompt, max_tokens, temperature)
        # Track cost — estimate input tokens from prompt length
        tokens_in = max(len(prompt) // 4, 1)
        cost_tracker.track(
            backend=response.backend,
            model=response.model,
            tokens_in=tokens_in,
            tokens_out=response.tokens_used,
            latency_ms=response.latency_ms,
        )
        return response

    def health_check(self) -> Dict[str, bool]:
        return {self.backend_name: self._backend.health_check()}

    def switch_backend(self, name: str) -> None:
        if name not in BACKEND_MAP:
            raise ValueError(f"Unknown backend: {name}")
        self.backend_name = name
        self._backend = BACKEND_MAP[name]()
