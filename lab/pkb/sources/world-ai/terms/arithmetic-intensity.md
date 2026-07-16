---
title: "Arithmetic Intensity"
tags: [world-ai, performance]
aliases: [arithmetic-intensity, roofline]
---

The ratio of compute to memory traffic; it determines whether a workload is compute- or memory-bound.

Arithmetic intensity is FLOPs per byte moved. Low intensity (like LLM decoding) means the workload waits on memory; high intensity (like prefill or large batches) means it's limited by compute. The roofline model uses it to predict achievable performance.

**Example:** Batching raises arithmetic intensity, shifting decoding from memory-bound toward compute-bound.

## Related

- [[memory-bandwidth]]
- [[flops]]
- [[decode-phase]]
- [[continuous-batching]]

Source: authored
