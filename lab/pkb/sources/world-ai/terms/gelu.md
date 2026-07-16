---
title: "GELU"
tags: [world-ai, architecture]
aliases: [gelu, Gaussian Error Linear Unit]
---

A smooth activation function used in transformer feed-forward layers.

GELU multiplies an input by the probability it is positive under a Gaussian, giving a smooth, slightly negative-tolerant alternative to ReLU. Its smoothness helps gradient flow, and it is the default activation in many transformer MLP blocks (with SwiGLU now common too).

**Example:** A transformer's feed-forward block applies GELU between its two linear layers.

## Related

- [[transformer]]
- [[layernorm]]

Source: authored
