---
title: "Memory Stream"
tags: [world-ai, architecture]
aliases: [memory-stream]
---

A time-ordered log of an agent's observations, scored by recency, importance, and relevance for retrieval.

Popularized by the 'generative agents' work, a memory stream is an append-only list of natural-language memory records. To act, the agent retrieves a subset ranked by a blend of recency, importance, and relevance to the current situation, and periodically synthesizes higher-level reflections back into the stream.

**Example:** An agent's stream logs 'bought coffee at 8am'; later, retrieval surfaces it plus a reflection 'I have a morning coffee routine' when planning the day.

## Related

- [[episodic-memory]]
- [[reflection]]
- [[long-term-memory]]
- [[coala]]

Source: authored
