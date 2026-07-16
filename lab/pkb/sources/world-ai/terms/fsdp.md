---
title: "FSDP"
tags: [world-ai, training]
aliases: [fsdp, Fully Sharded Data Parallel]
---

Shards model parameters, gradients, and optimizer state across GPUs so huge models fit in training.

FSDP (PyTorch) splits parameters, gradients, and optimizer states across all data-parallel GPUs, gathering each shard only when needed. It trains models far larger than a single GPU's memory, with less overhead than older model-parallel schemes.

**Example:** Training a 70B model across 8 GPUs: FSDP keeps only 1/8 of the weights resident on each, all-gathering layers on the fly.

## Related

- [[zero]]
- [[backprop]]
- [[gradient]]

Source: authored
