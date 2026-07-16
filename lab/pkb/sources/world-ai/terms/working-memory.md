---
title: "Working Memory"
tags: [world-ai, architecture]
aliases: [working-memory, short-term memory]
---

An agent's active scratchpad — the small, volatile state it holds for the current decision.

In the CoALA framing, working memory is the agent's transient state for the current cycle: the active goal, intermediate reasoning, recently retrieved facts, and the latest observation. It is what actually flows into the prompt at each step and is overwritten as the task proceeds — analogous to RAM, not disk. Its capacity is bounded by the context window.

**Example:** Mid-task, the agent's working memory holds 'goal: book a flight; found 2 options; need user's date preference' — discarded once the booking completes.

## Related

- [[coala]]
- [[context-window]]
- [[episodic-memory]]
- [[agent]]

Source: authored
