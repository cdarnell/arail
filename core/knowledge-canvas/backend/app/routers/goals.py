"""
Goal-aware endpoints. Bridge between ARAIL's GoalStore and the graph.

Phase 1 surface:
  POST /api/goals/upsert            — persist Goal + SubObjective nodes
  POST /api/goals/{goal_id}/archive — flip status to archived
  POST /api/goals/link-source       — Goal -[:MOTIVATES]-> Source (+ optional ADDRESSES)
  GET  /api/goals/{goal_id}/coverage
  GET  /api/goals/{goal_id}/sources
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.services.goal_graph import GoalGraphService

router = APIRouter()


class GoalUpsertRequest(BaseModel):
    record: dict[str, Any]
    archive_others: bool = True


class LinkSourceToGoalRequest(BaseModel):
    source_id: str
    goal_id: str
    sub_objective_id: str | None = None
    relevance: float | None = None


def _service(req: Request) -> GoalGraphService:
    store = getattr(req.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Knowledge store is initializing")
    return GoalGraphService(store)


@router.post("/upsert")
async def upsert_goal(req: Request, payload: GoalUpsertRequest):
    svc = _service(req)
    result = await svc.upsert_goal(payload.record, archive_others=payload.archive_others)
    return {"ok": True, "goal": result}


@router.post("/{goal_id}/archive")
async def archive_goal(req: Request, goal_id: str):
    svc = _service(req)
    await svc.archive_goal(goal_id)
    return {"ok": True}


@router.post("/link-source")
async def link_source_to_goal(req: Request, payload: LinkSourceToGoalRequest):
    svc = _service(req)
    await svc.link_source_to_goal(
        payload.source_id,
        payload.goal_id,
        sub_objective_id=payload.sub_objective_id,
        relevance=payload.relevance,
    )
    return {"ok": True}


@router.get("/{goal_id}/coverage")
async def coverage(req: Request, goal_id: str):
    svc = _service(req)
    return await svc.coverage(goal_id)


@router.get("/{goal_id}/sources")
async def sources(req: Request, goal_id: str):
    svc = _service(req)
    return {"sources": await svc.sources_for_goal(goal_id)}
