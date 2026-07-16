---
title: "Planning"
tags: [world-ai, architecture]
aliases: [planning, task decomposition]
---

An agent breaks a goal into an ordered set of subtasks before (or while) acting.

Planning is the internal action of decomposing a high-level goal into steps and sequencing them, optionally revising the plan as observations arrive. Approaches range from plan-then-execute (fix the whole plan up front) to interleaved planning (replan each step, as in ReAct). Good planning keeps long-horizon tasks coherent.

**Example:** Given 'organize a launch', the agent plans: draft copy -> get review -> schedule post -> notify list, then executes each.

## Related

- [[agent]]
- [[react]]
- [[reasoning]]
- [[orchestration]]
- [[workflow]]

Source: authored
