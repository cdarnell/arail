"""Model Building tab API — thin portal layer over arail.build.*"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

log = logging.getLogger(__name__)

build_router = APIRouter(prefix="/api/build", tags=["build"])

BUILD_MODES = ("local", "anthropix", "hybrid", "dry_run")


def _client():
    from arail.build.nucleus_client import NucleusClient
    return NucleusClient()


def _anthropix_gate() -> Dict[str, Any]:
    """Is the Anthropix-gateway (accelerated) option available right now?"""
    from arail.airgap import is_airgapped
    airgapped = is_airgapped()
    has_key = bool(os.getenv("ANTHROPIC_API_KEY", "").strip())
    ok = (not airgapped) and has_key
    if airgapped:
        reason = ("Locked — lab is airgapped. Flip the Airgapped pill "
                  "(LAB_MODE=hybrid) and set ANTHROPIC_API_KEY to enable.")
    elif not has_key:
        reason = "Locked — ANTHROPIC_API_KEY is not set (Manage Providers)."
    else:
        reason = ""
    return {"available": ok, "reason": reason,
            "airgapped": airgapped, "has_key": has_key}


class PreflightRequest(BaseModel):
    spec: Dict[str, Any]


@build_router.post("/preflight")
async def build_preflight(req: PreflightRequest) -> Dict[str, Any]:
    """Estimate resources/time for a build spec. Works with nucleus offline."""
    from arail.build.preflight import PreflightSpec, estimate
    try:
        spec = PreflightSpec.from_dict(req.spec)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"bad spec: {exc}")
    report = estimate(spec)
    return {"report": report.to_dict(), "gate": _anthropix_gate(),
            "modes": _mode_cards(report)}


def _mode_cards(report) -> List[Dict[str, Any]]:
    gate = _anthropix_gate()
    local_h = report.est_wall_clock_hours.get("local", 0.0)
    remote_h = report.est_wall_clock_hours.get("remote", 0.0)
    return [
        {"mode": "local", "label": "Local build",
         "detail": "Full control, no egress, slowest.",
         "est_hours": local_h, "est_cost_usd": 0.0, "available": True,
         "recommended": local_h <= 8.0},
        {"mode": "anthropix", "label": "Anthropix gateway (accelerated)",
         "detail": "Teacher tier served through the Anthropic API — "
                   "recommended for long builds.",
         "est_hours": remote_h,
         "est_cost_usd": report.est_anthropic_cost_usd,
         "available": gate["available"], "reason": gate["reason"],
         "recommended": gate["available"] and local_h > 8.0},
        {"mode": "hybrid", "label": "Hybrid",
         "detail": "Local data prep + tokenization + bulk teacher; remote "
                   "(Anthropic) escalation on failure hotspots.",
         "est_hours": round((local_h + remote_h) / 2, 2),
         "est_cost_usd": round(report.est_anthropic_cost_usd * 0.3, 2),
         "available": gate["available"], "reason": gate["reason"],
         "recommended": False},
        {"mode": "dry_run", "label": "Dry run",
         "detail": "Validate config + dataset, produce the time/resource "
                   "estimate only. No training; results badged SIMULATED.",
         "est_hours": 0.1, "est_cost_usd": 0.0, "available": True,
         "recommended": False},
    ]


@build_router.get("/health")
async def build_health() -> Dict[str, Any]:
    import anyio
    from dataclasses import asdict
    h = await anyio.to_thread.run_sync(lambda: _client().health())
    return {**asdict(h), "gate": _anthropix_gate()}


class StartRequest(BaseModel):
    run_id: str
    mode: str                      # local | anthropix | hybrid | dry_run
    spec: Dict[str, Any]
    domain: str = "ai-model-engineer"
    subdomains: List[str] = []
    student_model: str = "mlx-community/Qwen2.5-3B-Instruct-4bit"
    override_red: bool = False


@build_router.post("/start")
async def build_start(req: StartRequest) -> Dict[str, Any]:
    import anyio
    from arail.activity import activity_log
    from arail.build.jobs import BuildJobStore
    from arail.build.manifest import build_manifest, validate_run_id, write_manifest
    from arail.build.preflight import PreflightSpec, estimate

    if req.mode not in BUILD_MODES:
        raise HTTPException(status_code=400,
                            detail=f"mode must be one of {BUILD_MODES}")
    try:
        validate_run_id(req.run_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # Anthropic-backed modes are hard-gated (visible reason, never a 500).
    if req.mode in ("anthropix", "hybrid"):
        gate = _anthropix_gate()
        if not gate["available"]:
            raise HTTPException(status_code=409, detail=gate["reason"])

    # Preflight gate: red requires an explicit, recorded override.
    try:
        spec = PreflightSpec.from_dict(req.spec)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"bad spec: {exc}")
    report = estimate(spec)
    if report.has_red and not req.override_red:
        raise HTTPException(
            status_code=409,
            detail={"error": "preflight_red",
                    "message": "Preflight has RED requirements — the run is "
                               "blocked. Pass override_red=true to start "
                               "anyway (recorded).",
                    "report": report.to_dict()})

    dry = req.mode == "dry_run"
    manifest = build_manifest(
        run_id=req.run_id, mode=("local" if dry else req.mode),
        spec=req.spec, domain=req.domain, subdomains=req.subdomains,
        student_model=req.student_model)
    try:
        _abs, rel_path = write_manifest(req.run_id, manifest)
    except OSError as exc:
        raise HTTPException(status_code=502,
                            detail=f"cannot write manifest into the nucleus "
                                   f"configs tree: {exc}")

    try:
        result = await anyio.to_thread.run_sync(
            lambda: _client().start(req.run_id, rel_path, dry_run=dry))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"nucleus orchestrator rejected the run: {exc}")

    job = BuildJobStore().create(
        req.run_id, mode=req.mode, manifest_path=rel_path,
        preflight=report.to_dict(), override_red=req.override_red
        and report.has_red, dry_run=dry)
    activity_log.emit(
        "build",
        f"Nucleus build '{req.run_id}' started ({req.mode}"
        f"{', RED override recorded' if job['override_red'] else ''}"
        f"{', SIMULATED' if dry else ''}).",
        "warn" if job["override_red"] else "success",
        {"build": {"run_id": req.run_id, "mode": req.mode, "dry_run": dry}})
    return {"job": job, "nucleus": result}


@build_router.get("/jobs")
async def build_jobs() -> Dict[str, Any]:
    """Local ledger merged with live nucleus status + trainer telemetry."""
    import anyio
    from arail.build.jobs import BuildJobStore

    store = BuildJobStore()
    jobs = store.list()

    def _live() -> Dict[str, Any]:
        client = _client()
        h = client.health()
        out: Dict[str, Any] = {"health": h.__dict__, "statuses": {},
                               "trainer": None}
        if not h.up:
            return out
        out["trainer"] = client.trainer_progress()
        for job in jobs[:10]:
            if job.get("phase") in ("completed", "failed", "aborted", "lost"):
                continue
            try:
                out["statuses"][job["run_id"]] = client.status(job["run_id"])
            except Exception as exc:  # noqa: BLE001
                out["statuses"][job["run_id"]] = {"error": str(exc)[:120]}
        return out

    live = await anyio.to_thread.run_sync(_live)
    for job in jobs:
        st = live["statuses"].get(job["run_id"])
        if isinstance(st, dict) and st.get("status"):
            if (st.get("status") == "not_found"
                    and live["health"].get("up")
                    and job.get("phase") not in ("completed", "failed",
                                                 "aborted", "lost")):
                # Nucleus is up but forgot the run (restarted) — never
                # freeze at the stale phase; say what happened.
                store.update(job["run_id"], phase="lost",
                             lost_reason="nucleus no longer knows this run "
                                         "(restarted?)")
                job["phase"] = "lost"
                job["lost_reason"] = "nucleus no longer knows this run (restarted?)"
                continue
            job["last_nucleus_status"] = st
            phase = st.get("current_phase") or st.get("status")
            if phase and phase != job.get("phase"):
                store.update(job["run_id"], phase=phase,
                             last_nucleus_status=st)
                job["phase"] = phase
    return {"jobs": jobs, "nucleus": live["health"],
            "trainer": live["trainer"], "statuses": live["statuses"]}


@build_router.post("/{run_id}/{action}")
async def build_action(run_id: str, action: str) -> Dict[str, Any]:
    import anyio
    from arail.activity import activity_log
    if action not in ("pause", "resume", "stop", "abort"):
        raise HTTPException(status_code=400, detail="unknown action")
    client = _client()
    fn = {"pause": lambda: client.pause(),
          "resume": lambda: client.resume(),
          "stop": lambda: client.stop(run_id),
          "abort": lambda: client.abort(run_id)}[action]
    try:
        result = await anyio.to_thread.run_sync(fn)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)[:200])
    activity_log.emit("build", f"Build '{run_id}': {action}.", "info",
                      {"build": {"run_id": run_id, "action": action}})
    return {"ok": True, "result": result}


@build_router.get("/{run_id}/detail")
async def build_detail(run_id: str) -> Dict[str, Any]:
    import anyio
    from arail.build.jobs import BuildJobStore

    def _fetch() -> Dict[str, Any]:
        client = _client()
        out: Dict[str, Any] = {}
        for key, fn in (("status", lambda: client.status(run_id)),
                        ("events", lambda: client.events(run_id)),
                        ("graduation", lambda: client.graduation(run_id)),
                        ("seal", lambda: client.seal(run_id))):
            try:
                out[key] = fn()
            except Exception as exc:  # noqa: BLE001
                out[key] = {"error": str(exc)[:120]}
        return out

    detail = await anyio.to_thread.run_sync(_fetch)
    detail["job"] = BuildJobStore().get(run_id)
    return detail
