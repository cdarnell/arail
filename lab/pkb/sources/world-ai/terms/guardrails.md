---
title: "Guardrails"
tags: [world-ai, rl-alignment]
aliases: [guardrails, safety filters]
---

Runtime checks around a model that block, filter, or reshape unsafe inputs and outputs.

Guardrails are the deployment-time controls layered around a model — input/output classifiers, content filters, schema/format validators, and policy checks — that catch what alignment training missed. Unlike alignment baked into weights, guardrails are external, fast to update, and independently auditable.

**Example:** An output guardrail blocks a response containing personal data before it reaches the user, even if the model generated it.

## Related

- [[alignment]]
- [[red-teaming]]
- [[constitutional-ai]]
- [[hallucination]]

Source: authored
