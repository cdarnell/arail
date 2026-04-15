---
title: pkb module
section: docs
tags: [python, module]
aliases: [pkb, pkb.py]
source: src/oglab/pkb.py
generated: 2026-04-15T11:48:11Z
---

# pkb module

**Source:** `src/oglab/pkb.py`

OGLab PKM — Personal Knowledge Management for your lab.

Three operations:
  ingest  — process inbox/ into sources/
  compile — merge sources/ + agents/ + notes/ → compiled/ + index.md
  browse  — search and list the knowledge base

## Functions

### `ingest(pkb_root)`

Process everything in inbox/ → sources/.

Returns a summary dict of actions taken.

### `compile_index(pkb_root)`

Build index.md at the PKM root. Returns compile stats.

### `browse(pkb_root)`

Return a structured view of the entire PKM for the portal UI.

### `search(query, pkb_root)`

Full-text search across all PKM text files.

### `write_agent_research(goal_id, content, pkb_root)`

Write a research report to agents/research/.

### `write_agent_experiment(exp_id, content, pkb_root)`

Write an experiment log to agents/experiments/.

### `write_agent_synthesis(topic, content, pkb_root)`

Write a synthesis document to agents/synthesis/.

### `write_agent_recommendation(content, pkb_root)`

Write a recommendation to agents/recommendations/.

### `scaffold(pkb_root)`

Create the full PKM folder structure. Idempotent.
