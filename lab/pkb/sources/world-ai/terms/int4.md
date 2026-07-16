---
title: "INT4"
tags: [world-ai, quantization]
aliases: [int4, 4-bit]
---

4-bit integer weights — the aggressive quantization that makes big models fit on small hardware.

INT4 stores each weight in 4 bits (16 levels), roughly 8x smaller than FP32. Schemes like GPTQ, AWQ, and NF4 pick scales and zero-points to preserve quality. Small models tolerate 4-bit well; frontier models often need 8-bit for the same fidelity.

**Example:** A 7B model in INT4 is ~4GB and runs on a laptop; a 671B MoE at Q4 fits a 1TB SSD for layer-streamed inference.

## Related

- [[quantization]]
- [[gguf]]
- [[qlora]]
- [[bf16]]

Source: knowledge_base/wiki/concepts/Quantization_SNR_Affine.md
