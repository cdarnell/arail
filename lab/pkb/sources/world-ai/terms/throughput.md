---
title: "Throughput"
tags: [world-ai, performance]
aliases: [throughput]
---

How many tokens a system generates per unit time, across all requests.

Throughput measures total tokens/second a serving stack produces; it trades off against per-request latency. Speculative decoding and batching push it up.

**Example:** Speculative decoding lifts AeroLLM throughput up to 7× on 70B+ teachers.

## Related

- [[latency]]
- [[speculative-decoding]]
- [[continuous-batching]]
- [[prompt-caching]]

Source: QuKaiZen AI Dictionary
