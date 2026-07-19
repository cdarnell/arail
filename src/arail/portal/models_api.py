"""Model registry API — the portal surface of ``arail.registry``.

Kept out of portal/app.py (the monolith) per the wiki/world/librarian
pattern: app.py only does ``app.include_router(models_router)``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

models_router = APIRouter(prefix="/api/models", tags=["models"])


def _registry():
    from arail.registry import get_registry
    return get_registry()


@models_router.get("/state")
async def models_state() -> Dict[str, Any]:
    """Everything the statusbar/switcher/banner/chips need, in one call."""
    return _registry().to_state()


class BindRequest(BaseModel):
    profile: str                  # task profile or "*" (with tab)
    entry_id: Optional[str] = None  # None clears the binding/override
    tab: Optional[str] = None


@models_router.post("/bind")
async def models_bind(req: BindRequest) -> Dict[str, Any]:
    try:
        _registry().bind(req.profile, req.entry_id, tab=req.tab)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    from arail.activity import activity_log
    scope = f"{req.tab} tab" if req.tab else "lab-wide"
    activity_log.emit(
        "registry",
        f"Model binding changed ({scope}): {req.profile} → "
        f"{req.entry_id or 'default'}", "info",
        {"model_event": {"kind": "bind", "profile": req.profile,
                         "entry_id": req.entry_id, "tab": req.tab}})
    return _registry().to_state()


@models_router.post("/health/refresh")
async def models_health_refresh() -> Dict[str, Any]:
    """Force a re-probe of every entry (runs off-loop; probes are 2s-capped)."""
    import anyio
    reg = _registry()
    reg._ensure_loaded()
    from arail.registry import health
    await anyio.to_thread.run_sync(
        lambda: health.run_preflight(reg, announce=False))
    return reg.to_state()


@models_router.get("/resolve")
async def models_resolve(profile: str, tab: Optional[str] = None) -> Dict[str, Any]:
    """Dry-run resolution — what would this profile/tab get right now?"""
    from dataclasses import asdict
    try:
        res = _registry().resolve(profile, tab)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "profile": res.profile,
        "tab": res.tab,
        "entry": res.entry.to_public() if res.entry else None,
        "requested": res.requested.to_public() if res.requested else None,
        "fallback": asdict(res.fallback) if res.fallback else None,
        "config_version": res.config_version,
    }


class RegisterArtifactRequest(BaseModel):
    run_id: str
    name: Optional[str] = None       # entry id / ollama model name override
    gguf_path: Optional[str] = None  # explicit path when known client-side


@models_router.post("/register-artifact")
async def models_register_artifact(req: RegisterArtifactRequest) -> Dict[str, Any]:
    """Register a nucleus-graduated model into the registry.

    The entry lands as ``not_installed`` with an install hint; the interval
    health probe flips it healthy once the model appears in Ollama, at which
    point it is selectable in the switcher for every tab.
    """
    from arail.registry.core import ModelEntry
    import os

    grad: Dict[str, Any] = {}
    gguf = req.gguf_path
    if gguf is None:
        try:
            from arail.build.nucleus_client import NucleusClient
            grad = NucleusClient().graduation(req.run_id) or {}
            gguf = grad.get("gguf_path") or grad.get("model_path")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=502,
                detail=f"could not fetch graduation info for run "
                       f"'{req.run_id}': {exc}")
    name = (req.name or grad.get("skill_id")
            or f"nucleus-{req.run_id}").lower().replace("_", "-")

    entry = ModelEntry(
        id=name,
        display_name=name,
        provider_type="local",
        backend="ollama_native",
        endpoint=f"http://127.0.0.1:{os.getenv('OLLAMA_PORT', '11434')}/v1",
        model_id=name,
        tags=["fast"],
        source="artifact",
        artifact={"run_id": req.run_id, "gguf": gguf,
                  "graduated": grad or None},
        note="Graduated from Nucleus. Install with the generated Modelfile "
             "(ollama create) — health flips automatically once present.",
    )
    reg = _registry()
    reg.add_entry(entry)
    from arail.activity import activity_log
    activity_log.emit(
        "registry",
        f"Registered graduated model '{name}' (run {req.run_id}) — "
        "install it in Ollama to activate.", "success",
        {"model_event": {"kind": "artifact_registered", "entry_id": name}})
    install_hint = (
        f"# Install the graduated model into Ollama:\n"
        f"cat > /tmp/Modelfile.{name} <<EOF\nFROM {gguf or '<path-to-gguf>'}\nEOF\n"
        f"ollama create {name} -f /tmp/Modelfile.{name}")
    return {"entry": entry.to_public(), "install_hint": install_hint,
            "state": reg.to_state()}
