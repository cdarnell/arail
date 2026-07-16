---
title: "INT8"
tags: [world-ai, quantization]
aliases: [int8, 8-bit integer]
---

8-bit integer representation — a common, low-risk quantization that roughly halves memory versus 16-bit.

INT8 stores weights and/or activations as 8-bit integers with a scale factor, cutting memory and enabling fast integer matrix multiply on supported hardware. It is the conservative quantization choice: accuracy loss is usually negligible, unlike the more aggressive 4-bit formats. Mixed approaches keep sensitive parts in higher precision.

**Example:** An INT8 model halves the VRAM of a BF16 model and runs faster on hardware with INT8 tensor cores, with little quality change.

## Related

- [[int4]]
- [[fp8]]
- [[bf16]]
- [[quantization]]
- [[mixed-precision]]

Source: authored
