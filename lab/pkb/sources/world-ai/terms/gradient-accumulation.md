---
title: "Gradient Accumulation"
tags: [world-ai, training]
aliases: [gradient-accumulation]
---

Sum gradients over several micro-batches before updating, simulating a large batch on limited memory.

Gradient accumulation runs several forward/backward passes, adding their gradients, and only then steps the optimizer — so a small GPU can train with a large effective batch size. It trades extra time for memory headroom.

**Example:** Accumulating 8 micro-batches of 4 gives an effective batch of 32 without the memory of a real 32-batch.

## Related

- [[batch-size]]
- [[fsdp]]
- [[zero]]
- [[learning-rate]]

Source: authored
