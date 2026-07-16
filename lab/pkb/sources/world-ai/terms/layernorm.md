---
title: "LayerNorm"
tags: [world-ai, architecture]
aliases: [layernorm, Layer Normalization, RMSNorm]
---

Normalizes activations within each layer to keep training stable; modern LLMs often use RMSNorm.

Layer normalization rescales each token's activation vector to zero mean and unit variance (RMSNorm skips the mean), stabilizing and speeding training. Placement (pre-norm vs post-norm) and the variant chosen materially affect deep-transformer stability.

**Example:** Llama-style models apply pre-RMSNorm before attention and the feed-forward block for stable deep training.

## Related

- [[transformer]]
- [[attention]]
- [[gelu]]

Source: authored
