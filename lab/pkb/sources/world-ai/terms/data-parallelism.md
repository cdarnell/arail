---
title: "Data Parallelism"
tags: [world-ai, training]
aliases: [data-parallelism]
---

Replicate the model across devices, split the batch, and average gradients each step.

Data parallelism puts a full copy of the model on each device, feeds each a different slice of the batch, and synchronizes gradients (all-reduce) so all replicas stay identical. It is the simplest way to scale training throughput; ZeRO/FSDP shard the replicated state to save memory.

**Example:** Across 8 GPUs, each handles 1/8 of the batch and they average gradients before the step.

## Related

- [[fsdp]]
- [[zero]]
- [[tensor-parallelism]]
- [[pipeline-parallelism]]
- [[batch-size]]

Source: authored
