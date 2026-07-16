---
title: "Multi-Query Attention"
tags: [world-ai, architecture]
aliases: [multi-query-attention, MQA]
---

All query heads share a single key/value head — the most aggressive KV-cache reduction.

Multi-query attention keeps many query heads but collapses to one shared key and value projection. This minimizes KV-cache size and memory bandwidth during decoding, dramatically speeding long-context inference, at some cost to quality — which grouped-query attention later recovered.

**Example:** 32 query heads but one K/V head means the per-token KV-cache is a fraction of multi-head's.

## Related

- [[grouped-query-attention]]
- [[multi-head-attention]]
- [[kv-cache]]

Source: authored
