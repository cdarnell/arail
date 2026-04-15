---
title: costs module
section: docs
tags: [python, module]
aliases: [costs, costs.py]
source: src/oglab/costs.py
generated: 2026-04-15T00:51:55Z
---

# costs module

**Source:** `src/oglab/costs.py`

CostTracker — simulate what local inference would cost via cloud APIs.

Every inference call is tracked: tokens in/out, backend used, latency.
The tracker computes:
  1. Cloud-equivalent cost (what you'd pay OpenRouter / Anthropic / Nvidia)
  2. Local energy cost          (watts × hours × $/kWh)
  3. Net savings                (cloud − energy)

Persists running totals to ``data/costs.json``.

## Classes

### `CostRecord`

A single inference cost record.

### `CostTracker`

**Methods:**

- `__new__(cls)`
- `__init__(self)`
- `track(self, backend, model, tokens_in, tokens_out, latency_ms)`
    - Record one inference call and return the cost breakdown.
- `get_summary(self)`
    - Return full cost summary for the dashboard.
- `get_last_record(self)`
    - Return the most recent cost record.
