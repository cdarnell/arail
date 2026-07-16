---
title: "Batch Size"
tags: [world-ai, training]
aliases: [batch-size]
---

How many training examples are processed before each weight update.

Batch size sets how many samples contribute to one gradient estimate. Larger batches give smoother gradients and better hardware utilization but need scaled learning rates and more memory; gradient accumulation simulates large batches on limited memory. It interacts tightly with learning rate.

**Example:** An effective batch of 1M tokens is reached by accumulating gradients over many small micro-batches across GPUs.

## Related

- [[learning-rate]]
- [[gradient]]
- [[fsdp]]
- [[zero]]
- [[epoch]]

Source: authored
