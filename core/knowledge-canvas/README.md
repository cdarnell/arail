# Knowledge Canvas

> The **Knowledge section** of the AI Lab. A 3D spatial canvas where
> users and agents drop in sources (notes, papers, datasets, URLs, API
> pulls), and the lab curates, clusters, and connects them automatically.

See [`SKILL.md`](SKILL.md) for the full skill contract.

## What's here

```
core/knowledge-canvas/
├── SKILL.md                 Skill contract (read this first)
├── README.md                This file
├── docker-compose.yml       Neo4j + backend services
├── client.py                Python client used by other lab skills
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py
│   │   ├── models/source.py         Universal Source record
│   │   ├── services/
│   │   │   ├── adapters.py          Per-kind source adapters
│   │   │   ├── graph_store.py       LanceDB + Neo4j hybrid
│   │   │   ├── embeddings.py        Pluggable embedder
│   │   │   └── llm_router.py        Wraps the lab's model_router
│   │   ├── routers/
│   │   │   ├── sources.py           ingest / query / link
│   │   │   ├── graph.py             snapshot / semantic-edges
│   │   │   ├── agents.py            cluster-summary / discover-links
│   │   │   ├── nlq.py               natural-language fly-to
│   │   │   └── ws.py                WebSocket for live updates
│   │   └── agents/
│   │       ├── cluster_synthesizer.py
│   │       ├── link_discoverer.py
│   │       └── nlq_planner.py
│   └── scripts/
│       └── import_from_curator.py   Bootstrap canvas from domains/*
├── integrations/
│   ├── from_curator.py              Data Curator → canvas
│   ├── from_experiments.py          Experiment Tracker → canvas
│   └── for_insights.py              Insight Generator ← canvas
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── src/
│       ├── App.tsx
│       ├── main.tsx
│       ├── components/
│       │   ├── SourceCanvas.tsx       The 3D graph
│       │   ├── SourceSidebar.tsx      Glassmorphic detail panel
│       │   ├── SourceDropZone.tsx     Drag-and-drop to ingest
│       │   ├── LegendPanel.tsx        Kind + source filters
│       │   └── NLQBar.tsx             ⌘K fly-to
│       ├── hooks/
│       │   ├── useCanvasSocket.ts
│       │   ├── useSemanticMode.ts
│       │   └── useFlyTo.ts
│       └── lib/api.ts
└── docs/
    ├── ARCHITECTURE.md
    ├── SOURCE_INGESTION.md
    └── GRAPH_RAG.md
```

## Quick start

```bash
# From the lab root
cd core/knowledge-canvas
cp ../../.env.example .env      # or create one with NEO4J_PASSWORD set

# Start the canvas services
docker-compose up -d

# Seed the canvas with sources the Data Curator already knows about
docker-compose exec backend \
  python -m scripts.import_from_curator /lab/domains/farming

# Start the frontend
cd frontend && npm install && npm run dev
```

Open `http://localhost:5173`. Every source the lab has curated is now
a visible node.

## Wiring into other skills

The canvas is opt-in per skill. Each integration is a single import
and one function call:

### Data Curator → canvas

```python
# core/data-curator/data_curator.py
from core.knowledge_canvas.integrations import pipe_to_canvas

def curate(goal):
    result = existing_curator_logic(goal)
    pipe_to_canvas(result)           # <-- add this line
    return result
```

Result: every source the curator finds becomes a node, linked to the
goal by a `MOTIVATES` edge.

### Experiment Tracker → canvas

```python
# core/experiment-tracker/experiment_tracker.py
from core.knowledge_canvas.integrations import pipe_experiment

def complete_experiment(exp_id, results):
    exp = existing_complete_logic(exp_id, results)
    pipe_experiment(exp)             # <-- add this line
    return exp
```

Result: completed experiments appear as `experiment_log` nodes, linked
back to the sources that motivated them via `DERIVED_FROM` edges.

### Insight Generator ← canvas

```python
# core/insight-generator/insight_generator.py
from core.knowledge_canvas.integrations import gather_evidence, cross_source_patterns

def generate_insights(question, domain):
    evidence = gather_evidence(question, domain=domain, k=30,
                               prefer_kinds=["paper", "experiment_log"])
    patterns = cross_source_patterns(evidence)
    return synthesize(patterns)      # existing LLM call
```

Result: insights are grounded in the canvas, with explicit source
attribution and kind diversity metrics.

### Agents (anywhere)

```python
from core.knowledge_canvas.client import canvas

# Agent found a webpage, wants to add it
canvas.ingest({
    "kind": "web_page",
    "uri": "https://...",
    "title": "Cover crop + peanut rotation outcomes",
    "body_excerpt": page_text[:2000],
    "tags": ["peanuts", "cover-crop"],
    "ingested_by": "agent",
})
```

## Design principles

1. **Sources first-class.** Every piece of knowledge the lab touches
   appears in the canvas. Nothing hidden in config files.
2. **Visual by default.** Users see what the lab knows without writing
   queries. Agents see it too — same canvas, same API.
3. **Opt-in integration.** Other skills add one line. If you fork and
   don't want the canvas, delete `integrations/` and the calls go
   silent. Nothing else breaks.
4. **Offline-resilient.** If the canvas backend is down, writes queue
   to a local file and replay on reconnect.
5. **Local-first.** LanceDB is embedded; Neo4j and optional Ollama run
   in containers. No cloud required.
6. **Privacy-first.** All LLM calls go through the lab's `model_router`.
   Set `ROUTER_BACKEND=ollama` for fully air-gapped operation.

## License

MIT, matching the rest of the lab.
