from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.agents.nlq_planner import plan_and_fly

router = APIRouter()


class NLQReq(BaseModel):
    utterance: str
    k: int = 25


@router.post("/query")
async def query(req: Request, body: NLQReq):
    store = getattr(req.app.state, "store", None)
    if store is None:
        return {
            "node_ids": [],
            "message": "Knowledge store is initializing; NLQ is temporarily unavailable.",
        }
    return await plan_and_fly(store, body.utterance, body.k)
