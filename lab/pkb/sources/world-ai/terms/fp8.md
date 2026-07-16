---
title: "FP8"
tags: [world-ai, quantization]
aliases: [fp8, 8-bit float]
---

An 8-bit floating-point format for faster training and inference on H100-class hardware.

FP8 represents numbers in 8 bits (e4m3 or e5m2 variants), halving memory and doubling throughput versus BF16 on supporting GPUs. It needs careful scaling but is increasingly used for both training and high-throughput inference.

**Example:** Serving a teacher in FP8 on H100s roughly doubles tokens/sec versus BF16 with minimal quality loss.

## Related

- [[bf16]]
- [[int4]]
- [[quantization]]
- [[vllm]]

Source: authored
