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


def _is_importable(module: str) -> bool:
    """Can this module actually be imported, right now, in this process?

    Deliberately a real import rather than ``find_spec``. A spec that
    cannot execute is precisely the case that matters here: on a Mac
    with mlx-lm on disk but a broken dependency chain, ``find_spec``
    says yes and the import then raises — so detection would "verify"
    MLX and hand back a backend whose constructor fails.

    The import is not wasted work: the only reason to ask is that we are
    about to construct this backend, which imports it anyway.
    """
    import importlib
    try:
        importlib.import_module(module)
        return True
    except Exception:
        # Any failure — missing, half-installed, incompatible pair, a
        # poisoned dependency — means "cannot use this backend", which is
        # the only question being asked.
        return False


def _configured_backend() -> str:
    """The lab's configured backend, or "auto" to detect.

    Read lazily rather than captured at import: ``arail.config`` computes
    MODEL_BACKEND from the env at *its* import time, and callers
    (including tests) reload it. Binding the value here would freeze
    whichever env happened to be live first.

    This exists because the fallback used to be the literal ``"mlx"``.
    That skipped ``config.MODEL_BACKEND`` entirely, so whenever
    ``MODEL_BACKEND`` was absent from the environment the router built an
    MLX backend on machines that had no MLX — ignoring the project's own
    default of ``"auto"`` — and raised "MLX not installed" instead of
    detecting what the box could actually run.
    """
    try:
        from arail import config
        return getattr(config, "MODEL_BACKEND", "auto") or "auto"
    except Exception:  # pragma: no cover - config should always import
        return "auto"


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
        name = (backend or os.getenv("MODEL_BACKEND")
                or _configured_backend()).lower()
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
    @classmethod
    def from_backend(cls, backend: BaseBackend, name: str, *,
                     billing_source: str = "agent") -> "ModelRouter":
        """Wrap an already-constructed backend in a router.

        Used by the model registry (arail.registry) so registry-built
        backends keep flowing through cost_tracker like every other call.
        Optional attributes ``provider`` / ``entry_id`` / ``tab`` may be set
        on the returned router by the caller; complete()/stream_complete()
        forward them to cost tracking when present.
        """
        self = cls.__new__(cls)
        self.backend_name = name
        self.billing_source = billing_source
        self._backend = backend
        return self

    # ------------------------------------------------------------------
    @staticmethod
    def _auto_detect() -> str:
        """Best-effort platform detection (mirrors setup.sh logic).

        Detection asks two questions per candidate, not one: is this the
        right *hardware*, and is the runtime for it actually importable.
        Apple Silicon without mlx-lm installed is a real configuration —
        the minimalist tier does not install it — and answering "mlx"
        there produces a hard ImportError from a code path whose whole
        job is to pick something that works.
        """
        import platform
        import shutil

        if platform.system() == "Darwin" and platform.machine() == "arm64":
            if _is_importable("mlx_lm"):
                return "mlx"
            # Apple Silicon, but MLX cannot actually be loaded: Ollama is
            # what setup installs by default and what the rest of the lab
            # assumes.
            return "ollama_native"
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
            provider=getattr(self, "provider", None),
            entry_id=getattr(self, "entry_id", None),
            tab=getattr(self, "tab", None),
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
                    provider=getattr(self, "provider", None),
                    entry_id=getattr(self, "entry_id", None),
                    tab=getattr(self, "tab", None),
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
