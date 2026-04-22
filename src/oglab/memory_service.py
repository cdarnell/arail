"""Core memory service for OGLab.

LanceDB is the default production accelerator for workflow recall, but
every workflow snapshot is also persisted to JSON on disk for backup and
disaster recovery.
"""

from __future__ import annotations

from fastapi import FastAPI

from oglab.agent_workflows import get_agent_workflow, list_agent_workflows, workflow_health

app = FastAPI(title="OGLab Memory Service", docs_url=None, redoc_url=None)


@app.get("/health")
async def health() -> dict[str, object]:
    info = workflow_health()
    return {
        "service": "oglab-memory",
        "status": "ok",
        **info,
    }


@app.get("/workflows")
async def workflows() -> dict[str, object]:
    return {"workflows": list_agent_workflows()}


@app.get("/workflows/{agent_id}")
async def workflow(agent_id: str) -> dict[str, object]:
    row = get_agent_workflow(agent_id)
    return {"workflow": row}