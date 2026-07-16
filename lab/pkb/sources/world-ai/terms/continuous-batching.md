---
title: "Continuous Batching"
tags: [world-ai, performance]
aliases: [continuous-batching, in-flight batching]
---

Swapping requests in and out of a running batch every step to keep the GPU saturated.

Continuous (in-flight) batching removes finished sequences and adds new ones each step, instead of waiting for a whole batch to complete — dramatically improving serving throughput and latency.

**Example:** A server using continuous batching serves many users at once with no idle GPU gaps.

## Related

- [[paged-attention]]
- [[throughput]]
- [[latency]]

Source: QuKaiZen AI Dictionary
