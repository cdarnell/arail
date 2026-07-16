---
title: "CUDA Graphs"
tags: [world-ai, performance]
aliases: [cuda-graphs]
---

Capture a fixed sequence of GPU operations once and replay it, eliminating per-step launch overhead.

CUDA Graphs record a static graph of GPU work and replay it as a single submission, removing the CPU-side kernel-launch overhead that otherwise dominates small, repetitive steps like token decoding. They meaningfully speed up low-latency inference.

**Example:** Replaying a captured CUDA graph per decode step cuts the CPU launch overhead of many tiny kernels.

## Related

- [[kernel-fusion]]
- [[cuda]]
- [[torch-compile]]
- [[latency]]

Source: authored
