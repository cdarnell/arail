"""Librarian API — the DaC tab's agent-focus and term-proposal surface.

Status/pause/resume mirror the AutoResearch control endpoints; the
proposal queue is the human gate of the term-scout loop: the Librarian
files proposals into the per-world sidecar, the operator approves or
rejects here, and approval routes through the exact same machinery the
term editor uses (validate → gate → reseal → swap) so nothing enters
the sealed World any other way.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, Request

from arail import librarian_scout as ls
from arail import world_forge as wf
from arail.activity import activity_log
from arail.portal.world_routes import (
    _csrf_reject,
    _err,
    _load_terms,
    _mounted_catalog_dir,
    _reseal_lock,
    _reseal_and_swap,
    _validate_term_fields,
)

_log = logging.getLogger(__name__)

router = APIRouter()


def _librarian() -> Optional[Any]:
    from arail.agents import loader
    return loader.load_one("librarian")


@router.get("/api/librarian/status")
async def api_librarian_status():
    agent = _librarian()
    if agent is None or not hasattr(agent, "snapshot"):
        return {"status": "unavailable", "world": {"mounted": False},
                "forge": {}, "grow": {}, "scout": {}}
    return agent.snapshot()


@router.post("/api/librarian/pause")
async def api_librarian_pause(request: Request):
    if (rej := _csrf_reject(request)) is not None:
        return rej
    agent = _librarian()
    if agent is None:
        return _err(503, {"error": "librarian_unavailable"})
    agent.pause()
    return {"ok": True, "status": agent.status}


@router.post("/api/librarian/resume")
async def api_librarian_resume(request: Request):
    if (rej := _csrf_reject(request)) is not None:
        return rej
    agent = _librarian()
    if agent is None:
        return _err(503, {"error": "librarian_unavailable"})
    if agent.status == "idle" and hasattr(agent, "start"):
        agent.start()
    else:
        agent.resume()
    return {"ok": True, "status": agent.status}


# ── term proposals (the human gate of the scout loop) ───────────────────

@router.get("/api/librarian/proposals")
async def api_proposals_list():
    bundle_dir = _mounted_catalog_dir()
    if bundle_dir is None:
        return {"world": None, "proposals": [], "last_scan": None}
    doc = ls.load_sidecar(bundle_dir)
    manifest = json.loads((bundle_dir / "manifest.json").read_bytes())
    return {
        "world": manifest.get("world"),
        "display_name": manifest.get("display_name"),
        "tier": manifest.get("provenance_tier"),
        "last_scan": doc.get("last_scan"),
        "proposals": [p for p in doc.get("proposals", [])
                      if p.get("status") == "pending"],
    }


@router.post("/api/librarian/scan")
async def api_scan_now(request: Request):
    """Manual scout trigger — one pass in the background."""
    if (rej := _csrf_reject(request)) is not None:
        return rej
    if _mounted_catalog_dir() is None:
        return _err(409, {"error": "no_world_mounted",
                          "message": "Mount a World before scouting terms."})
    agent = _librarian()
    if agent is not None and hasattr(agent, "scout_once"):
        asyncio.create_task(agent.scout_once())
    else:  # agent unavailable — run the pass directly
        asyncio.create_task(asyncio.to_thread(ls.scout_mounted_world))
    return {"started": True}


def _find_proposal(doc: dict, proposal_id: str) -> Optional[dict]:
    return next((p for p in doc.get("proposals", [])
                 if p.get("id") == proposal_id), None)


@router.post("/api/librarian/proposals/{proposal_id}/approve")
async def api_proposal_approve(proposal_id: str, request: Request):
    """Compile a scouted term into the mounted World — the same gate →
    reseal → swap path the term editor uses. The proposal's source is
    preserved verbatim (the honest provenance the operator just judged)."""
    if (rej := _csrf_reject(request)) is not None:
        return rej
    async with _reseal_lock:
        bundle_dir = _mounted_catalog_dir()
        if bundle_dir is None:
            return _err(409, {"error": "no_world_mounted"})
        doc = ls.load_sidecar(bundle_dir)
        proposal = _find_proposal(doc, proposal_id)
        if proposal is None or proposal.get("status") != "pending":
            return _err(404, {"error": "proposal_not_found", "id": proposal_id})

        spec, terms = _load_terms(bundle_dir)
        known = {t["slug"] for t in terms}
        slug = str(proposal.get("slug", ""))
        if slug in known:
            proposal["status"] = "duplicate"
            ls.save_sidecar(bundle_dir, doc)
            return _err(409, {"error": "term_exists", "slug": slug})
        body = {k: proposal.get(k) for k in
                ("term", "category", "short", "definition", "example", "related")}
        if (bad := _validate_term_fields(body, spec, known, slug)) is not None:
            return bad

        source = str(proposal.get("source", "")).strip()
        terms.append({
            "slug": slug, "term": str(proposal.get("term", ""))[:120],
            "category": str(proposal.get("category", "")),
            "short": str(proposal.get("short", ""))[:wf.MAX_SHORT],
            "definition": str(proposal.get("definition", ""))[:wf.MAX_DEFINITION],
            "example": str(proposal.get("example", ""))[:wf.MAX_EXAMPLE],
            "related": list(proposal.get("related") or []),
            "source": source,
        })
        if (err := await _reseal_and_swap(bundle_dir, terms)) is not None:
            terms.pop()
            return err

        proposal["status"] = "approved"
        ls.save_sidecar(bundle_dir, doc)
        manifest = json.loads((bundle_dir / "manifest.json").read_bytes())
        activity_log.emit(
            "librarian",
            f"'{proposal.get('term')}' compiled into the "
            f"'{manifest.get('display_name')}' World "
            f"({wf.tier_of_source(source)}) — resealed.", "success",
            {"dac_proposals": {"action": "approve", "slug": slug}})
        return {"ok": True, "slug": slug,
                "tier": manifest.get("provenance_tier"),
                "counts": manifest.get("provenance_counts")}


@router.post("/api/librarian/proposals/{proposal_id}/reject")
async def api_proposal_reject(proposal_id: str, request: Request):
    """Dismiss a proposal. Its slug enters the never-re-propose memory."""
    if (rej := _csrf_reject(request)) is not None:
        return rej
    bundle_dir = _mounted_catalog_dir()
    if bundle_dir is None:
        return _err(409, {"error": "no_world_mounted"})
    doc = ls.load_sidecar(bundle_dir)
    proposal = _find_proposal(doc, proposal_id)
    if proposal is None or proposal.get("status") != "pending":
        return _err(404, {"error": "proposal_not_found", "id": proposal_id})
    proposal["status"] = "rejected"
    import time as _time
    doc.setdefault("rejected", {})[str(proposal.get("slug", ""))] = {
        "ts": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
        "by": "operator",
    }
    doc.get("candidates", {}).pop(str(proposal.get("slug", "")), None)
    ls.save_sidecar(bundle_dir, doc)
    activity_log.emit(
        "librarian",
        f"Proposal '{proposal.get('term')}' dismissed — the Librarian "
        "won't re-propose it.", "info",
        {"dac_proposals": {"action": "reject", "slug": proposal.get("slug")}})
    return {"ok": True}
