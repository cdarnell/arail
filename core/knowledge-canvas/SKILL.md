# Knowledge Canvas Skill

> Visual, spatial, AI-curated knowledge graph — the **front-and-center
> Knowledge section** of the AI Lab. Users and agents drop in sources
> (notes, papers, datasets, URLs, API pulls) and the system curates,
> clusters, and connects them automatically.

## What this skill does

This is the lab's **Knowledge section**. Every source the lab touches
— whether dropped in by a user, returned by the Data Curator skill, or
discovered by an autonomous agent — appears here as a node in a 3D
spatial graph. The graph self-organizes by semantic similarity, explicit
links, and agent-discovered relationships.

It replaces static "folders of JSON" and "lists of URLs" with an
explorable spatial map where:

- **Sources are visible by default.** No hunting through directory trees.
- **Related sources cluster together.** Vector similarity drives layout.
- **Agents can narrate the graph.** Click a cluster, get a synthesis.
- **The user can fly through it.** "Take me to 2024 peanut yield data."

## How it fits the lab

```
   Goal Parser ──► Data Curator ──► Knowledge Canvas ──► Experiment Tracker
                                    ▲         │
                                    │         ▼
                                  agents   Insight Generator
                                  drop in     queries the canvas
                                  sources
```

- **Data Curator** writes sources *into* the canvas (via
  `sources.ingest()`).
- **Insight Generator** reads *from* the canvas (via
  `sources.query()`) to find patterns across sources.
- **Experiment Tracker** links experiments to the source nodes that
  motivated them.
- **Agents** poll for orphaned sources and autonomously suggest links.

## Source types supported

The canvas treats all sources uniformly as nodes. Ingestion adapters
normalize them:

| Type              | Example                                       | Adapter              |
|-------------------|-----------------------------------------------|----------------------|
| `markdown`        | A note the user wrote                         | `md_adapter`         |
| `api_snapshot`    | USDA Quickstats pull, timestamped             | `api_adapter`        |
| `paper`           | arXiv abstract + PDF link                     | `paper_adapter`      |
| `web_page`        | URL captured by an agent                      | `web_adapter`        |
| `dataset`         | CSV/Parquet with metadata card                | `dataset_adapter`    |
| `experiment_log`  | Output of Experiment Tracker                  | `experiment_adapter` |
| `image`           | A soil photo, a chart                         | `image_adapter`      |

All adapters produce a common `Source` record (see
`backend/app/models/source.py`) with: `id`, `kind`, `title`, `tags`,
`body_excerpt`, `uri`, `created_at`, plus kind-specific metadata.

## Storage

- **LanceDB** (embedded, file-based) — vector store for similarity search
- **Neo4j** (containerized) — typed relationships for Graph RAG queries

Both are described in `backend/app/services/graph_store_lance.py`. The
lab stays local-first: zero cloud dependencies by default.

## Quick start (inside the lab)

```bash
# From the lab root
cd core/knowledge-canvas

# Start the canvas services (Neo4j + backend)
docker-compose up -d

# One-shot import of existing curated sources from Data Curator
python -m backend.scripts.import_from_curator ../../domains/farming

# Run the frontend
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. The canvas appears with every source the
lab has curated so far.

### Arail integration notes

- Imported location: `core/knowledge-canvas/`
- Backend mount in portal: `http://127.0.0.1:8080/knowledge-canvas/`
   (native canvas API routes stay under this prefix, e.g.
   `/knowledge-canvas/api/graph/snapshot`)
- Knowledge tab spotlight: `http://127.0.0.1:8080/knowledge` includes a
   centered graph card that expands to fullscreen explorer.

## Wiring into other skills

### From Data Curator

```python
# core/data-curator/data_curator.py
from core.knowledge_canvas.client import canvas

def curate(goal):
    sources = discover_sources_for(goal)  # existing logic
    for src in sources:
        canvas.ingest(src)                # <-- new line
    return sources
```

### From an agent

```python
from core.knowledge_canvas.client import canvas

# Agent discovers a relevant webpage
canvas.ingest({
    "kind": "web_page",
    "uri": "https://soilhealthinstitute.org/...",
    "title": "Cover crop + peanut rotation outcomes",
    "body_excerpt": page_text[:2000],
    "tags": ["peanuts", "cover-crop", "agent-discovered"],
})
```

### From Insight Generator

```python
# Query the canvas to find patterns
related = canvas.query(
    semantic="nitrogen timing yield",
    must_tags=["peanuts"],
    year_from=2022,
    k=20,
)
```

## Design principles

1. **Sources are first-class.** Every piece of knowledge the lab touches
   lands here. Nothing is "hidden in a config file."
2. **Visual by default.** Users and agents see what the lab knows
   without writing queries.
3. **Agent-curated.** Autonomous link discovery runs in the background,
   proposing connections with confidence scores.
4. **Vine-friendly.** Drops into any existing lab fork — no rewrite
   required. Uses the lab's `model_router` for all LLM calls.
5. **Privacy-first.** All inference and storage local by default.
   Cloud routing is opt-in via the existing router config.

## Files

| Path | Purpose |
|------|---------|
| `backend/` | FastAPI service, LanceDB + Neo4j store, agents |
| `frontend/` | React + Three.js spatial canvas |
| `client.py` | Python client for other lab skills to use |
| `docker-compose.yml` | Neo4j + backend containers |
| `docs/ARCHITECTURE.md` | System overview |
| `docs/SOURCE_INGESTION.md` | How to add new source types |
| `docs/GRAPH_RAG.md` | Hybrid query patterns |
