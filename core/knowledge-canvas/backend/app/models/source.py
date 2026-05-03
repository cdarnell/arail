"""
Source / IngestRequest / QueryRequest models for the Knowledge Canvas
backend. The original `app/models/` package was never committed alongside
the rest of `core/knowledge-canvas/backend` (commit 9683681), which left
every router that imported from here failing at import time and the
canvas iframe stuck on "Loading canvas…".

Field shapes here are recovered from how the rest of the canvas backend
uses them: `services/graph_store.py`, `services/adapters.py`, and
`routers/sources.py` are the witnesses. Notably:
  - graph_store reads `source.created_at.isoformat()` → datetime
  - graph_store reads `source.triage_state` → str (default "manual")
  - adapters constructs Source(...) with these exact kwargs
  - routers/sources passes IngestRequest fields straight to adapt()
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


SourceKind = Literal[
    "markdown",
    "api_snapshot",
    "paper",
    "web_page",
    "dataset",
    "experiment_log",
    "image",
    "focus",
]


class Source(BaseModel):
    id: str
    kind: SourceKind
    title: str
    uri: str
    body_excerpt: str = ""
    tags: list[str] = Field(default_factory=list)
    year: int | None = None
    author: str | None = None
    domain: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    ingested_by: str = "user"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    triage_state: str = "manual"


class IngestRequest(BaseModel):
    kind: SourceKind
    title: str
    uri: str
    body_excerpt: str = ""
    tags: list[str] = Field(default_factory=list)
    year: int | None = None
    author: str | None = None
    domain: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    ingested_by: str = "user"


class QueryRequest(BaseModel):
    semantic: str | None = None
    must_tags: list[str] = Field(default_factory=list)
    must_not_tags: list[str] = Field(default_factory=list)
    kinds: list[str] | None = None
    domain: str | None = None
    year_from: int | None = None
    year_to: int | None = None
    k: int = 25
