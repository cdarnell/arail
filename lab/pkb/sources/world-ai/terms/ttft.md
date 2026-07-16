---
title: "TTFT"
tags: [world-ai, performance]
aliases: [ttft, time to first token]
---

Time to first token — how long after a request before the model emits its first output token.

Time to first token measures responsiveness: the delay covering queuing plus prefill before any output appears. It is the latency users feel most in streaming interfaces, distinct from overall throughput or per-token speed.

**Example:** A long prompt raises TTFT because prefill must finish before the first token streams out.

## Related

- [[prefill]]
- [[latency]]
- [[throughput]]
- [[continuous-batching]]

Source: authored
