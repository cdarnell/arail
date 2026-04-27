import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import sources, graph, agents, nlq, ws, goals
from app.services.graph_store import GraphStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    store = GraphStore(
        lance_path=os.getenv("LANCE_PATH", "./data/lance"),
        neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        neo4j_auth=(os.getenv("NEO4J_USER", "neo4j"),
                    os.getenv("NEO4J_PASSWORD", "changeme-please")),
    )
    await store.init()
    app.state.store = store
    app.state.ws_broadcaster = ws.broadcaster
    try:
        yield
    finally:
        await store.close()


app = FastAPI(title="Knowledge Canvas", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

app.include_router(sources.router, prefix="/api/sources", tags=["sources"])
app.include_router(graph.router,   prefix="/api/graph",   tags=["graph"])
app.include_router(goals.router,   prefix="/api/goals",   tags=["goals"])
app.include_router(agents.router,  prefix="/api/agents",  tags=["agents"])
app.include_router(nlq.router,     prefix="/api/nlq",     tags=["nlq"])
app.include_router(ws.router)
