---
title: "Quantization-aware training"
tags: [world-ai, quantization]
aliases: [quantization-aware-training]
---

Train with simulated quantization so the model adapts to the reduced precision.

QAT inserts simulated quantization operations (fake quantization) during training, so the model learns to be robust to the quantization error. The gradients flow through the fake-quantize operations via the straight-through estimator. QAT recovers quality lost in PTQ at the cost of an additional training pass, and is preferred when deployment quality matters more than conversion speed.

**Example:** QAT on a 1B model for 1k steps after int8 quantization recovers 90% of the PTQ quality loss compared to fp16.

## Related

- [[quantization]]
- [[post-training-quantization]]

Source: Jacob et al. — Quantization and Training of Neural Networks for Efficient Integer-Arithmetic-Only Inference arXiv:1712.05877; PyTorch quantization docs
