from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.agents.cluster_synthesizer import synthesize_cluster
from app.agents.link_discoverer import discover_links
from oglab.config import PKB_ROOT
from oglab import wiki

router = APIRouter()


class ClusterReq(BaseModel):
    source_id: str
    hops: int = 2


@router.post("/cluster-summary")
async def cluster_summary(req: Request, body: ClusterReq):
    store = getattr(req.app.state, "store", None)
    if store is None:
        return {"summary": _fallback_cluster_summary(body.source_id)}
    summary = await synthesize_cluster(store, body.source_id, body.hops)
    return {"summary": summary}


@router.post("/discover-links")
async def discover(req: Request, threshold: float = 0.65, max_orphans: int = 20):
    store = getattr(req.app.state, "store", None)
    if store is None:
        return {"suggestions": []}
    suggestions = await discover_links(store, threshold, max_orphans)
    # Broadcast each new suggestion so the canvas shows them live
    broadcaster = getattr(req.app.state, "ws_broadcaster", None)
    for s in suggestions:
        if broadcaster is not None:
            await broadcaster.send({"event": "link_added", "link": s})
    return {"suggestions": suggestions}


def _fallback_cluster_summary(source_id: str) -> str:
    """Return a useful local summary even before GraphStore is ready."""
    try:
        manifest = wiki.load_manifest(PKB_ROOT)
        graph = manifest.get("graph", {})
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
    except Exception:
        return (
            "Knowledge store is warming up. Running in fallback mode using local wiki graph only."
        )

    node_by_id = {n.get("id"): n for n in nodes if n.get("id")}
    node = node_by_id.get(source_id)
    if not node:
        return (
            "Knowledge store is warming up. This node isn't in the fallback wiki graph yet; "
            "try another node or wait for store initialization to finish."
        )

    neighbors = set()
    for e in edges:
        s = e.get("source")
        t = e.get("target")
        if s == source_id and t:
            neighbors.add(t)
        elif t == source_id and s:
            neighbors.add(s)

    grouped: dict[str, int] = {}
    for nid in neighbors:
        group = str(node_by_id.get(nid, {}).get("group") or "notes")
        grouped[group] = grouped.get(group, 0) + 1
    mix = ", ".join(f"{k}:{v}" for k, v in sorted(grouped.items(), key=lambda kv: (-kv[1], kv[0]))[:4])
    if not mix:
        mix = "no linked groups yet"

    title = str(node.get("label") or node.get("id") or "this node")
    return (
        f"Fallback summary for '{title}': {len(neighbors)} linked node(s), mix {mix}. "
        "GraphStore (Neo4j/LanceDB) is still initializing, so this summary uses the local wiki graph snapshot."
    )
