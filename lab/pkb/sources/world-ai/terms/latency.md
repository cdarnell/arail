---
title: "Latency"
tags: [world-ai, performance]
aliases: [latency]
---

The delay before and during a model's response — time-to-first-token and per-token time.

Latency is how quickly a single request responds, distinct from throughput (total volume). Keeping the model warm and prefetching weights cut it.

**Example:** Warm-keeping the SLM drops a dictionary lookup from ~17s cold to a couple of seconds.

## Related

- [[throughput]]
- [[prefetch]]
- [[prompt-caching]]

Source: QuKaiZen AI Dictionary
