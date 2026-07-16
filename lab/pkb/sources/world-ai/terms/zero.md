---
title: "ZeRO"
tags: [world-ai, training]
aliases: [zero, Zero Redundancy Optimizer]
---

DeepSpeed's optimizer that partitions optimizer state, gradients, and params to remove memory redundancy.

ZeRO eliminates the memory redundancy of vanilla data parallelism by partitioning optimizer states (stage 1), gradients (stage 2), and parameters (stage 3) across GPUs. It is the idea FSDP also implements, enabling trillion-parameter training.

**Example:** ZeRO-3 lets each of 64 GPUs hold only 1/64 of the optimizer state, freeing memory for larger batches.

## Related

- [[fsdp]]
- [[adamw]]
- [[gradient]]

Source: authored
