---
title: "Numerical underflow"
tags: [world-ai, pathologies]
aliases: [numerical-underflow]
---

Values become too small to represent and round to zero — silent precision loss.

Numerical underflow occurs when a floating-point computation produces a value smaller than the minimum representable normal number for the format, causing it to round to zero (or to a subnormal). In fp16, the minimum normal is ~6e-5. Log-probabilities and softmax computations are most vulnerable. Underflow in gradients causes them to vanish silently — the model stops learning without any error message.

**Example:** Softmax over a large vocabulary in fp16 underflows for tail tokens whose logits are very negative, producing zero probabilities and NaN cross-entropy.

## Related

- [[fp16-overflow]]
- [[nan-loss]]
- [[float-precision-loss]]

Source: PyTorch numerical stability docs; NVIDIA mixed-precision guide (numerical formats)
