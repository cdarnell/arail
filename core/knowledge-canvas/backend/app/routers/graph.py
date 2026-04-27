import importlib.util
import os
from pathlib import Path

from fastapi import APIRouter, Request

from arail.config import PKB_ROOT
from arail import wiki

router = APIRouter()


@router.get("/snapshot")
async def snapshot(req: Request):
    """Full graph for initial load. After this, rely on WS patches."""
    if hasattr(req.app.state, "store"):
        graph = await req.app.state.store.full_graph()
    else:
        graph = _fallback_snapshot()
    return _inject_focus_clusters(graph)


@router.get("/status")
async def status(req: Request):
    """Canvas readiness + dependency status for UI diagnostics."""
    lance_path = os.getenv("LANCE_PATH", "./data/lance")
    store_ready = hasattr(req.app.state, "store")
    return {
        "store_ready": store_ready,
        "mode": "graph-store" if store_ready else "wiki-fallback",
        "lance": {
            "path": lance_path,
            "path_exists": Path(lance_path).exists(),
            "package_installed": importlib.util.find_spec("lancedb") is not None,
        },
        "neo4j": {
            "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            "driver_installed": importlib.util.find_spec("neo4j") is not None,
        },
    }


@router.get("/semantic-edges")
async def semantic_edges(req: Request, k: int = 5, threshold: float = 0.75):
    """Compute semantic-proximity edges for semantic mode."""
    if not hasattr(req.app.state, "store"):
        return {"links": []}
    store = req.app.state.store
    graph = await store.full_graph()
    edges = []
    for n in graph["nodes"]:
        neighbors = await store.semantic_neighbors(n["id"], k=k)
        for nb in neighbors:
            if nb["score"] >= threshold:
                edges.append({
                    "source": n["id"], "target": nb["id"],
                    "kind": "semantic", "weight": round(nb["score"], 3),
                })
    seen = set()
    deduped = []
    for e in edges:
        key = tuple(sorted([e["source"], e["target"]]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)
    return {"links": deduped}


def _fallback_snapshot() -> dict:
    """Build a canvas graph from the existing wiki manifest when the
    full knowledge-canvas store is unavailable.
    """
    manifest = wiki.load_manifest(PKB_ROOT)
    graph = manifest.get("graph", {"nodes": [], "edges": []})

    nodes = []
    for node in graph.get("nodes", []):
        group = node.get("group") or "notes"
        kind = {
            "sources": "web_page",
            "agents": "experiment_log",
            "notes": "markdown",
            "compiled": "dataset",
            "inference": "api_snapshot",
            "docs": "paper",
        }.get(group, "markdown")
        nodes.append({
            "id": node.get("id"),
            "title": node.get("label") or node.get("id"),
            "kind": kind,
            "tags": node.get("tags", []),
            "domain": group,
            "ingested_by": "agent" if group in {"agents", "compiled"} else "user",
            "year": None,
            "orphan": False,
        })

    links = []
    for edge in graph.get("edges", []):
        links.append({
            "source": edge.get("source"),
            "target": edge.get("target"),
            "kind": "wikilink",
            "confidence": 1.0,
        })

    return {"nodes": nodes, "links": links}


def _inject_focus_clusters(graph: dict) -> dict:
    """Add lab-centric focus hubs to shape default graph exploration.

    Hubs (lab-dimension orientation, orthogonal to user goals):
      - health: agent/lab maintenance signals
      - performance: speed/throughput/latency experimentation
      - cleanliness: notes/tasks/housekeeping references

    The active user goal is no longer injected as an ephemeral focus_goal
    node — Goal/SubObjective nodes now live in Neo4j as first-class
    citizens (see services/goal_graph.py + GraphStore.upsert_goal). The
    snapshot returns them via full_graph().
    """
    nodes = list(graph.get("nodes", []))
    links = list(graph.get("links", []))

    by_id = {n.get("id"): n for n in nodes}

    focus_nodes = [
        {
            "id": "focus_health",
            "title": "Lab Health",
            "kind": "focus",
            "tags": ["health", "agents", "ops"],
            "domain": "lab",
            "ingested_by": "agent",
            "orphan": False,
        },
        {
            "id": "focus_performance",
            "title": "Performance",
            "kind": "focus",
            "tags": ["performance", "inference", "speed"],
            "domain": "lab",
            "ingested_by": "agent",
            "orphan": False,
        },
        {
            "id": "focus_clean",
            "title": "Cleanliness",
            "kind": "focus",
            "tags": ["clean", "hygiene", "maintenance"],
            "domain": "lab",
            "ingested_by": "agent",
            "orphan": False,
        },
    ]

    for fn in focus_nodes:
        if fn["id"] not in by_id:
            nodes.append(fn)
            by_id[fn["id"]] = fn

    def _lc_values(n: dict) -> str:
        values = [
            str(n.get("title") or ""),
            str(n.get("kind") or ""),
            str(n.get("domain") or ""),
            " ".join(n.get("tags") or []),
            str(n.get("ingested_by") or ""),
        ]
        return " ".join(values).lower()

    def _link(src: str, dst: str, confidence: float = 0.75):
        links.append({
            "source": src,
            "target": dst,
            "kind": "focus",
            "confidence": round(confidence, 3),
        })

    perf_terms = {
        "perf", "performance", "latency", "throughput", "benchmark", "token/s",
        "inference", "stream", "streaming", "parallel", "batch", "gpu", "mlx", "aerollm",
        "experiment", "hypothesis",
    }
    health_terms = {"health", "agent", "scheduler", "runtime", "error", "status", "ops"}
    clean_terms = {"clean", "cleanup", "todo", "debt", "hygiene", "lint", "refactor"}

    for n in nodes:
        nid = n.get("id")
        if not nid or str(nid).startswith("focus_"):
            continue
        # Goal / SubObjective nodes are not lab-dimension citizens; skip.
        if n.get("node_type") in {"Goal", "SubObjective"}:
            continue
        blob = _lc_values(n)
        if any(t in blob for t in perf_terms) or n.get("kind") == "experiment_log":
            _link("focus_performance", nid, 0.74)
        if any(t in blob for t in health_terms) or n.get("ingested_by") in {"agent", "curator"}:
            _link("focus_health", nid, 0.6)
        if any(t in blob for t in clean_terms) or n.get("kind") in {"markdown", "dataset"}:
            _link("focus_clean", nid, 0.52)

    # De-duplicate by undirected pair + kind.
    seen = set()
    deduped = []
    for e in links:
        a, b = sorted([e.get("source"), e.get("target")])
        key = (a, b, e.get("kind"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(e)

    return {"nodes": nodes, "links": deduped}
