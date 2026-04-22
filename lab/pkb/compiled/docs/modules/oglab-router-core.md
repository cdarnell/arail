---
title: core module
section: docs
tags: [python, module]
aliases: [core, core.py]
source: src/oglab/router/core.py
generated: 2026-04-22T01:03:30Z
---

# core module

**Source:** `src/oglab/router/core.py`

ModelRouter — single entry-point for all inference backends.

## Classes

### `ModelRouter`

Instantiate the correct backend based on env / config and expose a
uniform ``complete()`` interface.

**Methods:**

- `__init__(self, backend)`
- `complete(self, prompt, max_tokens, temperature, top_p)`
- `stream_complete(self, prompt, max_tokens, temperature, top_p)`
- `health_check(self)`
- `switch_backend(self, name)`
