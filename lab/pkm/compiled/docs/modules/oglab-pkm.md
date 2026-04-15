---
title: pkm module
section: docs
tags: [python, module]
aliases: [pkm, pkm.py]
source: src/oglab/pkm.py
generated: 2026-04-15T00:51:55Z
---

# pkm module

**Source:** `src/oglab/pkm.py`

OGLab PKM — Personal Knowledge Management for your lab.

Three operations:
  ingest  — process inbox/ into sources/
  compile — merge sources/ + agents/ + notes/ → compiled/ + index.md
  browse  — search and list the knowledge base

## Functions

### `ingest(pkm_root)`

Process everything in inbox/ → sources/.

Returns a summary dict of actions taken.

### `compile_index(pkm_root)`

Build index.md at the PKM root. Returns compile stats.

### `browse(pkm_root)`

Return a structured view of the entire PKM for the portal UI.

### `search(query, pkm_root)`

Full-text search across all PKM text files.

### `write_agent_research(goal_id, content, pkm_root)`

Write a research report to agents/research/.

### `write_agent_experiment(exp_id, content, pkm_root)`

Write an experiment log to agents/experiments/.

### `write_agent_synthesis(topic, content, pkm_root)`

Write a synthesis document to agents/synthesis/.

### `write_agent_recommendation(content, pkm_root)`

Write a recommendation to agents/recommendations/.

### `scaffold(pkm_root)`

Create the full PKM folder structure. Idempotent.
