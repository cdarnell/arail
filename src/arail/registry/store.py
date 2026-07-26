"""Registry persistence + env-seed migration.

File: ``lab/data/model_registry.json`` (override: ``ARAIL_MODEL_REGISTRY_FILE``
— same test-isolation convention as ARAIL_ENV_FILE / ARAIL_SECRETS_FILE).
Secrets are NEVER stored here: entries carry ``key_env`` names only; the keys
themselves stay in lab/data/secrets.env via the existing providers flow.

``health`` is runtime state and is not persisted.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional

from arail.registry.core import (TASK_PROFILES, HealthState, ModelCapabilities,
                                 ModelEntry, ModelRegistry)

SCHEMA_VERSION = 1


def registry_file() -> Path:
    override = os.getenv("ARAIL_MODEL_REGISTRY_FILE", "").strip()
    if override:
        return Path(override)
    try:
        from arail.config import DATA_DIR
        return Path(DATA_DIR) / "model_registry.json"
    except Exception:  # noqa: BLE001
        return Path("lab/data/model_registry.json")


# ── (de)serialization ──────────────────────────────────────────────

def _entry_to_dict(e: ModelEntry) -> Dict[str, Any]:
    from dataclasses import asdict
    d = asdict(e)
    d.pop("health", None)   # runtime-only
    return d


def _entry_from_dict(d: Dict[str, Any]) -> Optional[ModelEntry]:
    try:
        caps = d.get("capabilities") or {}
        return ModelEntry(
            id=str(d["id"]),
            display_name=str(d.get("display_name") or d["id"]),
            provider_type=str(d.get("provider_type") or "local"),
            backend=str(d.get("backend") or "openai_compat"),
            endpoint=d.get("endpoint"),
            model_id=str(d.get("model_id") or "default"),
            context_window=d.get("context_window"),
            params_b=d.get("params_b"),
            architecture=str(d.get("architecture") or "dense"),
            moe=d.get("moe"),
            capabilities=ModelCapabilities(
                tools=bool(caps.get("tools", False)),
                json_mode=bool(caps.get("json_mode", False)),
                streaming=bool(caps.get("streaming", True)),
                vision=bool(caps.get("vision", False)),
            ),
            cost_tier=str(d.get("cost_tier") or "free_local"),
            tier=d.get("tier"),
            tags=list(d.get("tags") or []),
            enabled=bool(d.get("enabled", True)),
            source=str(d.get("source") or "user"),
            artifact=d.get("artifact"),
            key_env=d.get("key_env"),
            note=str(d.get("note") or ""),
            health=HealthState(),
        )
    except Exception:  # noqa: BLE001  # tolerate malformed rows
        return None


def save(reg: ModelRegistry) -> None:
    path = registry_file()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "config_version": reg.config_version,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "entries": [_entry_to_dict(e) for e in reg.entries.values()],
        "bindings": dict(reg.bindings),
        "tab_overrides": {t: dict(o) for t, o in reg.tab_overrides.items()},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent),
                                   prefix=".model_registry.", suffix=".tmp")
        with os.fdopen(fd, "w") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp, path)
    except OSError:
        pass  # registry stays usable in memory; persistence is best-effort


def load_or_seed(reg: ModelRegistry) -> None:
    """Populate *reg* from disk, seeding from env when the file is absent.

    Env drift reconciliation: the tier-0/tier-1 seeded entries follow the env
    (MODEL_NAME / AEROLLM_MODEL) — if env no longer matches the stored entry,
    the entry is updated in place (env stays a valid way to configure the lab).
    """
    path = registry_file()
    data: Dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text())
        except Exception:  # noqa: BLE001
            data = {}

    for d in data.get("entries", []):
        entry = _entry_from_dict(d)
        if entry is not None:
            reg.entries[entry.id] = entry

    for profile in TASK_PROFILES:
        reg.bindings[profile] = (data.get("bindings") or {}).get(profile)
    for tab_name, overrides in (data.get("tab_overrides") or {}).items():
        if isinstance(overrides, dict):
            reg.tab_overrides[tab_name] = {
                k: v for k, v in overrides.items() if isinstance(v, str)}
    reg.config_version = int(data.get("config_version") or 0)

    changed = _seed_from_env(reg)
    if changed or not path.exists():
        reg.config_version += 1
        save(reg)


# ── env seeding ────────────────────────────────────────────────────

TIER0_ID = _TIER0_ID = "tier0-local"
TIER1_ID = _TIER1_ID = "tier1-aerollm"
QKZ_2B_ID = "qkz-project-aware-2b"


def _specs_for(model_id: str) -> tuple[Optional[int], Optional[float]]:
    ctx: Optional[int] = None
    params: Optional[float] = None
    try:
        from arail.model_specs import context_label, context_tokens, get_total_params
        label = context_label(model_id)
        if label is not None:
            ctx = context_tokens(label)
        params = get_total_params(model_id)
    except Exception:  # noqa: BLE001
        pass
    return ctx, params


def _short_name(model_id: str) -> str:
    name = model_id.split("/")[-1]
    return name.split(":", 1)[0] if ":" in name else name


def _seed_from_env(reg: ModelRegistry) -> bool:
    changed = False

    # ── Tier 0 — the resident fast model ───────────────────────────
    backend = (os.getenv("MODEL_BACKEND") or "mlx").lower()
    model_name = os.getenv("MODEL_NAME", "default")
    if backend in ("ollama_native", "openai_compat"):
        endpoint = os.getenv("MODEL_API_BASE") or (
            f"http://127.0.0.1:{os.getenv('OLLAMA_PORT', '11434')}/v1"
            if backend == "ollama_native" else "http://localhost:1234/v1")
        t0_backend = backend
    else:
        # mlx/cpu/cuda env setups still get a tier-0 row fronting the local
        # runtime; endpoint None means "in-process/managed by MODEL_BACKEND".
        endpoint = None
        t0_backend = backend
    ctx, params = _specs_for(model_name)
    existing = reg.entries.get(_TIER0_ID)
    if (existing is None or existing.model_id != model_name
            or existing.backend != t0_backend
            or existing.endpoint != endpoint):
        reg.entries[_TIER0_ID] = ModelEntry(
            id=_TIER0_ID,
            display_name=_short_name(model_name),
            provider_type="local",
            backend=t0_backend,
            endpoint=endpoint,
            model_id=model_name,
            context_window=ctx,
            params_b=params,
            tier=0,
            tags=["fast", "tool_use"],
            source="seed_env",
            note="Tier 0 resident — routing, classification, summarization, "
                 "instant UI responses.",
        )
        changed = True

    # ── Tier 1 — aeroLLM deep reasoning ────────────────────────────
    aero_model = os.getenv("AEROLLM_MODEL", "Qwen2.5-7B-Instruct-4bit")
    aero_enabled = os.getenv("AEROLLM_RESEARCH", "true").lower() not in (
        "0", "false", "no")
    is_moe = "moe" in aero_model.lower()
    ctx1, params1 = _specs_for(aero_model)
    existing = reg.entries.get(_TIER1_ID)
    if (existing is None or existing.model_id != aero_model
            or existing.enabled != aero_enabled):
        reg.entries[_TIER1_ID] = ModelEntry(
            id=_TIER1_ID,
            display_name=_short_name(aero_model),
            provider_type="aerollm",
            backend="aerollm",
            endpoint=None,   # in-process PyO3 runtime (no HTTP server)
            model_id=aero_model,
            context_window=ctx1,
            params_b=params1,
            architecture="moe" if is_moe else "dense",
            moe=None,
            tier=1,
            tags=["reasoning", "build", "long_context"],
            enabled=aero_enabled,
            source="seed_env",
            note="Tier 1 deep reasoning via aeroLLM (in-process, MoE-preferred). "
                 "Kept resident by deep_policy once first warmed.",
        )
        changed = True

    # ── Builtins (only added when absent — user edits survive) ─────
    if QKZ_2B_ID not in reg.entries:
        reg.entries[QKZ_2B_ID] = ModelEntry(
            id=QKZ_2B_ID,
            display_name="qkz-project-aware-2b",
            provider_type="local",
            backend="ollama_native",
            endpoint=f"http://127.0.0.1:{os.getenv('OLLAMA_PORT', '11434')}/v1",
            model_id="qkz-project-aware-2b",
            params_b=2.5,
            tier=None,   # becomes the preferred Tier 0 once fused + installed
            tags=["fast"],
            enabled=True,
            source="builtin",
            note="Preferred Tier 0 upgrade — the graduated QuKaiZen Gemma-2B "
                 "fine-tune. Adapters-only today: fuse the LoRA and register "
                 "it via the Model Building tab to activate.",
        )
        changed = True
    if "cloud-anthropic" not in reg.entries:
        reg.entries["cloud-anthropic"] = ModelEntry(
            id="cloud-anthropic",
            display_name="Claude (Anthropic)",
            provider_type="anthropic",
            backend="claude",
            endpoint="https://api.anthropic.com/v1",
            model_id=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
            context_window=200_000,
            capabilities=ModelCapabilities(tools=True, json_mode=True,
                                           streaming=True, vision=True),
            cost_tier="metered",
            tags=["reasoning", "long_context", "tool_use"],
            source="builtin",
            key_env="ANTHROPIC_API_KEY",
        )
        changed = True
    if "cloud-xai" not in reg.entries:
        reg.entries["cloud-xai"] = ModelEntry(
            id="cloud-xai",
            display_name="Grok (xAI)",
            provider_type="xai",
            backend="openai_compat",
            endpoint="https://api.x.ai/v1",
            model_id=os.getenv("XAI_MODEL", "grok-4"),
            context_window=256_000,
            capabilities=ModelCapabilities(tools=True, json_mode=True,
                                           streaming=True),
            cost_tier="metered",
            tags=["reasoning", "long_context"],
            source="builtin",
            key_env="XAI_API_KEY",
        )
        changed = True
    if "gateway-custom" not in reg.entries:
        base = os.getenv("MODEL_API_BASE", "")
        reg.entries["gateway-custom"] = ModelEntry(
            id="gateway-custom",
            display_name="Custom gateway",
            provider_type="gateway",
            backend="openai_compat",
            endpoint=base or None,
            model_id=os.getenv("MODEL_NAME", "default"),
            cost_tier="metered",
            enabled=bool(base),
            source="builtin",
            key_env="MODEL_API_KEY",
            note="Any OpenAI-compatible endpoint. Configure via the "
                 "providers UI or MODEL_API_BASE / MODEL_API_KEY.",
        )
        changed = True

    # ── Default bindings (fill only unset profiles) ────────────────
    defaults = {"fast": _TIER0_ID, "reasoning": _TIER1_ID, "build": _TIER1_ID}
    for profile, eid in defaults.items():
        if reg.bindings.get(profile) is None and eid in reg.entries:
            reg.bindings[profile] = eid
            changed = True

    return changed
