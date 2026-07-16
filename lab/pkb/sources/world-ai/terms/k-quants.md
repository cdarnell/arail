---
title: "K-Quants"
tags: [world-ai, quantization]
aliases: [k-quants, k-quant]
---

The GGUF family of mixed-bit quantization schemes that allocate more bits to important weights.

K-quants are llama.cpp/GGUF quantization formats (Q4_K, Q5_K, Q6_K, etc.) that use a mix of bit-widths within a block, spending more bits on the parts of the weight matrix that matter most. They give better quality per byte than uniform low-bit quantization.

**Example:** A Q4_K_M GGUF holds a 7B model in a few GB while staying close to full-precision quality.

## Related

- [[gguf]]
- [[quantization]]
- [[int4]]
- [[calibration]]

Source: authored
