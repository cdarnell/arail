---
title: "NF4"
tags: [world-ai, quantization]
aliases: [nf4, NormalFloat4]
---

A 4-bit 'normal float' data type, used in QLoRA, tuned for the bell-curve distribution of weights.

NF4 (4-bit NormalFloat) is an information-theoretically motivated 4-bit format whose quantization levels match the roughly normal distribution of neural-network weights, giving lower error than uniform 4-bit. It is the storage format behind QLoRA.

**Example:** QLoRA stores the frozen base model in NF4, fitting a 70B model on a single large GPU.

## Related

- [[qlora]]
- [[int4]]
- [[quantization]]
- [[double-quantization]]
- [[bf16]]

Source: authored
