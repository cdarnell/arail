---
title: "Post-training quantization"
tags: [world-ai, quantization]
aliases: [post-training-quantization]
---

Quantize a trained model without further training — fast but some quality loss.

Post-training quantization (PTQ) converts a trained fp16/fp32 model to a lower-bit format (int8, int4) without any additional training. It requires a small calibration dataset to compute quantization scales. PTQ is faster and simpler than QAT but trades some quality for convenience. GPTQ and bitsandbytes NF4 are popular PTQ methods for LLMs.

**Example:** GPTQ quantization converts a 7B fp16 model to int4 using 128 calibration examples in about 1 hour on a GPU, producing a model with near-identical perplexity.

## Related

- [[quantization]]
- [[quantization-aware-training]]

Source: Frantar et al. — GPTQ arXiv:2210.17323; bitsandbytes (load_in_4bit) docs
