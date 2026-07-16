---
title: "Temperature"
tags: [world-ai, inference]
aliases: [temperature, sampling temperature]
---

A knob for randomness in generation — low is focused/deterministic, high is creative/diverse.

Temperature scales logits before softmax: below 1 sharpens the distribution (safer, more repetitive), above 1 flattens it (more diverse, more errors). At 0 the model is effectively greedy. It is the simplest lever for output style.

**Example:** Use temperature 0.2 for code or facts; 0.9 for brainstorming or creative writing.

## Related

- [[logits]]
- [[softmax]]
- [[beam-search]]
- [[inference]]

Source: authored
