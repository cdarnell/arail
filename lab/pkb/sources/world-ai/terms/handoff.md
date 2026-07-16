---
title: "Handoff"
tags: [world-ai, architecture]
aliases: [handoff, agent handoff]
---

Passing control and context from one agent to another so work continues without losing state.

A handoff transfers a task between agents — often via a committed artifact rather than chat memory — so a specialist picks up exactly where the previous one left off. Clean handoffs (explicit inputs and outputs) are what let multi-agent systems stay coherent and prevent context rot across a long pipeline.

**Example:** A planning agent writes a spec file, then hands off to a builder agent that reads that file rather than re-deriving the plan.

## Related

- [[multi-agent]]
- [[orchestration]]
- [[workflow]]
- [[agent]]

Source: authored
