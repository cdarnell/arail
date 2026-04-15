---
title: activity module
section: docs
tags: [python, module]
aliases: [activity, activity.py]
source: src/oglab/activity.py
generated: 2026-04-15T11:48:11Z
---

# activity module

**Source:** `src/oglab/activity.py`

ActivityLog — global event bus for the OGLab portal.

All agents, skills, and system components emit events here.
The portal streams them to the dashboard via SSE.

## Classes

### `ActivityLog`

Singleton event bus.  Thread-safe for sync emitters,
asyncio-safe for SSE subscribers.

**Methods:**

- `__new__(cls)`
- `emit(self, source, message, level, data)`
    - Emit an event.  Called from sync or async code.
- `recent(self, n)`
- `subscribe(self)`
    - Yields events as they arrive.  Used by the SSE endpoint.
