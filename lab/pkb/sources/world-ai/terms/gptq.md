---
title: "GPTQ"
tags: [world-ai, quantization]
aliases: [gptq]
---

A one-shot, layer-by-layer post-training quantization method that minimizes per-layer error using second-order info.

GPTQ quantizes a trained model to low bit-widths (e.g. 4-bit) one layer at a time, choosing rounded weights that minimize the layer's output error using approximate second-order (Hessian) information on a small calibration set. It made accurate 4-bit quantization of large models practical without retraining.

**Example:** A 70B model is GPTQ-quantized to 4-bit overnight on one GPU using a few hundred calibration samples, with minor accuracy loss.

## Related

- [[awq]]
- [[int4]]
- [[quantization]]
- [[calibration]]
- [[perplexity]]

Source: authored
