# Knowledge Canvas — Architecture

## Where this sits in the lab

```
  User goal
     │
     ▼
  Goal Parser ──► Data Curator ──► Knowledge Canvas ──► Experiment Tracker
                       │            ▲         │
                       │            │         ▼
                       └────────────┘      Insight Generator
                         agents drop        queries the canvas
                         sources in         for evidence
```

The canvas is the **persistent memory** of the lab. Other skills write
into it (curator, tracker, agents) and read out of it (insight generator,
UI, other agents). It doesn't do its own goal parsing or experiment
design — that stays in the existing skills.

## Two stores, one purpose

**LanceDB** — embedded vector store (file-based, no server).
- What's in it: every Source + its embedding vector + flat metadata
- What it's for: semantic search, hybrid filters (`kind IN (...) AND year >= 2023`)
- Why embedded: no extra container, file-ownable by the user, versioning built in

**Neo4j** — graph database for typed relationships.
- What's in it: Source nodes + edges like `LINKS_TO`, `MOTIVATES`,
  `DISCOVERED_FROM`, `CITES`, `SUGGESTED`
- What it's for: multi-hop queries you can't express in a vector store
- Why not LanceDB alone: faking traversals in Python costs one round-trip
  per hop; real-world questions easily go 2-3 hops

Together they enable **Graph RAG**: filter by graph structure, rank by
vector similarity. See [`GRAPH_RAG.md`](GRAPH_RAG.md) for query patterns.

## The Source record

Everything the canvas stores is a `Source` (see
`backend/app/models/source.py`). One shape, many kinds:

| kind             | Example                           |
|------------------|-----------------------------------|
| `markdown`       | User notes, example goals         |
| `paper`          | arXiv, peer-reviewed publications |
| `web_page`       | Agent-scraped URL                 |
| `api_snapshot`   | USDA Quickstats pull              |
| `dataset`        | CSV/Parquet with metadata card    |
| `experiment_log` | Experiment Tracker output         |
| `image`          | Photos, charts, diagrams          |

**Deterministic IDs.** `id = sha1(uri)[:16]`. Re-ingesting the same
source updates in place. Agents can ingest without worrying about
duplicates.

## Edge kinds

Neo4j holds six relationship types, each with visual differentiation in
the frontend:

| Rel               | Meaning                                    |
|-------------------|--------------------------------------------|
| `LINKS_TO`        | Explicit wikilink from a markdown source   |
| `MOTIVATES`       | Source → experiment or goal it drove       |
| `DISCOVERED_FROM` | Agent provenance: "I found B via A"        |
| `CITES`           | Paper → paper citation                     |
| `DERIVED_FROM`    | Experiment → source it was based on        |
| `SUGGESTED`       | Agent-proposed link with confidence score  |

## Data flow

### Ingest
```
Agent / Curator / User
        │
        ▼
   POST /api/sources/ingest
        │
        ▼
  adapter (kind-specific)  ──► Source record
        │
        ├─► embed(title + excerpt)  ──► LanceDB
        └─► MERGE (n:Source)        ──► Neo4j
        │
        ▼
   WebSocket broadcast ──► live update in frontend
```

### Query
```
Insight Generator / NLQ / UI
        │
        ▼
   POST /api/sources/query {semantic, kinds, domain, year_from, ...}
        │
        ▼
   embed(semantic) ──► LanceDB vector search
         └── with SQL-ish predicate
        │
        ▼
   Post-filter tags (LanceDB list ops vary by version)
        │
        ▼
   Return ranked Sources
```

### Agent-discovered links
```
Periodic (or manual trigger)
        │
        ▼
   GET orphans (Neo4j: no incoming/outgoing edges)
        │
        ▼
   For each orphan: get semantic neighbors from LanceDB
        │
        ▼
   LLM judges relation (JSON {confidence, relation, reason})
        │
        ▼
   If confidence > threshold: MERGE (:SUGGESTED edge) in Neo4j
        │
        ▼
   Broadcast new edge over WS ──► frontend shows dashed amber line
```

## Frontend rendering

Uses `react-force-graph-3d` with shared geometry/material caches —
~10k nodes at 60fps on typical hardware. Per-frame frustum culling
skips drawing off-screen nodes. Node color encodes `kind`; edge style
encodes relationship type.

For vaults past ~15k sources, the design for a true InstancedMesh
renderer is at `docs/INSTANCED_RENDERER.md` (from the standalone
prototype). Same prop shape, so it drops in as a replacement.

## Offline resilience

The canvas is **additive**. If the backend is down:
- Other skills can still operate; `canvas.ingest()` queues to a local
  JSONL file and replays on reconnect.
- `canvas.query()` returns `[]` and the calling skill degrades to its
  pre-canvas behavior (curator still discovers sources, insight
  generator still synthesizes without evidence metrics).

The canvas should **enhance** the lab, never block it.

## Security

- `/api/sources/{id}` returns source metadata + body excerpt (no full
  file contents by default; excerpts cap at 4000 chars).
- No path traversal: the canvas doesn't read arbitrary files off the
  filesystem. Callers supply the excerpt at ingest time.
- Local-first deployment assumption: the API binds to localhost.
  Exposing publicly requires adding auth (not in scope for v1).
