from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel

from app.models.source import IngestRequest, QueryRequest, Source
from app.services.adapters import adapt

router = APIRouter()


class LinkRequest(BaseModel):
    src_id: str
    dst_id: str
    rel: str = "LINKS_TO"
    props: dict = {}


@router.post("/ingest", response_model=Source)
async def ingest(req: Request, payload: IngestRequest):
    store = getattr(req.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Knowledge store is initializing")
    source = adapt(payload)
    stored = await store.upsert(source)
    broadcaster = getattr(req.app.state, "ws_broadcaster", None)
    if broadcaster is not None:
        await broadcaster.send({
        "event": "source_added",
        "source": stored.model_dump(mode="json"),
        })
    return stored


@router.post("/query")
async def query(req: Request, payload: QueryRequest):
    store = getattr(req.app.state, "store", None)
    if store is None:
        return {"results": []}
    results = await store.query(
        semantic=payload.semantic,
        must_tags=payload.must_tags,
        must_not_tags=payload.must_not_tags,
        kinds=payload.kinds,
        domain=payload.domain,
        year_from=payload.year_from,
        year_to=payload.year_to,
        k=payload.k,
    )
    return {"results": results}


@router.post("/link")
async def link(req: Request, payload: LinkRequest):
    store = getattr(req.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Knowledge store is initializing")
    valid_rels = {"LINKS_TO", "DISCOVERED_FROM", "MOTIVATES", "CITES", "DERIVED_FROM", "SUGGESTED"}
    if payload.rel not in valid_rels:
        raise HTTPException(400, f"rel must be one of {valid_rels}")
    await store.link(payload.src_id, payload.dst_id, payload.rel, payload.props)
    broadcaster = getattr(req.app.state, "ws_broadcaster", None)
    if broadcaster is not None:
        await broadcaster.send({
        "event": "link_added",
        "link": {"source": payload.src_id, "target": payload.dst_id,
                 "rel": payload.rel, "kind": payload.rel.lower()},
        })
    return {"ok": True}


@router.delete("/{source_id}")
async def remove(req: Request, source_id: str):
    store = getattr(req.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Knowledge store is initializing")
    await store.remove(source_id)
    broadcaster = getattr(req.app.state, "ws_broadcaster", None)
    if broadcaster is not None:
        await broadcaster.send({
        "event": "source_removed", "id": source_id,
        })
    return {"ok": True}


@router.get("/{source_id}")
async def get(req: Request, source_id: str):
    store = getattr(req.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Knowledge store is initializing")
    s = await store.get(source_id)
    if not s:
        raise HTTPException(404, "Not found")
    return s
