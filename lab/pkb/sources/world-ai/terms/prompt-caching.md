---
title: "Prompt Caching"
tags: [world-ai, performance]
aliases: [prompt-caching, ephemeral cache, cache_control, prefix caching]
---

Provider-side cache that bills a repeated prompt prefix at a fraction of fresh-input cost on cache hit.

Prompt caching marks part of a request (typically the system prompt or a stable conversation prefix) with cache_control: ephemeral so the provider keeps a hashed copy. Subsequent requests with the same prefix bill as cache_read tokens — much cheaper than fresh input — while the volatile remainder is processed normally. It is API-side at the provider, distinct from the in-process KV-cache. Each model has a minimum cacheable prefix (e.g. 2048 tokens on Claude Sonnet 4.x); below that floor a well-behaved client omits the marker entirely.

**Example:** ARAIL's Researcher threads an identical system context across 3-5 calls per run, so calls 2-5 hit cache_read instead of fresh input. A ~1.2K-token chat prefix on Sonnet 4 sits below the 2048 floor and only starts caching once multi-turn growth pushes it over.

## Related

- [[kv-cache]]
- [[latency]]
- [[throughput]]
- [[inference]]

Source: authored
