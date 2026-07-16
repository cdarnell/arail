---
title: "Double Quantization"
tags: [world-ai, quantization]
aliases: [double-quantization]
---

Quantize the quantization constants themselves to squeeze out extra memory, as in QLoRA.

Double quantization, introduced with QLoRA, quantizes the per-block scaling constants of an already-quantized model, saving a further fraction of a bit per parameter. The savings are small per value but meaningful across billions of parameters.

**Example:** Double quantization shaves additional memory off a 4-bit model by compressing its block scales too.

## Related

- [[qlora]]
- [[int4]]
- [[quantization]]
- [[nf4]]

Source: authored
