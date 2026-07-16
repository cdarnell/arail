---
title: "Parameter"
tags: [world-ai, fundamentals]
aliases: [parameter, weights]
---

A single learned number in a model; their count (e.g. 7B) is the rough measure of model size.

Parameters are the model's learned values — the weights and biases adjusted during training. Their total count (billions for modern LLMs) is shorthand for capacity and largely sets memory footprint: at 16-bit, each parameter is two bytes, so a 7B model needs ~14GB just to hold weights. Quantization shrinks the bytes per parameter, not their number.

**Example:** A 7B model has ~7 billion parameters; in 4-bit that's roughly 3.5GB of weights.

## Related

- [[quantization]]
- [[moe]]
- [[feedforward-network]]
- [[scaling-laws]]

Source: authored
