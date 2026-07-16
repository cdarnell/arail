---
title: "Action Space"
tags: [world-ai, architecture]
aliases: [action-space]
---

The set of things an agent can do — internal (reason, retrieve) and external (call tools, act in the world).

In the CoALA framework an agent's action space splits into internal actions (reasoning, retrieval from memory, learning) and external/grounding actions (tool calls, environment steps). Defining a clear, bounded action space is what makes an agent controllable and safe.

**Example:** An agent's action space might be {search, run_code, read_file, ask_user} plus internal reasoning.

## Related

- [[coala]]
- [[tool-use]]
- [[grounding]]
- [[react]]
- [[agent-loop]]

Source: authored
