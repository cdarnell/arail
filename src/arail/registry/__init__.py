"""Unified model registry — the single model-resolution layer for every tab.

Every tab resolves its model through ``resolve(task_profile, tab=...)``;
no tab talks to an inference endpoint directly. Providers (local resident
model, in-process aeroLLM, OpenAI-compatible gateways, Anthropic, xAI) are
declared as ``ModelEntry`` records, health-checked on startup and on an
interval, and any fallback is a *visible* ``FallbackEvent`` on the activity
stream — never a silent skip.

Import is side-effect free: the registry file is loaded/seeded lazily on the
first ``get_registry()`` call (the researcher/agent singletons import at app
import time, before test conftests could redirect paths).
"""

from arail.registry.core import (  # noqa: F401
    TASK_PROFILES,
    FallbackEvent,
    HealthState,
    ModelCapabilities,
    ModelEntry,
    ModelRegistry,
    Resolution,
    get_registry,
    resolve,
)
