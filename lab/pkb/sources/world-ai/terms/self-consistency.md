---
title: "Self-Consistency"
tags: [world-ai, inference]
aliases: [self-consistency]
---

Sample several reasoning chains and take the majority answer, trading compute for accuracy.

Self-consistency improves chain-of-thought by sampling multiple independent reasoning paths and selecting the most common final answer, since correct reasoning tends to converge while errors scatter. It is a simple, strong test-time scaling technique.

**Example:** Drawing 10 reasoning chains and voting on the answer beats taking a single chain.

## Related

- [[chain-of-thought]]
- [[sampling]]
- [[reasoning]]
- [[process-reward-model]]

Source: authored
