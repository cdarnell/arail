---
title: "Mixed Precision"
tags: [world-ai, quantization]
aliases: [mixed-precision, AMP]
---

Use lower precision for most math but keep sensitive parts in higher precision for stability.

Mixed-precision computation runs the bulk of operations in a low-precision format (FP16/BF16/FP8) for speed and memory while keeping numerically sensitive pieces — master weights, accumulations, certain norms — in higher precision. It is standard for both training (with loss scaling) and inference, capturing most of the speedup without the instability of going fully low-precision.

**Example:** Training in BF16 but accumulating gradients and keeping master weights in FP32 trains fast yet stably.

## Related

- [[bf16]]
- [[fp8]]
- [[int8]]
- [[quantization]]
- [[gradient-clipping]]

Source: authored
