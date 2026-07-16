---
title: "Tensor Parallelism"
tags: [world-ai, training]
aliases: [tensor-parallelism]
---

Split individual weight matrices across devices so one layer's math is computed in parallel.

Tensor parallelism partitions the weight matrices of a layer across devices, each computing part of the matmul and exchanging partial results. It lets a single layer too big for one device run across several, at the cost of heavy inter-device communication, so it's used within a fast-interconnect node.

**Example:** A huge FFN matrix is split column-wise across 4 GPUs, each computing a quarter of the output.

## Related

- [[data-parallelism]]
- [[pipeline-parallelism]]
- [[fsdp]]
- [[feedforward-network]]

Source: authored
