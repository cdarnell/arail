---
title: "PagedAttention"
tags: [world-ai, performance]
aliases: [paged-attention]
---

Storing the KV-cache in non-contiguous pages so long contexts fit without waste.

PagedAttention (from vLLM) manages attention key/value cache in fixed-size pages like virtual memory, eliminating fragmentation and letting many requests share memory — large serving-throughput gains.

**Example:** Paged KV-cache lets a server batch far more concurrent long-context requests.

## Related

- [[kv-cache]]
- [[continuous-batching]]
- [[context-window]]

Source: QuKaiZen AI Dictionary
