---
title: "QAT"
tags: [world-ai, quantization]
aliases: [qat, quantization-aware training]
---

Quantization-aware training: simulate low precision during training so the model learns to tolerate it.

Quantization-aware training inserts fake-quantization ops during training so weights and activations adapt to the eventual low-bit format, usually beating post-training quantization on accuracy at the cost of a training run. Used when the last points of quality matter.

**Example:** QAT recovers accuracy a 4-bit model lost under post-training quantization, by training with the rounding in the loop.

## Related

- [[quantization]]
- [[gptq]]
- [[awq]]
- [[calibration]]
- [[int4]]

Source: authored
