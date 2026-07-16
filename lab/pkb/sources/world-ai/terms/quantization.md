---
title: "Quantization"
tags: [world-ai, quantization]
aliases: [quantization, quantisation]
---

Storing weights/activations in fewer bits (FP16 to INT4) to shrink models and speed inference.

Quantization maps high-precision weights to a smaller numeric type (8-bit, 4-bit, ...) using a scale and zero-point, trading a little accuracy for big savings in memory and bandwidth. It is what lets frontier-scale models run on commodity hardware.

**Example:** Quantizing a 13B model from FP16 (26GB) to Q4 (~7GB) lets it load on a single consumer GPU.

## Related

- [[int4]]
- [[bf16]]
- [[fp8]]
- [[gguf]]

Source: knowledge_base/wiki/concepts/Quantization_SNR_Affine.md
