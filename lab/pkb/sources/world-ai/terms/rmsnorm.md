---
title: "RMSNorm"
tags: [world-ai, architecture]
aliases: [rmsnorm]
---

A lighter normalization that scales activations by their root-mean-square, without subtracting the mean.

RMSNorm normalizes a vector by its root-mean-square and a learned scale, skipping LayerNorm's mean-centering and bias. It is cheaper and empirically as effective, so most recent large models use it in place of LayerNorm.

**Example:** Swapping LayerNorm for RMSNorm trims compute per layer with no quality loss in large transformers.

## Related

- [[layernorm]]
- [[residual-connection]]
- [[transformer]]

Source: authored
