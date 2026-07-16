---
title: "MFU"
tags: [world-ai, performance]
aliases: [mfu, model FLOPs utilization]
---

Model FLOPs Utilization — the fraction of a chip's peak FLOP/s your training actually achieves.

Model FLOPs Utilization is realized useful FLOPs divided by hardware peak, a single number for how efficiently a training run uses its accelerators. Real large-scale runs often land in the 30-50% range; raising MFU directly cuts cost and time.

**Example:** A run at 45% MFU is using under half the GPUs' theoretical throughput — room to optimize.

## Related

- [[flops]]
- [[throughput]]
- [[memory-bandwidth]]
- [[tensor-parallelism]]

Source: authored
