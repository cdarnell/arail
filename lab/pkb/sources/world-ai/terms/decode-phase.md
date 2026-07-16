---
title: "Decode Phase"
tags: [world-ai, inference]
aliases: [decode-phase, decode, generation phase]
---

The token-by-token generation phase, bottlenecked by memory bandwidth rather than compute.

After prefill, decoding generates one token per step, each reading the entire KV-cache and weights — so it is memory-bandwidth bound, not compute bound. This is why KV-cache size, GQA, and quantization dominate generation speed.

**Example:** During decode, throughput is limited by how fast weights and the KV-cache stream from memory, not raw FLOPs.

## Related

- [[prefill]]
- [[kv-cache]]
- [[throughput]]
- [[memory-bandwidth]]
- [[grouped-query-attention]]

Source: authored
