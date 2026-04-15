---
title: __init__ module
section: docs
tags: [python, module]
aliases: [__init__, __init__.py]
source: src/oglab/skills/goal_parser/__init__.py
generated: 2026-04-15T11:48:11Z
---

# __init__ module

**Source:** `src/oglab/skills/goal_parser/__init__.py`

Goal Parser — converts natural language goals into structured objectives.

## Classes

### `GoalParser`

Parse a natural-language goal into a structured dict.

**Methods:**

- `__init__(self, router)`
- `parse(self, goal_text, context)`
- `parse_offline(self, goal_text)`
    - Heuristic-only parsing — no LLM needed (works airgapped with no

## Functions

### `infer_domain(text)`

### `extract_entities(text)`
