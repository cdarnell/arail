---
title: "Prefill"
tags: [world-ai, inference]
aliases: [prefill]
---

The compute-heavy first phase where the model ingests the whole prompt in parallel.

Prefill processes all prompt tokens at once to build the KV-cache before generation begins; it is compute-bound and largely sets the time to first token. It contrasts with the memory-bound decode phase that emits tokens one at a time.

**Example:** A long prompt spends most of its latency in prefill, populating the KV-cache before the first output token.

## Related

- [[decode-phase]]
- [[kv-cache]]
- [[ttft]]
- [[latency]]
- [[continuous-batching]]

Source: authored
