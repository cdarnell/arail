---
title: "Grouped-Query Attention"
tags: [world-ai, architecture]
aliases: [grouped-query-attention, GQA]
---

Share key/value heads across groups of query heads to shrink the KV-cache with little quality loss.

Grouped-query attention is the middle ground between full multi-head attention (one K/V per query head) and multi-query attention (one K/V for all). Query heads are partitioned into groups that share a single key/value head, cutting KV-cache memory and bandwidth — the main inference bottleneck for long contexts — while keeping most of MHA's quality. It is standard in recent large models.

**Example:** A model with 32 query heads but 8 K/V groups stores a quarter of the KV-cache of full MHA.

## Related

- [[multi-head-attention]]
- [[multi-query-attention]]
- [[kv-cache]]
- [[attention]]

Source: authored
