---
title: "SmoothQuant"
tags: [world-ai, quantization]
aliases: [smoothquant]
---

Shift quantization difficulty from activations to weights so both can go to INT8 cleanly.

SmoothQuant addresses activation outliers (which wreck low-bit quantization) by mathematically migrating scale from activations into weights, smoothing the activation range so both can be quantized to INT8 with little loss. It enables efficient 8-bit inference of large models.

**Example:** SmoothQuant tames the outlier channels that otherwise force activations to stay in 16-bit.

## Related

- [[int8]]
- [[quantization]]
- [[calibration]]
- [[mixed-precision]]

Source: authored
