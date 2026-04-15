---
title: config module
section: docs
tags: [python, module]
aliases: [config, config.py]
source: src/oglab/config.py
generated: 2026-04-15T11:48:11Z
---

# config module

**Source:** `src/oglab/config.py`

OGLab — Configuration loader and runtime paths.

Runtime layout (all relative to the repo root by default):

    lab/
      data/      runtime state: activity.jsonl, goals/, consent/, experiments/, cache/
      models/    downloaded model weights
      pkb/       personal knowledge base tree

Every location is overridable via env var, so deployments can split runtime
state across disks without touching code.

## Functions

### `get(key, default)`
