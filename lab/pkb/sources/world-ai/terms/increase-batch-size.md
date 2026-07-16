---
title: "Increase batch size / accumulation"
tags: [world-ai, care-actions]
aliases: [increase-batch-size]
---

Use a larger effective batch size to stabilize gradient estimates and improve throughput.

A larger batch size provides a lower-variance gradient estimate, which can smooth convergence and allow a higher learning rate (linear scaling rule). When GPU VRAM prevents a large physical batch, gradient accumulation accumulates gradients over multiple forward passes before each optimizer step, achieving the same effective batch size. This also improves GPU utilization for small per-step batches.

**Example:** A run with batch_size=2 and gradient_accumulation_steps=16 achieves an effective batch of 32 on a 24GB GPU that could not fit batch_size=32 directly.

## Related

- [[out-of-memory-error]]
- [[gradient-accumulation]]
- [[batch-size]]
- [[mixed-precision-training]]

Source: PyTorch gradient accumulation pattern; HF Trainer docs (per_device_train_batch_size, gradient_accumulation_steps); NVIDIA performance guide
