---
title: researcher module
section: docs
tags: [python, module]
aliases: [researcher, researcher.py]
source: src/oglab/agents/researcher.py
generated: 2026-04-15T11:48:11Z
---

# researcher module

**Source:** `src/oglab/agents/researcher.py`

ResearcherAgent — the lab's default background agent.

Takes a parsed goal, auto-generates hypotheses, designs experiments,
gathers sources (via Curator + consent), analyzes findings, and
produces a report.  Every step is emitted to the ActivityLog so the
dashboard shows live progress.

The agent's entire personality is shaped by the lab's *intent* — set at
bootstrap time.  An AI Engineer lab produces hypotheses about models and
architectures.  A Farming lab produces hypotheses about soil, crops, and
yield.  The intent rewrites the system context for every LLM call.

## Classes

### `ResearcherAgent`

Autonomous research agent that drives experiments toward a goal.

**Methods:**

- `__init__(self)`
- `status(self)`
- `start(self, parsed_goal)`
- `pause(self)`
- `resume(self)`
- `stop(self)`
