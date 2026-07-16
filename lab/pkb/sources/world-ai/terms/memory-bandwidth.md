---
title: "Memory Bandwidth"
tags: [world-ai, performance]
aliases: [memory-bandwidth]
---

How fast data moves between memory and compute — the usual bottleneck for LLM inference.

Memory bandwidth is the rate at which weights and the KV-cache can be read from device memory. Because LLM decoding reads huge amounts of data per token while doing relatively little math, it is bandwidth-bound — which is why quantization and smaller KV-caches speed it up more than raw FLOPs.

**Example:** Decode speed tracks memory bandwidth: halving bytes read per token (via quantization) roughly doubles it.

## Related

- [[decode-phase]]
- [[kv-cache]]
- [[throughput]]
- [[quantization]]
- [[arithmetic-intensity]]

Source: authored
