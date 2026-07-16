---
title: "AWQ"
tags: [world-ai, quantization]
aliases: [awq, Activation-aware Weight Quantization]
---

Low-bit quantization that protects the small fraction of weights tied to large activations, preserving accuracy.

Activation-aware Weight Quantization observes that a small set of weight channels — those multiplying large activations — matter disproportionately, and scales them to reduce their quantization error before quantizing the rest to low bits. It yields accurate 4-bit models that are fast to run and is widely used for deployment.

**Example:** AWQ keeps the ~1% 'salient' channels low-error, so a 4-bit model tracks the full-precision one closely on benchmarks.

## Related

- [[gptq]]
- [[int4]]
- [[quantization]]
- [[calibration]]

Source: authored
