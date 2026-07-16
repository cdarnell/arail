---
title: "fp16 overflow (loss scale overflow)"
tags: [world-ai, pathologies]
aliases: [fp16-overflow]
---

fp16's limited dynamic range causes activations or gradients to overflow to inf.

Half-precision (fp16) has a maximum representable value of ~65504. When activations, loss values, or gradients exceed this, they overflow to inf, which propagates through the computation and produces NaN in the loss or weights. PyTorch's GradScaler addresses this by multiplying the loss by a large scale factor before the backward pass and dividing afterwards, keeping gradients in fp16 range. If the scale factor itself is too large, the scaled gradients overflow — producing the same NaN symptom.

**Example:** A GradScaler with scale=65536 overflows for a particularly large batch; GradScaler's dynamic scaling automatically halves the scale on overflow detection.

## Related

- [[nan-loss]]
- [[mixed-precision-training]]
- [[numerical-overflow]]

Source: PyTorch AMP GradScaler docs (pytorch.org/docs/stable/amp.html); NVIDIA mixed-precision guide
