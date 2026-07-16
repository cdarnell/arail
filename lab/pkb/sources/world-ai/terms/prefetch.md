---
title: "Prefetch"
tags: [world-ai, performance]
aliases: [prefetch]
---

Loading the next layer from disk while the current compute runs, hiding I/O latency.

Prefetching overlaps disk reads with computation: while the GPU works on layer N, layer N+1 is already streaming in, so the model rarely waits on storage. It's what makes layer streaming fast.

**Example:** AeroLLM prefetches the next shard so the GPU stays busy instead of stalling on the SSD.

## Related

- [[layer-streaming]]
- [[latency]]
- [[throughput]]

Source: QuKaiZen AI Dictionary
