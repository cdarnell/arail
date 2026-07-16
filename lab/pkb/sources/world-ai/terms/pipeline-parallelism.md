---
title: "Pipeline Parallelism"
tags: [world-ai, training]
aliases: [pipeline-parallelism]
---

Place different layers on different devices and stream micro-batches through them like an assembly line.

Pipeline parallelism splits the model by layer across devices; micro-batches flow through the stages so multiple are in flight at once. Scheduling matters — naive pipelines waste time in 'bubbles' while stages wait. It complements data and tensor parallelism in large-scale training.

**Example:** Layers 1-10 on GPU A, 11-20 on GPU B; while B works on batch 1, A starts batch 2.

## Related

- [[data-parallelism]]
- [[tensor-parallelism]]
- [[fsdp]]

Source: authored
