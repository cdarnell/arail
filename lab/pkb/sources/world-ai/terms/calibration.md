---
title: "Calibration"
tags: [world-ai, quantization]
aliases: [calibration, calibration set]
---

Running a small representative dataset through a model to set quantization ranges or scales.

In post-training quantization, calibration passes a small, representative sample through the model to measure activation/weight statistics, which set the scales and zero-points (or salient channels) used to map values to low precision. A poor or out-of-distribution calibration set degrades the quantized model's accuracy.

**Example:** A few hundred domain sentences used as the calibration set make a 4-bit quantization track full precision on that domain.

## Related

- [[gptq]]
- [[awq]]
- [[quantization]]
- [[int4]]

Source: authored
