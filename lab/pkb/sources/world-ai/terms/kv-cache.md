---
title: "KV-Cache"
tags: [world-ai, performance]
aliases: [kv-cache, key-value cache, KV cache]
---

Cached key/value tensors from past tokens so generation does not recompute the whole sequence each step.

During autoregressive generation each new token attends to all previous tokens. The KV-cache stores the keys and values already computed, so each step only processes the new token — turning quadratic regeneration into linear. It is the main consumer of inference memory.

**Example:** Generating token 1000 reuses 999 cached K/V pairs; only the new token's attention is computed. vLLM's PagedAttention manages this cache efficiently.

## Related

- [[attention]]
- [[speculative-decoding]]
- [[vllm]]
- [[inference]]
- [[prompt-caching]]

Source: authored
