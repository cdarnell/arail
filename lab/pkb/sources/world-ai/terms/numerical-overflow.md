---
title: "Numerical overflow"
tags: [world-ai, pathologies]
aliases: [numerical-overflow]
---

Values exceed the representable range and become inf — NaN propagates downstream.

Numerical overflow is the counterpart to underflow: a value grows beyond the maximum representable number for the floating-point format and becomes inf. inf in any computation typically produces NaN (inf - inf = NaN, inf × 0 = NaN). In fp16 training, this is the dominant source of NaN loss. In fp32 training it is rare except with very high LR or unnormalized weights.

**Example:** A logit of 70000 in fp16 overflows to inf; log_softmax of inf produces NaN cross-entropy.

## Related

- [[fp16-overflow]]
- [[nan-loss]]
- [[numerical-underflow]]

Source: PyTorch AMP docs; NVIDIA mixed-precision guide
