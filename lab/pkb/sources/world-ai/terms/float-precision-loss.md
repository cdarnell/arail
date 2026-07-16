---
title: "Float precision loss"
tags: [world-ai, pathologies]
aliases: [float-precision-loss]
---

Accumulated rounding errors degrade model quality over many steps.

Every floating-point operation introduces a small rounding error. Over millions of training steps with many operations per step, these errors can accumulate into meaningful precision loss, particularly in optimizer accumulators (Adam's m and v tensors). Keeping optimizer state in fp32 (standard in mixed-precision training) mitigates this by providing a wider mantissa for accumulation.

**Example:** Running Adam optimizer states in fp16 instead of fp32 for 100k steps produces model weights that diverge from fp32-trained weights by more than noise level — a known failure mode.

## Related

- [[numerical-underflow]]
- [[numerical-overflow]]
- [[mixed-precision-training]]

Source: PyTorch AMP docs (fp32 master weights); NVIDIA mixed-precision guide
